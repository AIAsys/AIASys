"""
Session 级 task / plan 持久化与投影。

本模块只处理当前会话的结构化任务与计划状态，不涉及 AutoTask 工作区调度。
任务状态写入 session metadata.json；计划正文写入 .aiasys/session/_active/plans/。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from app.models.session import SessionMetadata, SessionPlanState, SessionTaskItem
from app.services.session.constants import ACTIVE_SESSION_STATE_DIR_NAME, METADATA_FILE_NAME

logger = logging.getLogger(__name__)

TaskStatus = Literal["pending", "in_progress", "completed", "cancelled"]
PlanModeStatus = Literal["active", "inactive"]
PlanApprovalStatus = Literal["draft", "pending_approval", "approved", "rejected"]
TaskItem = SessionTaskItem

TASK_MANAGEMENT_PROTOCOL = """\
# 任务管理规则

1. 不要在脑中维护任务清单，使用 task_create / task_update / task_list。
2. 多步骤任务要立刻拆分为 task。
3. 已批准的 plan 要先转成 task 再执行。
4. 标记 completed 前先确认工作确实完成。
5. 同一时刻只保留一个 in_progress task。
6. 不要启动依赖尚未满足的 task。
7. 完成任务后立刻更新 task 状态。
8. 上下文压缩后活跃 task 会保留，不要重复创建。
"""

PLAN_WORKFLOW_GUIDANCE = """\
# 规划工作流

1. Explore & Analyze：先只读探索，梳理受影响模块与依赖。
2. Consult：复杂方案先询问用户，明确取舍。
3. Draft：把计划写到当前 session 的 plans 目录。
4. Review & Approval：退出 plan mode，等待用户批准后再执行。
"""

PLAN_MODE_ALLOWED_TOOL_NAMES: tuple[str, ...] = (
    "tool_search",
    "ReadMediaFile",
    "ReadFile",
    "ReadNotebook",
    "ListSessionNotebooks",
    "ReadNotebookOutputs",
    "ListKernelEnvs",
    "KnowledgeBaseQuery",
    "ListKnowledgeBases",
    "SearchKnowledgeGraphEntities",
    "GetKnowledgeGraphEntityDetail",
    "ListKnowledgeGraphs",
    "QueryEntityRelations",
    "GetCommunityReport",
    "ListSkills",
    "LoadSkill",
    "AskUser",
    "task_list",
    "enter_plan_mode",
    "exit_plan_mode",
)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _sanitize_line_breaks(value: str | None) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


@dataclass(slots=True)
class SessionPlanRecord:
    """单个计划文件记录。"""

    filename: str
    title: str
    content: str
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    status: PlanApprovalStatus = "draft"
    submitted_at: str | None = None
    approved_at: str | None = None
    rejected_at: str | None = None


class SessionTaskPlanStore:
    """当前 session 的 task / plan 存储。"""

    def __init__(self, session_root: Path):
        self.session_root = Path(session_root)
        self.sidecar_dir = self.session_root / ".aiasys/session"
        self.active_state_dir = self.sidecar_dir / ACTIVE_SESSION_STATE_DIR_NAME
        self.plans_dir = self.active_state_dir / "plans"
        self.metadata_path = self.session_root / METADATA_FILE_NAME

    def ensure_structure(self) -> None:
        self.active_state_dir.mkdir(parents=True, exist_ok=True)
        self.plans_dir.mkdir(parents=True, exist_ok=True)

    def _load_metadata(self) -> SessionMetadata:
        self.ensure_structure()
        if not self.metadata_path.exists():
            raise FileNotFoundError(f"session metadata 不存在: {self.metadata_path}")
        try:
            payload = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"读取 session metadata 失败: {self.metadata_path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"session metadata 格式无效: {self.metadata_path}")
        return SessionMetadata(**payload)

    def _save_metadata(self, metadata: SessionMetadata) -> None:
        self.ensure_structure()
        metadata.updated_at = _now_iso()
        self.metadata_path.write_text(
            json.dumps(metadata.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def read_tasks(self) -> list[TaskItem]:
        return list(self._load_metadata().tasks)

    def write_tasks(self, tasks: list[TaskItem], *, merge: bool = False) -> list[TaskItem]:
        metadata = self._load_metadata()
        current = {task.id: task for task in metadata.tasks}
        if merge:
            for task in tasks:
                current[task.id] = task
        else:
            current = {task.id: task for task in tasks}

        normalized = self._normalize_tasks(list(current.values()))
        metadata.tasks = normalized
        self._save_metadata(metadata)
        return normalized

    def update_task(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        content: str | None = None,
        dependencies: list[str] | None = None,
    ) -> list[TaskItem]:
        metadata = self._load_metadata()
        current = {task.id: task for task in metadata.tasks}
        task = current.get(task_id)
        if task is None:
            raise ValueError(f"task 不存在: {task_id}")
        if task.status in {"completed", "cancelled"} and status != task.status:
            raise ValueError(f"task 已结束，不能再次修改状态: {task_id}")

        now = _now_iso()
        if status is not None:
            task.status = status
            if status in {"completed", "cancelled"}:
                task.completed_at = task.completed_at or now
            else:
                task.completed_at = None
        if content is not None:
            task.content = content.strip()
        if dependencies is not None:
            task.dependencies = [
                dep.strip() for dep in dependencies if isinstance(dep, str) and dep.strip()
            ]
        task.updated_at = now
        current[task_id] = task
        normalized = self._normalize_tasks(list(current.values()))
        metadata.tasks = normalized
        self._save_metadata(metadata)
        return normalized

    def read_plan_state(self) -> SessionPlanState:
        return self._load_metadata().plan_state

    def write_plan_state(
        self,
        *,
        mode: PlanModeStatus | None = None,
        approval_status: PlanApprovalStatus | None = None,
        current_plan_file: str | None = None,
        pre_plan_permission_mode: str | None = None,
    ) -> SessionPlanState:
        metadata = self._load_metadata()
        plan_state = metadata.plan_state
        if mode is not None:
            plan_state.mode = mode
        if approval_status is not None:
            plan_state.approval_status = approval_status
        if current_plan_file is not None:
            plan_state.current_plan_file = current_plan_file
        if pre_plan_permission_mode is not None:
            plan_state.pre_plan_permission_mode = pre_plan_permission_mode
        plan_state.updated_at = _now_iso()
        metadata.plan_state = plan_state
        self._save_metadata(metadata)
        return plan_state

    def enter_plan_mode(self) -> SessionPlanState:
        return self.write_plan_state(mode="active", approval_status="draft")

    def build_task_summary_text(self) -> str:
        tasks = self.read_tasks()
        if not tasks:
            return ""

        lines = ["# 当前会话任务"]
        for task in tasks:
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]",
                "cancelled": "[-]",
            }.get(task.status, "[ ]")
            deps = f" (依赖: {', '.join(task.dependencies)})" if task.dependencies else ""
            lines.append(f"- {marker} {task.id}: {task.content}{deps} ({task.status})")
        return "\n".join(lines)

    def build_active_task_context(self) -> str | None:
        active = [task for task in self.read_tasks() if task.status in {"pending", "in_progress"}]
        if not active:
            return None

        lines = ["[你的活跃任务列表在上下文压缩后保留]"]
        for task in active:
            marker = "[>]" if task.status == "in_progress" else "[ ]"
            deps = f" (依赖: {', '.join(task.dependencies)})" if task.dependencies else ""
            lines.append(f"- {marker} {task.id}. {task.content}{deps} ({task.status})")
        return "\n".join(lines)

    def write_plan_file(
        self,
        *,
        filename: str,
        title: str,
        content: str,
        status: PlanApprovalStatus = "draft",
    ) -> SessionPlanRecord:
        safe_name = self._sanitize_plan_filename(filename)
        self.ensure_structure()
        plan_path = self.plans_dir / safe_name
        plan_path.write_text(_sanitize_line_breaks(content).strip() + "\n", encoding="utf-8")
        submitted_at = _now_iso() if status == "pending_approval" else None
        record = SessionPlanRecord(
            filename=safe_name,
            title=title.strip() or safe_name,
            content=_sanitize_line_breaks(content).strip(),
            status=status,
            submitted_at=submitted_at,
        )
        self._write_plan_metadata(record)
        if status == "pending_approval":
            self.write_plan_state(
                mode="inactive",
                approval_status="pending_approval",
                current_plan_file=record.filename,
            )
        else:
            self.write_plan_state(
                approval_status=status,
                current_plan_file=record.filename,
            )
        return record

    def load_plan_file(self, filename: str) -> SessionPlanRecord:
        safe_name = self._sanitize_plan_filename(filename)
        plan_path = self.plans_dir / safe_name
        if not plan_path.exists():
            raise FileNotFoundError(safe_name)
        content = plan_path.read_text(encoding="utf-8")
        meta = self._read_plan_metadata(safe_name)
        if meta is None:
            meta = SessionPlanRecord(filename=safe_name, title=safe_name, content=content.strip())
        else:
            meta.content = content.strip()
        return meta

    def approve_plan_file(self, filename: str) -> SessionPlanRecord:
        record = self.load_plan_file(filename)
        record.status = "approved"
        record.approved_at = _now_iso()
        record.updated_at = record.approved_at
        self._write_plan_metadata(record)
        self.write_plan_state(
            mode="inactive",
            approval_status="approved",
            current_plan_file=record.filename,
        )
        return record

    def reject_plan_file(self, filename: str) -> SessionPlanRecord:
        record = self.load_plan_file(filename)
        record.status = "rejected"
        record.rejected_at = _now_iso()
        record.updated_at = record.rejected_at
        self._write_plan_metadata(record)
        self.write_plan_state(
            mode="active",
            approval_status="rejected",
            current_plan_file=record.filename,
        )
        return record

    def list_plan_files(self) -> list[SessionPlanRecord]:
        self.ensure_structure()
        records: list[SessionPlanRecord] = []
        for plan_path in sorted(self.plans_dir.glob("*.md")):
            try:
                records.append(self.load_plan_file(plan_path.name))
            except Exception:
                logger.debug("读取 plan 文件失败: %s", plan_path, exc_info=True)
        return records

    def _sanitize_plan_filename(self, filename: str) -> str:
        safe_name = str(filename or "").strip().replace("\\", "/")
        safe_name = safe_name.split("/")[-1]
        if not safe_name.endswith(".md"):
            safe_name += ".md"
        if not safe_name or safe_name in {".md", "..md"}:
            raise ValueError("plan 文件名无效")
        if ".." in safe_name:
            raise ValueError("plan 文件名不能包含 ..")
        return safe_name

    def _plan_meta_path(self, filename: str) -> Path:
        return self.plans_dir / f"{filename}.json"

    def _read_plan_metadata(self, filename: str) -> SessionPlanRecord | None:
        meta_path = self._plan_meta_path(filename)
        if not meta_path.exists():
            return None
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            return SessionPlanRecord(
                filename=str(data.get("filename") or filename),
                title=str(data.get("title") or filename),
                content=str(data.get("content") or ""),
                created_at=str(data.get("created_at") or _now_iso()),
                updated_at=str(data.get("updated_at") or _now_iso()),
                status=str(data.get("status") or "draft"),
                submitted_at=data.get("submitted_at"),
                approved_at=data.get("approved_at"),
                rejected_at=data.get("rejected_at"),
            )
        except Exception:
            logger.warning("读取 plan 元数据失败: %s", meta_path, exc_info=True)
            return None

    def _write_plan_metadata(self, record: SessionPlanRecord) -> None:
        self.ensure_structure()
        meta_path = self._plan_meta_path(record.filename)
        meta_path.write_text(
            json.dumps(
                {
                    "filename": record.filename,
                    "title": record.title,
                    "content": record.content,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                    "status": record.status,
                    "submitted_at": record.submitted_at,
                    "approved_at": record.approved_at,
                    "rejected_at": record.rejected_at,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _normalize_tasks(self, tasks: list[TaskItem]) -> list[TaskItem]:
        deduped: dict[str, TaskItem] = {}
        for task in tasks:
            task.id = task.id.strip()
            task.content = task.content.strip()
            task.dependencies = [
                dep.strip() for dep in task.dependencies if isinstance(dep, str) and dep.strip()
            ]
            if not task.id:
                raise ValueError("task id 不能为空")
            if not task.content:
                raise ValueError(f"task 内容不能为空: {task.id}")
            if task.id in task.dependencies:
                raise ValueError(f"task 不能依赖自身: {task.id}")
            if task.status in {"completed", "cancelled"} and task.completed_at is None:
                task.completed_at = task.updated_at or _now_iso()
            if task.status not in {"completed", "cancelled"}:
                task.completed_at = None
            deduped[task.id] = task

        missing_dependencies: dict[str, list[str]] = {}
        for task in deduped.values():
            missing = [dep for dep in task.dependencies if dep not in deduped]
            if missing:
                missing_dependencies[task.id] = missing
        if missing_dependencies:
            detail = ", ".join(
                f"{task_id} -> {', '.join(missing)}"
                for task_id, missing in missing_dependencies.items()
            )
            raise ValueError(f"task 依赖不存在: {detail}")

        for task in deduped.values():
            if task.status != "in_progress":
                continue
            blocked = [dep for dep in task.dependencies if deduped[dep].status != "completed"]
            if blocked:
                raise ValueError(
                    f"task 依赖尚未完成，不能进入 in_progress: {task.id} "
                    f"(未完成依赖: {', '.join(blocked)})"
                )

        normalized = list(deduped.values())
        in_progress = [task for task in normalized if task.status == "in_progress"]
        if len(in_progress) <= 1:
            return self._sort_tasks(normalized)

        keep_first = in_progress[0].id
        for task in normalized:
            if task.status == "in_progress" and task.id != keep_first:
                task.status = "pending"
                task.updated_at = _now_iso()
                task.completed_at = None
        return self._sort_tasks(normalized)

    def _sort_tasks(self, tasks: list[TaskItem]) -> list[TaskItem]:
        status_order = {"in_progress": 0, "pending": 1, "completed": 2, "cancelled": 3}
        return sorted(
            tasks,
            key=lambda item: (
                status_order.get(item.status, 9),
                item.created_at,
                item.id,
            ),
        )

"""
任务工作区与对话读写投影服务
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

from app.core.config import WORKSPACE_DIR
from app.models.task_profile import (
    normalize_execution_policy,
)
from app.models.workspace import (
    ExecutionResourceGroup,
    OrphanConversationCleanupCandidate,
    OrphanConversationCleanupResponse,
    WorkspaceConversationSummary,
    WorkspaceDetailResponse,
    WorkspaceRuntimeBinding,
)
from app.services.agent_context_documents import (
    ensure_user_soul_file,
    ensure_workspace_project_profile_file,
)
from app.services.folder_import import copy_selected_files
from app.services.memory.resolver import get_workspace_memory_file_path
from app.services.memory.store import MemoryStore
from app.services.session import SessionManager
from app.services.session.config_projection import (
    ensure_workspace_layout,
)
from app.utils.ids import generate_conversation_id, generate_workspace_id
from app.utils.path_utils import as_system_path

_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_WORKSPACE_META_DIR = ".aiasys/workspace"
_WORKSPACE_META_FILE = "workspace.json"
_WORKSPACE_CONVERSATIONS_FILE = "conversations.json"


def _now_iso() -> str:
    return datetime.now().isoformat()


def _ensure_valid_id(value: str, field_name: str) -> None:
    if not value or not _ID_PATTERN.match(value):
        raise ValueError(f"无效的 {field_name}")


def _normalize_optional_model_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_getattr(obj: Any, attr: str, default: Any = None) -> Any:
    if obj is None:
        return default
    return getattr(obj, attr, default)


def _normalize_workspace_runtime_binding(value: Any) -> WorkspaceRuntimeBinding:
    raw: dict[str, Any]
    if isinstance(value, WorkspaceRuntimeBinding):
        raw = value.model_dump(mode="json")
    elif isinstance(value, dict):
        raw = dict(value)
    else:
        raw = {}

    # 兼容旧数据：从 sandbox_mode/env_id 提取信息到 resources
    sandbox_mode_raw = raw.get("sandbox_mode")
    sandbox_mode = (
        str(sandbox_mode_raw).strip().lower() if sandbox_mode_raw not in (None, "") else None
    )
    legacy_env_id = raw.get("env_id")
    legacy_env_id = str(legacy_env_id).strip() if legacy_env_id not in (None, "") else None

    env_vars = raw.get("env_vars")

    resources_raw = raw.get("resources")
    if not isinstance(resources_raw, dict):
        resources_raw = {}

    docker_resource_id = resources_raw.get("docker_resource_id") or None
    # Docker 沙盒与本地运行时互斥：优先 Docker，清空本地资源
    if docker_resource_id or sandbox_mode == "docker":
        resources = ExecutionResourceGroup(
            docker_resource_id=docker_resource_id,
        )
        return WorkspaceRuntimeBinding(
            env_vars=env_vars if isinstance(env_vars, dict) else None,
            resources=resources,
        )

    resources = ExecutionResourceGroup(
        python_env_id=resources_raw.get("python_env_id") or legacy_env_id or None,
        node_env_id=resources_raw.get("node_env_id") or None,
        docker_resource_id=None,
    )

    return WorkspaceRuntimeBinding(
        env_vars=env_vars if isinstance(env_vars, dict) else None,
        resources=resources,
    )


def _merge_workspace_runtime_binding(
    current: Any,
    patch: WorkspaceRuntimeBinding | dict[str, Any],
) -> WorkspaceRuntimeBinding:
    base = _normalize_workspace_runtime_binding(current).model_dump(mode="json")
    raw_patch = (
        patch.model_dump(mode="json", exclude_unset=True)
        if isinstance(patch, WorkspaceRuntimeBinding)
        else dict(patch)
    )
    # 只合并 env_vars 和 resources，sandbox_mode/env_id 由 resources 派生
    if "env_vars" in raw_patch:
        base["env_vars"] = raw_patch["env_vars"]
    if "resources" in raw_patch and isinstance(raw_patch["resources"], dict):
        base.setdefault("resources", {})
        for rkey in ("python_env_id", "node_env_id", "docker_resource_id"):
            if rkey in raw_patch["resources"]:
                base["resources"][rkey] = raw_patch["resources"][rkey]
    # 兼容旧 patch 直接传 sandbox_mode/env_id 的情况
    if "sandbox_mode" in raw_patch or "env_id" in raw_patch:
        base.setdefault("resources", {})
        if raw_patch.get("sandbox_mode") == "docker":
            base["resources"]["docker_resource_id"] = (
                base["resources"].get("docker_resource_id") or "docker-default"
            )
            base["resources"]["python_env_id"] = None
            base["resources"]["node_env_id"] = None
        if raw_patch.get("env_id"):
            base["resources"]["python_env_id"] = raw_patch["env_id"]
    return _normalize_workspace_runtime_binding(base)


class WorkspaceRegistryService:
    def __init__(
        self,
        base_dir: Path,
        session_manager: Optional[SessionManager] = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        os.makedirs(as_system_path(self.base_dir), exist_ok=True)
        self.session_manager = session_manager or SessionManager(self.base_dir)

    def _get_user_dir(self, user_id: str) -> Path:
        _ensure_valid_id(user_id, "user_id")
        return self.base_dir / user_id

    def _get_workspace_dir(self, user_id: str, workspace_id: str) -> Path:
        _ensure_valid_id(workspace_id, "workspace_id")
        return self._get_user_dir(user_id) / workspace_id

    def _generate_workspace_id(self, user_id: str) -> str:
        return generate_workspace_id(self._get_user_dir(user_id))

    def get_session_dir(self, user_id: str, session_id: str) -> Path:
        _ensure_valid_id(session_id, "session_id")
        return self._get_user_dir(user_id) / session_id

    def _get_workspace_meta_path(self, workspace_dir: Path) -> Path:
        return workspace_dir / _WORKSPACE_META_DIR / _WORKSPACE_META_FILE

    def _get_workspace_conversations_path(self, workspace_dir: Path) -> Path:
        return workspace_dir / _WORKSPACE_META_DIR / _WORKSPACE_CONVERSATIONS_FILE

    def _get_session_index_path(self, user_id: str, session_id: str) -> Path:
        return self._get_user_dir(user_id) / ".index" / f"{session_id}.json"

    def _write_session_index(self, user_id: str, session_id: str, workspace_id: str) -> None:
        path = self._get_session_index_path(user_id, session_id)
        self._write_json(path, {"workspace_id": workspace_id})

    def _read_session_index(self, user_id: str, session_id: str) -> str | None:
        path = self._get_session_index_path(user_id, session_id)
        payload = self._read_json(path, default={})
        if isinstance(payload, dict):
            return payload.get("workspace_id")
        return None

    def _delete_session_index(self, user_id: str, session_id: str) -> None:
        path = self._get_session_index_path(user_id, session_id)
        try:
            if os.path.exists(as_system_path(path)):
                os.unlink(as_system_path(path))
        except OSError as exc:
            logger.warning("删除会话索引失败: %s — %s", path, exc)

    def _ensure_workspace_layout(self, workspace_dir: Path) -> None:
        os.makedirs(as_system_path(workspace_dir), exist_ok=True)
        os.makedirs(as_system_path(workspace_dir / _WORKSPACE_META_DIR), exist_ok=True)

    def _ensure_workspace_context_files(
        self,
        workspace_dir: Path,
        *,
        title: str | None = None,
        description: str | None = None,
    ) -> None:
        """确保工作区长期上下文文件存在。"""
        ensure_workspace_project_profile_file(
            workspace_dir,
            title=title,
            description=description,
        )
        memory_path = get_workspace_memory_file_path(workspace_dir)
        if not os.path.exists(as_system_path(memory_path)):
            store = MemoryStore(memory_path)
            store.initialize()
            store.write_text(
                "## 长期目标\n- 这个工作区长期要推进什么\n\n"
                "## 关键术语\n- 需要统一口径的概念与命名\n\n"
                "## 稳定约束\n- 跨会话都应遵守的限制\n\n"
                "## 已确认决策\n- 已经定下、不需要重复讨论的结论\n"
            )

    def _read_json(self, path: Path, default: Any) -> Any:
        if not os.path.exists(as_system_path(path)):
            return default
        try:
            return json.loads(Path(as_system_path(path)).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read JSON from %s: %s", path, e)
            return default

    def _write_json(self, path: Path, payload: Any) -> None:
        import tempfile

        os.makedirs(as_system_path(path.parent), exist_ok=True)
        data = json.dumps(payload, indent=2, ensure_ascii=False)
        fd, temp_path = tempfile.mkstemp(dir=as_system_path(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(as_system_path(temp_path), as_system_path(path))
        except Exception:
            try:
                os.unlink(as_system_path(temp_path))
            except FileNotFoundError:
                pass
            raise

    def _is_workspace_dir(self, path: Path) -> bool:
        return os.path.exists(as_system_path(self._get_workspace_meta_path(path)))

    def _looks_like_session_dir(self, path: Path) -> bool:
        if os.path.exists(as_system_path(path / "metadata.json")):
            return True
        if os.path.exists(as_system_path(path / ".aiasys" / "session")):
            return True
        for dirname in ("workspace", "attachments", "artifacts", ".aiasys"):
            if os.path.exists(as_system_path(path / dirname)):
                return True
        return False

    def _is_reserved_user_dir(self, path: Path) -> bool:
        return path.name in {"global_workspace", ".index", ".system"}

    def _read_workspace_meta(self, user_id: str, workspace_id: str) -> dict[str, Any]:
        workspace_dir = self._get_workspace_dir(user_id, workspace_id)
        meta_path = self._get_workspace_meta_path(workspace_dir)
        if not os.path.exists(as_system_path(meta_path)):
            raise FileNotFoundError(f"工作区不存在: {workspace_id}")
        payload = self._read_json(meta_path, default={})
        if not isinstance(payload, dict) or not payload:
            raise FileNotFoundError(f"工作区不存在: {workspace_id}")
        return payload

    def _write_workspace_meta(
        self, user_id: str, workspace_id: str, payload: dict[str, Any]
    ) -> None:
        workspace_dir = self._get_workspace_dir(user_id, workspace_id)
        self._ensure_workspace_layout(workspace_dir)
        ensure_user_soul_file(self.base_dir, user_id)
        self._ensure_workspace_context_files(
            workspace_dir,
            title=payload.get("title"),
            description=payload.get("description"),
        )
        payload["_schema_version"] = payload.get("_schema_version", 1)
        self._write_json(self._get_workspace_meta_path(workspace_dir), payload)

    def _read_conversation_payloads(
        self,
        user_id: str,
        workspace_id: str,
    ) -> list[dict[str, Any]]:
        workspace_dir = self._get_workspace_dir(user_id, workspace_id)
        path = self._get_workspace_conversations_path(workspace_dir)
        payload = self._read_json(path, default={})
        if isinstance(payload, dict):
            items = payload.get("conversations") or []
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return []

    def _collect_bound_session_ids(self, user_id: str) -> set[str]:
        bound_session_ids: set[str] = set()
        user_dir = self._get_user_dir(user_id)
        for candidate in user_dir.iterdir():
            if not os.path.isdir(as_system_path(candidate)):
                continue
            if not self._is_workspace_dir(candidate):
                continue
            for item in self._read_conversation_payloads(user_id, candidate.name):
                if not isinstance(item, dict):
                    continue
                session_id = item.get("session_id") or item.get("conversation_id")
                if isinstance(session_id, str) and session_id:
                    bound_session_ids.add(session_id)
        return bound_session_ids

    def _write_conversation_payloads(
        self,
        user_id: str,
        workspace_id: str,
        payloads: list[dict[str, Any]],
    ) -> None:
        workspace_dir = self._get_workspace_dir(user_id, workspace_id)
        self._ensure_workspace_layout(workspace_dir)
        self._write_json(
            self._get_workspace_conversations_path(workspace_dir),
            {"_schema_version": 1, "conversations": payloads},
        )

    def _build_conversation_summary(
        self,
        user_id: str,
        workspace_id: str,
        payload: dict[str, Any],
    ) -> WorkspaceConversationSummary:
        session_id = str(payload.get("session_id") or payload.get("conversation_id") or "")
        if not session_id:
            raise ValueError("conversation payload 缺少 session_id")

        metadata = self.session_manager.get_session(session_id, user_id)
        execution_summary = self.session_manager.get_execution_summary(session_id, user_id)

        created_at = payload.get("created_at") or _safe_getattr(metadata, "created_at", _now_iso())
        updated_at = (
            _safe_getattr(metadata, "updated_at", None) or payload.get("updated_at") or created_at
        )
        return WorkspaceConversationSummary(
            workspace_id=workspace_id,
            conversation_id=str(payload.get("conversation_id") or session_id),
            session_id=session_id,
            title=str(_safe_getattr(metadata, "title", None) or payload.get("title") or "新对话"),
            created_at=str(created_at),
            updated_at=str(updated_at),
            execution_policy=normalize_execution_policy(
                _safe_getattr(metadata, "execution_policy", None)
                or payload.get("execution_policy"),
            ),
            message_count=int(_safe_getattr(metadata, "message_count", 0) or 0),
            status=str(_safe_getattr(metadata, "status", None) or payload.get("status") or "draft"),
            branched_from_conversation_id=payload.get("branched_from_conversation_id"),
            last_execution_status=execution_summary.get("last_execution_status"),
            last_execution_record_id=execution_summary.get("last_execution_record_id"),
            execution_record_count=int(execution_summary.get("execution_record_count") or 0),
            source=_safe_getattr(metadata, "source", None) or payload.get("source"),
            conversation_type=(
                _safe_getattr(metadata, "conversation_type", None)
                or payload.get("conversation_type")
            ),
            bound_host_session_id=(
                _safe_getattr(metadata, "bound_host_session_id", None)
                or payload.get("bound_host_session_id")
            ),
            auto_task_id=(
                _safe_getattr(metadata, "auto_task_id", None) or payload.get("auto_task_id")
            ),
            automation_continuation_id=(
                _safe_getattr(metadata, "automation_continuation_id", None)
                or payload.get("automation_continuation_id")
            ),
            automation_continuation_target_kind=(
                _safe_getattr(metadata, "automation_continuation_target_kind", None)
                or payload.get("automation_continuation_target_kind")
            ),
        )

    def _is_hidden_conversation_payload(
        self,
        user_id: str,
        payload: dict[str, Any],
    ) -> bool:
        session_id = str(payload.get("session_id") or payload.get("conversation_id") or "")
        if not session_id:
            return False
        metadata = self.session_manager.get_session(session_id, user_id)
        return bool(_safe_getattr(metadata, "exclude_from_user_history", False))

    def list_workspaces(
        self,
        user_id: str,
        *,
        include_conversations: bool = False,
        include_hidden_conversations: bool = False,
        summary_only: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[WorkspaceDetailResponse]:
        user_dir = self._get_user_dir(user_id)
        workspaces: list[WorkspaceDetailResponse] = []
        for candidate in user_dir.iterdir():
            if not os.path.isdir(as_system_path(candidate)) or os.path.islink(as_system_path(candidate)):
                continue
            meta_path = self._get_workspace_meta_path(candidate)
            if not os.path.exists(as_system_path(meta_path)):
                continue

            workspace_id = candidate.name
            try:
                if summary_only:
                    workspaces.append(
                        self._get_workspace_summary(
                            user_id,
                            workspace_id,
                            include_hidden_conversations=include_hidden_conversations,
                        )
                    )
                else:
                    workspaces.append(
                        self.get_workspace(
                            user_id,
                            workspace_id,
                            include_conversations=include_conversations,
                            include_hidden_conversations=include_hidden_conversations,
                        )
                    )
            except (FileNotFoundError, ValueError):
                continue

        workspaces.sort(key=lambda item: item.updated_at, reverse=True)

        if offset > 0:
            workspaces = workspaces[offset:]
        if limit is not None:
            workspaces = workspaces[:limit]
        return workspaces

    def get_workspace(
        self,
        user_id: str,
        workspace_id: str,
        *,
        include_conversations: bool = True,
        include_hidden_conversations: bool = False,
    ) -> WorkspaceDetailResponse:
        meta = self._read_workspace_meta(user_id, workspace_id)
        conversation_payloads = self._read_conversation_payloads(user_id, workspace_id)
        visible_payloads = (
            conversation_payloads
            if include_hidden_conversations
            else [
                payload
                for payload in conversation_payloads
                if not self._is_hidden_conversation_payload(user_id, payload)
            ]
        )
        current_conversation_id = meta.get("current_conversation_id")
        conversations: list[WorkspaceConversationSummary] = []
        current_conversation: WorkspaceConversationSummary | None = None

        if include_conversations:
            conversations: list[WorkspaceConversationSummary] = []
            for payload in visible_payloads:
                try:
                    conversations.append(
                        self._build_conversation_summary(user_id, workspace_id, payload)
                    )
                except ValueError:
                    continue
            conversations.sort(key=lambda item: item.updated_at, reverse=True)
            current_conversation = next(
                (item for item in conversations if item.conversation_id == current_conversation_id),
                None,
            )
            if current_conversation is None and conversations:
                current_conversation = conversations[0]
                current_conversation_id = current_conversation.conversation_id
        elif visible_payloads:
            current_payload = next(
                (
                    payload
                    for payload in visible_payloads
                    if payload.get("conversation_id") == current_conversation_id
                ),
                None,
            )
            if current_payload is not None:
                current_conversation = self._build_conversation_summary(
                    user_id,
                    workspace_id,
                    current_payload,
                )
                current_conversation_id = current_conversation.conversation_id
            elif len(visible_payloads) == 1:
                current_conversation = self._build_conversation_summary(
                    user_id,
                    workspace_id,
                    visible_payloads[0],
                )
                current_conversation_id = current_conversation.conversation_id
            else:
                fallback_conversations = [
                    self._build_conversation_summary(user_id, workspace_id, payload)
                    for payload in visible_payloads
                ]
                fallback_conversations.sort(key=lambda item: item.updated_at, reverse=True)
                if fallback_conversations:
                    current_conversation = fallback_conversations[0]
                    current_conversation_id = current_conversation.conversation_id

        raw_kind = str(meta.get("workspace_kind") or "").strip()
        workspace_kind = raw_kind if raw_kind in ("task", "claw") else "task"

        common = dict(
            workspace_id=workspace_id,
            title=str(meta.get("title") or "新任务"),
            description=(
                str(meta.get("description")).strip()
                if meta.get("description") not in (None, "")
                else None
            ),
            created_at=str(meta.get("created_at") or _now_iso()),
            updated_at=str(meta.get("updated_at") or meta.get("created_at") or _now_iso()),
            workspace_kind=workspace_kind,
            execution_policy=normalize_execution_policy(
                meta.get("execution_policy"),
            ),
            runtime_binding=_normalize_workspace_runtime_binding(
                meta.get("runtime_binding"),
            ),
            status=str(meta.get("status") or "active"),
            current_conversation_id=current_conversation_id,
            conversation_count=len(visible_payloads),
            current_conversation=current_conversation,
        )

        if not include_conversations:
            return WorkspaceDetailResponse(**common, conversations=[])
        return WorkspaceDetailResponse(**common, conversations=conversations)

    def _get_workspace_summary(
        self,
        user_id: str,
        workspace_id: str,
        *,
        include_hidden_conversations: bool = False,
    ) -> WorkspaceDetailResponse:
        """仅读取 workspace.json 和 conversations.json，不读取会话元数据。

        用于工作区列表的快速加载。对话摘要只包含 conversations.json 中已有的字段，
        不查询 session_manager 获取实时状态。
        """
        meta = self._read_workspace_meta(user_id, workspace_id)
        conversation_payloads = self._read_conversation_payloads(user_id, workspace_id)
        visible_payloads = (
            conversation_payloads
            if include_hidden_conversations
            else [
                payload
                for payload in conversation_payloads
                if not self._is_hidden_conversation_payload(user_id, payload)
            ]
        )

        current_conversation_id = meta.get("current_conversation_id")
        current_conversation: WorkspaceConversationSummary | None = None

        # 从 conversations.json 的 payload 直接构建轻量摘要，不读 session 元数据
        if visible_payloads:
            target_payload = None
            if current_conversation_id:
                target_payload = next(
                    (
                        payload
                        for payload in visible_payloads
                        if payload.get("conversation_id") == current_conversation_id
                    ),
                    None,
                )
            if target_payload is None:
                target_payload = max(
                    visible_payloads,
                    key=lambda p: p.get("updated_at") or p.get("created_at") or "",
                )
            current_conversation = self._build_conversation_summary_from_payload(
                workspace_id, target_payload
            )
            current_conversation_id = current_conversation.conversation_id

        raw_kind = str(meta.get("workspace_kind") or "").strip()
        workspace_kind = raw_kind if raw_kind in ("task", "claw") else "task"

        return WorkspaceDetailResponse(
            workspace_id=workspace_id,
            title=str(meta.get("title") or "新任务"),
            description=(
                str(meta.get("description")).strip()
                if meta.get("description") not in (None, "")
                else None
            ),
            created_at=str(meta.get("created_at") or _now_iso()),
            updated_at=str(meta.get("updated_at") or meta.get("created_at") or _now_iso()),
            workspace_kind=workspace_kind,
            execution_policy=normalize_execution_policy(meta.get("execution_policy")),
            runtime_binding=_normalize_workspace_runtime_binding(meta.get("runtime_binding")),
            status=str(meta.get("status") or "active"),
            current_conversation_id=current_conversation_id,
            conversation_count=len(visible_payloads),
            current_conversation=current_conversation,
            conversations=[],
        )

    def _build_conversation_summary_from_payload(
        self,
        workspace_id: str,
        payload: dict[str, Any],
    ) -> WorkspaceConversationSummary:
        """仅从 conversations.json payload 构建对话摘要，不查询 session_manager。"""
        conversation_id = str(payload.get("conversation_id") or payload.get("session_id") or "")
        session_id = str(payload.get("session_id") or payload.get("conversation_id") or "")
        if not conversation_id:
            logger.warning(
                "conversations.json payload 缺少 conversation_id 和 session_id: workspace=%s",
                workspace_id,
            )
            raise ValueError("conversation payload 缺少 conversation_id 和 session_id")
        created_at = payload.get("created_at") or _now_iso()
        updated_at = payload.get("updated_at") or created_at
        return WorkspaceConversationSummary(
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            session_id=session_id,
            title=str(payload.get("title") or "新对话"),
            created_at=str(created_at),
            updated_at=str(updated_at),
            execution_policy=normalize_execution_policy(payload.get("execution_policy")),
            message_count=int(payload.get("message_count") or 0),
            status=str(payload.get("status") or "draft"),
            branched_from_conversation_id=payload.get("branched_from_conversation_id"),
            last_execution_status=payload.get("last_execution_status"),
            last_execution_record_id=payload.get("last_execution_record_id"),
            execution_record_count=int(payload.get("execution_record_count") or 0),
            source=payload.get("source"),
            conversation_type=payload.get("conversation_type"),
            bound_host_session_id=payload.get("bound_host_session_id"),
            auto_task_id=payload.get("auto_task_id"),
            automation_continuation_id=payload.get("automation_continuation_id"),
            automation_continuation_target_kind=payload.get("automation_continuation_target_kind"),
        )

    def get_workspace_root(
        self,
        user_id: str,
        workspace_id: str,
    ) -> Path:
        """返回工作区根目录，并确保工作区存在。"""
        self._read_workspace_meta(user_id, workspace_id)
        return self._get_workspace_dir(user_id, workspace_id)

    def get_workspace_env_vars(
        self,
        user_id: str,
        workspace_id: str,
    ) -> dict[str, str]:
        workspace = self.get_workspace(
            user_id,
            workspace_id,
            include_conversations=False,
        )
        env_vars = workspace.runtime_binding.env_vars or {}
        return {str(key): str(value) for key, value in env_vars.items()}

    def set_workspace_env_vars(
        self,
        user_id: str,
        workspace_id: str,
        env_vars: dict[str, str],
    ) -> WorkspaceDetailResponse:
        workspace = self.get_workspace(
            user_id,
            workspace_id,
            include_conversations=False,
        )
        normalized = {str(key): str(value) for key, value in env_vars.items()}
        return self.update_workspace(
            user_id=user_id,
            workspace_id=workspace_id,
            runtime_binding=WorkspaceRuntimeBinding(
                env_vars=normalized,
                resources=workspace.runtime_binding.resources,
            ),
        )

    def set_workspace_env_var(
        self,
        user_id: str,
        workspace_id: str,
        name: str,
        value: str,
    ) -> WorkspaceDetailResponse:
        env_vars = self.get_workspace_env_vars(user_id, workspace_id)
        env_vars[str(name)] = str(value)
        return self.set_workspace_env_vars(user_id, workspace_id, env_vars)

    def delete_workspace_env_var(
        self,
        user_id: str,
        workspace_id: str,
        name: str,
    ) -> bool:
        env_vars = self.get_workspace_env_vars(user_id, workspace_id)
        if name not in env_vars:
            return False
        del env_vars[name]
        self.set_workspace_env_vars(user_id, workspace_id, env_vars)
        return True

    def find_workspace_id_by_session_id(
        self,
        user_id: str,
        session_id: str,
    ) -> str | None:
        _ensure_valid_id(user_id, "user_id")
        if not session_id:
            return None

        return self._read_session_index(user_id, session_id)

    def get_logical_workspace_root(
        self,
        user_id: str,
        session_id: str,
    ) -> Path:
        """返回当前 session 对应的逻辑工作区根目录。"""
        workspace_id = self.find_workspace_id_by_session_id(user_id, session_id)
        if workspace_id:
            return self._get_workspace_dir(user_id, workspace_id)
        return self.get_session_dir(user_id, session_id)

    def create_workspace(
        self,
        *,
        user_id: str,
        title: str,
        description: Optional[str] = None,
        workspace_kind: str = "task",
        execution_policy=None,
        initial_conversation_id: Optional[str] = None,
        initial_conversation_title: str = "新对话",
        workspace_id: Optional[str] = None,
        env_id: Optional[str] = None,
        sandbox_mode: Optional[str] = None,
        recovery_policy: Optional[str] = None,
        code_timeout: Optional[int] = None,
        runtime_binding: WorkspaceRuntimeBinding | dict[str, Any] | None = None,
        template_id: Optional[str] = None,
        install_capabilities: Optional[list[str]] = None,
        template_files: Optional[list[str]] = None,
        source_folder_path: Optional[str] = None,
        temp_upload_id: Optional[str] = None,
        import_files: Optional[list[str]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> WorkspaceDetailResponse:
        normalized_title = (title or "").strip()
        if not normalized_title:
            raise ValueError("工作区名称不能为空")

        normalized_description = (description or "").strip() or None
        normalized_execution_policy = normalize_execution_policy(execution_policy)
        resolved_workspace_id = workspace_id or self._generate_workspace_id(user_id)
        _ensure_valid_id(resolved_workspace_id, "workspace_id")
        workspace_dir = self._get_workspace_dir(user_id, resolved_workspace_id)
        if os.path.exists(as_system_path(self._get_workspace_meta_path(workspace_dir))):
            raise ValueError(f"工作区已存在: {resolved_workspace_id}")

        # 确保工作区目录存在，以便应用模板文件
        os.makedirs(as_system_path(workspace_dir), exist_ok=True)
        try:
            # 如果从本地文件夹导入，先复制用户选中的文件
            if source_folder_path or temp_upload_id:
                from pathlib import Path as _Path

                src_path: Path | None = None
                if temp_upload_id:
                    from app.services.folder_import import (
                        get_import_upload_dir,
                        remove_import_upload_dir,
                    )

                    src_path = get_import_upload_dir(temp_upload_id)
                    if src_path is None:
                        raise ValueError("上传会话已过期或不存在")
                else:
                    src_path = _Path(source_folder_path).expanduser().resolve()

                try:
                    if progress_callback:
                        progress_callback(0, "正在扫描文件夹...")
                    copy_selected_files(
                        src_path,
                        workspace_dir,
                        import_files or [],
                        progress_callback=progress_callback,
                    )
                    if progress_callback:
                        progress_callback(95, "正在初始化工作区...")
                finally:
                    if temp_upload_id:
                        remove_import_upload_dir(temp_upload_id)

            now = _now_iso()
            normalized_runtime_binding = _normalize_workspace_runtime_binding(
                runtime_binding
                if runtime_binding is not None
                else {
                    "env_id": env_id,
                    "sandbox_mode": sandbox_mode,
                }
            )

            # 提前解析模板（后续多处使用）
            resolved_template = None
            if template_id:
                template_id = template_id.strip()
                if template_id:
                    from app.core.templates import get_workspace_template

                    resolved_template = get_workspace_template(template_id, user_id)
                    if resolved_template is None:
                        logger.warning(
                            "请求的模板不存在，将创建空白工作区: template_id=%s",
                            template_id,
                        )

            # 应用模板预置文件（在写 meta 之前，避免默认 memory 覆盖模板 memory）
            resolved_initial_conversation_title = initial_conversation_title or "新对话"
            capability_warnings: list[str] = []
            if resolved_template is not None:
                from app.core.templates import apply_template_to_workspace

                install_results, _template_warnings = apply_template_to_workspace(
                    workspace_dir,
                    resolved_template,
                    user_id=user_id,
                    install_capabilities=install_capabilities,
                    template_files=template_files,
                )
                # 若用户未自定义对话标题，使用模板的默认对话标题
                if not initial_conversation_title or initial_conversation_title == "新对话":
                    resolved_initial_conversation_title = (
                        resolved_template.initial_conversation_title
                    )

                capability_warnings = [
                    f"能力安装失败（必需）: {r['capability_id']} — {r['message']}"
                    for r in install_results
                    if not r.get("success") and r.get("required")
                ]
                capability_warnings.extend(_template_warnings)

            # 默认安装 aiasys-tool-usage-skill（所有工作区通用工具指南）
            try:
                from app.capabilities import get_capability_manager

                mgr = get_capability_manager()
                default_skill_result = mgr.install(
                    "aiasys-tool-usage-skill",
                    workspace_dir,
                    scope="workspace",
                )
                if not default_skill_result.success:
                    logger.warning(
                        "默认 skill 安装失败: %s",
                        default_skill_result.message,
                    )
            except Exception:
                logger.warning("默认 skill 安装异常", exc_info=True)

            meta = {
                "workspace_id": resolved_workspace_id,
                "title": normalized_title,
                "description": normalized_description,
                "workspace_kind": workspace_kind,
                "execution_policy": normalized_execution_policy.model_dump(mode="json"),
                "status": "active",
                "created_at": now,
                "updated_at": now,
                "current_conversation_id": None,
                "preferred_model_id": None,
                "runtime_binding": normalized_runtime_binding.model_dump(mode="json"),
                "template_id": template_id,
            }
            self._write_workspace_meta(user_id, resolved_workspace_id, meta)
            self._write_conversation_payloads(user_id, resolved_workspace_id, [])

            # 解析执行资源组，按需初始化并绑定 Python / Node / Docker
            resolved_resources = ExecutionResourceGroup(
                python_env_id=normalized_runtime_binding.resources.python_env_id,
                node_env_id=normalized_runtime_binding.resources.node_env_id,
                docker_resource_id=normalized_runtime_binding.resources.docker_resource_id,
            )
            env_vars = normalized_runtime_binding.env_vars

            if resolved_resources.docker_resource_id:
                # Docker 沙盒模式：本地运行时资源清空
                resolved_resources.python_env_id = None
                resolved_resources.node_env_id = None
                normalized_runtime_binding = WorkspaceRuntimeBinding(
                    env_vars=env_vars,
                    resources=resolved_resources,
                )
            else:
                # Python 环境
                if resolved_resources.python_env_id:
                    from app.services.runtime_environment import RuntimeEnvironmentService

                    runtime_env_service = RuntimeEnvironmentService(self.base_dir, self)
                    py_env_id = resolved_resources.python_env_id

                    if py_env_id != "workspace-default":
                        runtime_env_service.inspect_env(
                            user_id,
                            resolved_workspace_id,
                            py_env_id,
                        )
                        inspected = runtime_env_service.bind_workspace_env(
                            user_id,
                            resolved_workspace_id,
                            py_env_id,
                        )
                        resolved_resources.python_env_id = inspected.env_id
                    else:
                        inspected, _ = runtime_env_service.ensure_uv_env(
                            user_id=user_id,
                            workspace_id=resolved_workspace_id,
                            env_id="workspace-default",
                            create_venv=True,
                            sync=True,
                        )
                        inspected = runtime_env_service.bind_workspace_env(
                            user_id,
                            resolved_workspace_id,
                            inspected.env_id,
                        )
                        resolved_resources.python_env_id = inspected.env_id

                # Node.js 环境
                if resolved_resources.node_env_id:
                    from app.services.node_runtime import NodeRuntimeService

                    node_service = NodeRuntimeService(self.base_dir, self)
                    node_env_id = resolved_resources.node_env_id

                    if node_env_id != "workspace-default":
                        inspected = node_service.bind_workspace_node_env(
                            user_id,
                            resolved_workspace_id,
                            node_env_id,
                        )
                        resolved_resources.node_env_id = inspected.env_id
                    else:
                        inspected = node_service.ensure_workspace_node_env(
                            user_id=user_id,
                            workspace_id=resolved_workspace_id,
                            env_id="workspace-default",
                            create_if_missing=True,
                        )
                        inspected = node_service.bind_workspace_node_env(
                            user_id,
                            resolved_workspace_id,
                            inspected.env_id,
                        )
                        resolved_resources.node_env_id = inspected.env_id

                normalized_runtime_binding = WorkspaceRuntimeBinding(
                    env_vars=env_vars,
                    resources=resolved_resources,
                )

            meta["runtime_binding"] = normalized_runtime_binding.model_dump(mode="json")
            self._write_workspace_meta(user_id, resolved_workspace_id, meta)

            self.create_conversation(
                user_id=user_id,
                workspace_id=resolved_workspace_id,
                conversation_id=initial_conversation_id,
                title=resolved_initial_conversation_title,
                branched_from_conversation_id=None,
                env_id=normalized_runtime_binding.env_id,
                sandbox_mode=normalized_runtime_binding.sandbox_mode,
                recovery_policy=recovery_policy,
                code_timeout=code_timeout,
            )
            response = self.get_workspace(
                user_id, resolved_workspace_id, include_conversations=True
            )
            response.warnings = capability_warnings
            return response
        except Exception:
            logger.warning(
                "创建工作区失败，清理目录: %s",
                workspace_dir,
                exc_info=True,
            )
            if os.path.exists(as_system_path(workspace_dir)):
                shutil.rmtree(as_system_path(workspace_dir), ignore_errors=True)
            raise

    def sync_conversation_task_profile(
        self,
        *,
        user_id: str,
        session_id: str,
    ) -> bool:
        """按 session_id 同步工作区中的对话任务配置摘要。"""
        workspace_id = self.find_workspace_id_by_session_id(user_id, session_id)
        if not workspace_id:
            return False

        metadata = self.session_manager.get_session(session_id, user_id)
        if metadata is None:
            return False

        payloads = self._read_conversation_payloads(user_id, workspace_id)
        updated = False
        now = _now_iso()
        for payload in payloads:
            payload_session_id = str(
                payload.get("session_id") or payload.get("conversation_id") or ""
            )
            if payload_session_id != session_id:
                continue
            payload["execution_policy"] = normalize_execution_policy(
                getattr(metadata, "execution_policy", None),
            ).model_dump(mode="json")
            payload["updated_at"] = now
            updated = True
            break

        if not updated:
            return False

        self._write_conversation_payloads(user_id, workspace_id, payloads)
        meta = self._read_workspace_meta(user_id, workspace_id)
        meta["updated_at"] = now
        self._write_workspace_meta(user_id, workspace_id, meta)
        return True

    def remove_conversation_by_session_id(
        self,
        *,
        user_id: str,
        session_id: str,
    ) -> bool:
        """按 session_id 移除工作区中的对话投影，并维护 current_conversation_id。"""
        if not session_id:
            return False

        indexed_workspace_id = self._read_session_index(user_id, session_id)
        if not indexed_workspace_id:
            return False
        return self._remove_conversation_by_session_id_in_workspace(
            user_id=user_id,
            workspace_id=indexed_workspace_id,
            session_id=session_id,
        )

    def _remove_conversation_by_session_id_in_workspace(
        self,
        *,
        user_id: str,
        workspace_id: str,
        session_id: str,
    ) -> bool:
        payloads = self._read_conversation_payloads(user_id, workspace_id)
        removed_payloads = [
            payload
            for payload in payloads
            if str(payload.get("session_id") or payload.get("conversation_id") or "") == session_id
        ]
        if not removed_payloads:
            # 反向索引指向了错误的 workspace（可能已 fork/移动），清理索引后返回
            self._delete_session_index(user_id, session_id)
            return False

        kept_payloads = [payload for payload in payloads if payload not in removed_payloads]
        meta = self._read_workspace_meta(user_id, workspace_id)
        removed_conversation_ids = {
            str(payload.get("conversation_id") or payload.get("session_id") or "")
            for payload in removed_payloads
        }
        current_conversation_id = str(meta.get("current_conversation_id") or "")
        if current_conversation_id in removed_conversation_ids:
            meta["current_conversation_id"] = (
                str(kept_payloads[0].get("conversation_id") or kept_payloads[0].get("session_id"))
                if kept_payloads
                else None
            )
        meta["updated_at"] = _now_iso()

        self._write_conversation_payloads(user_id, workspace_id, kept_payloads)
        self._write_workspace_meta(user_id, workspace_id, meta)

        # 清理绑定到该会话的 AutoTask
        try:
            from app.services.auto_tasks.engine import AutoTaskStore

            for task in AutoTaskStore.list_tasks(user_id, workspace_id):
                if getattr(task, "bind_session_id", None) == session_id:
                    task.bind_session_id = None
                    AutoTaskStore.put_task(user_id, workspace_id, task)
                    logger.info(
                        "会话删除后清理 AutoTask 绑定: task=%s session=%s",
                        task.task_id,
                        session_id,
                    )
        except Exception:
            logger.warning("清理会话绑定的 AutoTask 失败", exc_info=True)

        self._delete_session_index(user_id, session_id)
        return True

    def update_workspace(
        self,
        *,
        user_id: str,
        workspace_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        execution_policy=None,
        runtime_binding: WorkspaceRuntimeBinding | dict[str, Any] | None = None,
    ) -> WorkspaceDetailResponse:
        meta = self._read_workspace_meta(user_id, workspace_id)

        if title is not None:
            normalized_title = (title or "").strip()
            if not normalized_title:
                raise ValueError("工作区名称不能为空")
            meta["title"] = normalized_title

        if description is not None:
            meta["description"] = (description or "").strip() or None

        if execution_policy is not None:
            meta["execution_policy"] = normalize_execution_policy(
                execution_policy,
            ).model_dump(mode="json")

        if runtime_binding is not None:
            meta["runtime_binding"] = _merge_workspace_runtime_binding(
                meta.get("runtime_binding"),
                runtime_binding,
            ).model_dump(mode="json")

        meta["updated_at"] = _now_iso()
        self._write_workspace_meta(user_id, workspace_id, meta)
        return self.get_workspace(user_id, workspace_id, include_conversations=True)

    def get_workspace_preferred_model_id(
        self,
        user_id: str,
        workspace_id: str,
    ) -> str | None:
        meta = self._read_workspace_meta(user_id, workspace_id)
        return _normalize_optional_model_id(meta.get("preferred_model_id"))

    def update_workspace_preferred_model_id(
        self,
        user_id: str,
        workspace_id: str,
        preferred_model_id: str | None,
    ) -> str | None:
        meta = self._read_workspace_meta(user_id, workspace_id)
        meta["preferred_model_id"] = _normalize_optional_model_id(preferred_model_id)
        meta["updated_at"] = _now_iso()
        self._write_workspace_meta(user_id, workspace_id, meta)
        return _normalize_optional_model_id(meta.get("preferred_model_id"))

    def delete_workspace(
        self,
        user_id: str,
        workspace_id: str,
    ) -> None:
        from app.services.auto_tasks.engine import AutoTaskStore

        self._read_workspace_meta(user_id, workspace_id)
        AutoTaskStore.clear_workspace(user_id, workspace_id)

        workspace_dir = self._get_workspace_dir(user_id, workspace_id)
        payloads = self._read_conversation_payloads(user_id, workspace_id)

        for payload in payloads:
            session_id = payload.get("session_id") or payload.get("conversation_id")
            if not isinstance(session_id, str) or not session_id:
                continue

            # 停止活跃运行态（服务层自我保护，避免物理删除时仍有执行中任务）
            try:
                from app.services.agent import agent_service

                session_key = f"{user_id}/{session_id}"
                if getattr(agent_service, "_active_sessions", {}).get(session_key):
                    agent_service.interrupt_session(user_id, session_id)
            except Exception:
                logger.warning("中断会话运行态失败: %s/%s", user_id, session_id, exc_info=True)

            try:
                from app.agents.tools.local_ipython_box import LocalIPythonBox

                LocalIPythonBox.shutdown_kernel(session_id=session_id, user_id=user_id)
            except Exception:
                logger.warning("关闭本地运行态失败: %s/%s", user_id, session_id, exc_info=True)

            detached_path = self.session_manager.detach_session_for_deletion(
                session_id,
                user_id,
            )
            if detached_path is not None:
                self.session_manager.purge_detached_session(detached_path)

            # 清理反向索引
            self._delete_session_index(user_id, session_id)

        try:
            from app.core.database import (
                SubAgentConfigORM,
                SubAgentInstanceORM,
                DatabaseConnectorORM,
                WorkspaceResourceDefaultORM,
                db_session,
            )

            with db_session() as db:
                db.query(SubAgentConfigORM).filter(
                    SubAgentConfigORM.user_id == user_id,
                    SubAgentConfigORM.workspace_id == workspace_id,
                ).delete(synchronize_session=False)

                db.query(SubAgentInstanceORM).filter(
                    SubAgentInstanceORM.user_id == user_id,
                    SubAgentInstanceORM.workspace_id == workspace_id,
                ).delete(synchronize_session=False)

                db.query(DatabaseConnectorORM).filter(
                    DatabaseConnectorORM.workspace_id == workspace_id,
                    DatabaseConnectorORM.scope == "workspace",
                ).delete(synchronize_session=False)

                db.query(WorkspaceResourceDefaultORM).filter(
                    WorkspaceResourceDefaultORM.workspace_id == workspace_id,
                ).delete(synchronize_session=False)

                db.commit()
        except Exception:
            logger.warning(
                "删除工作区 %s 时 ORM 记录清理失败", workspace_id, exc_info=True
            )

        # 清理工作区注册的 Docker 容器，避免删除目录后容器仍运行且挂载路径失效
        self._cleanup_workspace_containers(user_id, workspace_id)

        # 清理 GraphRAG 服务缓存中指向本工作区的条目
        self._cleanup_workspace_graphrag_cache(workspace_dir)

        if os.path.exists(as_system_path(workspace_dir)):
            shutil.rmtree(as_system_path(workspace_dir))

    def _cleanup_workspace_containers(
        self,
        user_id: str,
        workspace_id: str,
    ) -> None:
        """删除工作区目录前，停止并移除已注册的 Docker 容器。

        容器清理失败不应阻断工作区删除，只记录 warning。
        """
        try:
            from app.services.container_resource import ContainerResourceService

            service = ContainerResourceService(self.workspace_root, workspace_registry=self)
            registry = service.list_workspace_containers(user_id, workspace_id)
            for container in registry.containers:
                try:
                    service.unregister_container(user_id, workspace_id, container.container_id)
                except Exception:
                    logger.warning(
                        "删除工作区 %s 时清理容器 %s 失败",
                        workspace_id,
                        container.container_id,
                        exc_info=True,
                    )
        except Exception:
            logger.warning("删除工作区 %s 时容器资源清理失败", workspace_id, exc_info=True)

    def _cleanup_workspace_graphrag_cache(self, workspace_dir: Path) -> None:
        """清理 GraphRAG 服务缓存中指向本工作区的条目。

        GraphRAG 服务实例按 (user_id, db_path) 缓存，删除工作区后这些
        缓存指向的 .db 文件已不存在，需移除避免脏读。
        """
        try:
            ws_prefix = str(workspace_dir.resolve())

            # routes 层缓存：key 为 (user_id, db_path_str)
            from app.graphrag.api import routes as graphrag_routes

            stale_keys = [
                key
                for key, _svc in getattr(
                    graphrag_routes, "_workspace_graphrag_services", {}
                ).items()
                if isinstance(key, tuple) and len(key) == 2 and str(key[1]).startswith(ws_prefix)
            ]
            for key in stale_keys:
                graphrag_routes._workspace_graphrag_services.pop(key, None)

            # agent 工具层缓存：key 为 (user_id, graph_id)，通过 graph_store.db_path 判定归属
            from app.agents.tools import graphrag_tool

            stale_tool_keys = []
            for key, svc in getattr(graphrag_tool, "_graphrag_services", {}).items():
                try:
                    db_path = str(getattr(getattr(svc, "graph_store", None), "_db_path", ""))
                    if db_path and db_path.startswith(ws_prefix):
                        stale_tool_keys.append(key)
                except Exception:
                    continue
            for key in stale_tool_keys:
                graphrag_tool._graphrag_services.pop(key, None)
        except Exception:
            logger.warning(
                "清理工作区 %s 的 GraphRAG 服务缓存失败",
                str(workspace_dir.name),
                exc_info=True,
            )

    def list_conversations(
        self,
        user_id: str,
        workspace_id: str,
        *,
        include_hidden_conversations: bool = False,
    ) -> list[WorkspaceConversationSummary]:
        self._read_workspace_meta(user_id, workspace_id)
        payloads = self._read_conversation_payloads(user_id, workspace_id)
        if not include_hidden_conversations:
            payloads = [
                payload
                for payload in payloads
                if not self._is_hidden_conversation_payload(user_id, payload)
            ]
        conversations: list[WorkspaceConversationSummary] = []
        for payload in payloads:
            try:
                conversations.append(
                    self._build_conversation_summary(user_id, workspace_id, payload)
                )
            except ValueError:
                continue
        conversations.sort(key=lambda item: item.updated_at, reverse=True)
        return conversations

    def create_conversation(
        self,
        *,
        user_id: str,
        workspace_id: str,
        title: str,
        execution_policy=None,
        branched_from_conversation_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        env_id: Optional[str] = None,
        sandbox_mode: Optional[str] = None,
        source: Optional[str] = None,
        conversation_type: Optional[str] = None,
        bound_host_session_id: Optional[str] = None,
        exclude_from_user_history: bool = False,
        auto_task_id: Optional[str] = None,
        automation_continuation_id: Optional[str] = None,
        automation_continuation_target_kind: Optional[str] = None,
        recovery_policy: Optional[str] = None,
        code_timeout: Optional[int] = None,
        make_current: bool = True,
    ) -> WorkspaceConversationSummary:
        meta = self._read_workspace_meta(user_id, workspace_id)
        resolved_conversation_id = conversation_id or generate_conversation_id(
            self._get_user_dir(user_id)
        )
        _ensure_valid_id(resolved_conversation_id, "conversation_id")

        existing = self._read_conversation_payloads(user_id, workspace_id)
        if any(item.get("conversation_id") == resolved_conversation_id for item in existing):
            raise ValueError(f"对话已存在: {resolved_conversation_id}")

        session_id = resolved_conversation_id
        resolved_execution_policy = normalize_execution_policy(
            execution_policy if execution_policy is not None else meta.get("execution_policy"),
        )
        inherited_runtime_binding = _normalize_workspace_runtime_binding(
            meta.get("runtime_binding"),
        )
        create_kwargs: dict[str, Any] = {
            "env_id": env_id if env_id is not None else inherited_runtime_binding.env_id,
            "sandbox_mode": (
                sandbox_mode if sandbox_mode is not None else inherited_runtime_binding.sandbox_mode
            ),
            "code_timeout": code_timeout,
            "execution_policy": resolved_execution_policy,
            "source": source,
            "conversation_type": conversation_type,
            "bound_host_session_id": bound_host_session_id,
            "exclude_from_user_history": exclude_from_user_history,
            "auto_task_id": auto_task_id,
            "automation_continuation_id": automation_continuation_id,
            "automation_continuation_target_kind": automation_continuation_target_kind,
        }
        if recovery_policy is not None:
            create_kwargs["recovery_policy"] = recovery_policy

        self.session_manager.create_session(
            session_id=session_id,
            user_id=user_id,
            title=title or "新对话",
            workspace_id=workspace_id,
            **create_kwargs,
        )
        ensure_workspace_layout(self.base_dir / user_id / session_id)
        if branched_from_conversation_id:
            payloads = self._read_conversation_payloads(user_id, workspace_id)
            source_payload = next(
                (
                    item
                    for item in payloads
                    if item.get("conversation_id") == branched_from_conversation_id
                ),
                None,
            )
            if source_payload is None:
                raise FileNotFoundError(f"来源对话不存在: {branched_from_conversation_id}")
            source_session_id = str(
                source_payload.get("session_id") or branched_from_conversation_id
            )
            fork_ok = self.session_manager.fork_session_history(
                source_session_id=source_session_id,
                target_session_id=session_id,
                user_id=user_id,
            )
            if not fork_ok:
                logger.warning(
                    "Fork 会话历史失败，创建空会话: source=%s target=%s",
                    source_session_id,
                    session_id,
                )
            # 数据库连接器已改为全局资源，fork 时不再克隆 session_attachments
        else:
            # 数据库连接器已改为全局资源，新建会话时不再按工作区挂载配置 attach
            pass

        now = _now_iso()
        payload = {
            "conversation_id": resolved_conversation_id,
            "session_id": session_id,
            "title": title or "新对话",
            "execution_policy": resolved_execution_policy.model_dump(mode="json"),
            "created_at": now,
            "updated_at": now,
            "branched_from_conversation_id": branched_from_conversation_id,
            "source": source,
            "conversation_type": conversation_type,
            "bound_host_session_id": bound_host_session_id,
            "auto_task_id": auto_task_id,
        }
        existing.append(payload)
        self._write_conversation_payloads(user_id, workspace_id, existing)

        # 维护 session_id -> workspace_id 反向索引
        self._write_session_index(user_id, session_id, workspace_id)

        if make_current:
            meta["current_conversation_id"] = resolved_conversation_id
        meta["updated_at"] = now
        self._write_workspace_meta(user_id, workspace_id, meta)

        return self._build_conversation_summary(user_id, workspace_id, payload)

    def get_conversation_runs(
        self,
        *,
        user_id: str,
        workspace_id: str,
        conversation_id: str,
        limit: int = 50,
    ) -> list:
        session_id = self.resolve_session_id_for_conversation(
            user_id=user_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
        )
        return self.session_manager.get_execution_records(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
        )

    def resolve_session_id_for_conversation(
        self,
        *,
        user_id: str,
        workspace_id: str,
        conversation_id: str,
    ) -> str:
        payloads = self._read_conversation_payloads(user_id, workspace_id)
        conversation = next(
            (item for item in payloads if item.get("conversation_id") == conversation_id),
            None,
        )
        if conversation is None:
            raise FileNotFoundError(f"对话不存在: {conversation_id}")

        return str(conversation.get("session_id") or conversation_id)

    def list_orphan_conversation_candidates(
        self,
        user_id: str,
    ) -> list[OrphanConversationCleanupCandidate]:
        user_dir = self._get_user_dir(user_id)
        bound_session_ids = self._collect_bound_session_ids(user_id)
        candidates: list[OrphanConversationCleanupCandidate] = []

        for candidate in user_dir.iterdir():
            if os.path.islink(as_system_path(candidate)) or not os.path.isdir(as_system_path(candidate)):
                continue
            if self._is_reserved_user_dir(candidate):
                continue
            if self._is_workspace_dir(candidate):
                continue

            session_id = candidate.name
            if session_id in bound_session_ids:
                continue
            if not self._looks_like_session_dir(candidate):
                continue

            reason = "未绑定到任何工作区的旧会话目录"
            if not os.path.exists(as_system_path(candidate / "metadata.json")):
                reason = "未绑定到任何工作区的残留会话目录"

            candidates.append(
                OrphanConversationCleanupCandidate(
                    session_id=session_id,
                    path=str(candidate),
                    reason=reason,
                )
            )

        candidates.sort(key=lambda item: item.session_id)
        return candidates

    def cleanup_orphan_conversations(
        self,
        user_id: str,
        *,
        dry_run: bool = True,
    ) -> OrphanConversationCleanupResponse:
        candidates = self.list_orphan_conversation_candidates(user_id)
        deleted_session_ids: list[str] = []

        if not dry_run:
            for item in candidates:
                target = self._get_user_dir(user_id) / item.session_id
                if os.path.islink(as_system_path(target)) or not os.path.isdir(as_system_path(target)):
                    continue
                if os.path.exists(as_system_path(target)):
                    shutil.rmtree(as_system_path(target))
                    deleted_session_ids.append(item.session_id)

        return OrphanConversationCleanupResponse(
            user_id=user_id,
            dry_run=dry_run,
            deleted_count=0 if dry_run else len(deleted_session_ids),
            deleted_session_ids=deleted_session_ids,
            candidates=candidates,
        )


_workspace_registry_service: WorkspaceRegistryService | None = None


def get_workspace_registry_service() -> WorkspaceRegistryService:
    global _workspace_registry_service
    if _workspace_registry_service is None:
        _workspace_registry_service = WorkspaceRegistryService(WORKSPACE_DIR)
    return _workspace_registry_service

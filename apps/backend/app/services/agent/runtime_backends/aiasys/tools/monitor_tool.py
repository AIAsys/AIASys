"""
Monitor 工具 —— Claude Code 风格后台 shell 监控。

LLM 主动调用 Monitor(command) 来在后台执行 shell 命令。
命令在后台异步运行，stdout/stderr 按行分割为 segment，持久化到 session 目录。
不阻塞 Host ReAct 循环：invoke 立即返回 tool_result，实际进程在后台 Task 中运行。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import tempfile
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.agents.tools.local_ipython_box import build_sanitized_kernel_env
from app.core.agent_tool import AiasysTool
from app.core.config import WORKSPACE_DIR
from app.core.tool_result import ToolResult
from app.services.history import current_session_id, current_user_id, current_workspace
from app.services.runtime.runtime_execution import (
    build_runtime_shell_env,
    resolve_runtime_execution_plan,
    wrap_shell_command_for_runtime,
)
from app.services.workspace_registry import get_workspace_registry_service

logger = logging.getLogger(__name__)


def _log_task_exception(task: asyncio.Task) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        exc = task.exception()
        if exc is not None:
            logger.error("后台任务异常: %s", exc, exc_info=True)


MONITORS_DIR_NAME = "monitors"
META_FILE_SUFFIX = ".meta.json"
SEGMENTS_FILE_SUFFIX = ".segments.jsonl"

_DANGEROUS_PATTERNS = [
    r"^\s*rm\s+-rf\s+/",
    r"^\s*mkfs\s+",
    r"^\s*dd\s+if=.*of=/dev/",
    r"^\s*:\(\)\{\s*:\|\:\&\s*\};\s*:",  # fork bomb
    r"^\s*chmod\s+777\s+/",
    r"^\s*>\s*/dev/",
    r"^\s*mv\s+/\s+",
]


def _is_dangerous_command(command: str) -> bool:
    """检查命令是否包含危险操作模式。"""
    import re

    for pattern in _DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return True
    return False


# ---------------------------------------------------------------------------
# MonitorSession —— 单个后台进程的状态
# ---------------------------------------------------------------------------


@dataclass
class MonitorSession:
    id: str
    command: str
    session_key: str
    out_file: Path
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    session_root: Path | None = None
    output_offset: int = 0
    _sse_offset: int = 0
    _line_buffer: str = ""
    _segment_index: int = 0
    _stdout_offset: int = 0
    _stderr_offset: int = 0
    status: str = "running"  # running | completed | error | killed
    exit_code: int | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    process: asyncio.subprocess.Process | None = None
    stdout_f: Any | None = None
    stderr_f: Any | None = None
    mode: str = "notify"  # notify | silent

    def read_new_output(self) -> str:
        """增量读取输出缓冲文件，更新 offset（供外部 poll API 使用）。"""
        if not self.out_file.exists():
            return ""
        try:
            with open(self.out_file, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self.output_offset)
                data = f.read()
                self.output_offset = f.tell()
                return data
        except Exception as exc:
            logger.warning("读取 monitor 输出文件失败: %s", exc)
            return ""

    def _read_sse_output(self) -> str:
        """增量读取输出缓冲文件，更新 _sse_offset（供内部 SSE 推送使用）。"""
        if not self.out_file.exists():
            return ""
        try:
            with open(self.out_file, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._sse_offset)
                data = f.read()
                self._sse_offset = f.tell()
                return data
        except Exception as exc:
            logger.warning("读取 monitor 输出文件失败: %s", exc)
            return ""

    def read_all_output(self) -> str:
        """读取全部输出（不更新 offset）。"""
        if not self.out_file.exists():
            return ""
        try:
            with open(self.out_file, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as exc:
            logger.warning("读取 monitor 输出文件失败: %s", exc)
            return ""


# ---------------------------------------------------------------------------
# MonitorService —— 全局注册表 + 持久化
# ---------------------------------------------------------------------------


class MonitorService:
    """管理所有活跃的后台 monitor 进程。

    每个 monitor 进程独占一个输出文件，通过 file offset 实现增量读取。
    输出按行分割为 segment，持久化到 {session_root}/monitors/ 目录。
    SSE 流通过 per-session asyncio.Queue 接收增量输出事件。
    """

    def __init__(self) -> None:
        self._monitors: dict[str, MonitorSession] = {}
        self._queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    # ---- 持久化辅助方法 ----------------------------------------------------

    @staticmethod
    def _get_monitors_dir(session_root: Path) -> Path:
        return session_root / MONITORS_DIR_NAME

    @staticmethod
    def _meta_path(session_root: Path, monitor_id: str) -> Path:
        return MonitorService._get_monitors_dir(session_root) / f"{monitor_id}{META_FILE_SUFFIX}"

    @staticmethod
    def _segments_path(session_root: Path, monitor_id: str) -> Path:
        return (
            MonitorService._get_monitors_dir(session_root) / f"{monitor_id}{SEGMENTS_FILE_SUFFIX}"
        )

    @staticmethod
    def _write_meta(session: MonitorSession) -> None:
        if session.session_root is None:
            return
        path = MonitorService._meta_path(session.session_root, session.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "id": session.id,
            "command": session.command,
            "session_key": session.session_key,
            "status": session.status,
            "exit_code": session.exit_code,
            "mode": session.mode,
            "created_at": session.created_at,
            "completed_at": session.completed_at,
        }
        try:
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.warning("写入 monitor meta 失败: %s", exc)

    def _append_segments(
        self, session: MonitorSession, lines: list[str], is_stderr: bool = False
    ) -> None:
        if session.session_root is None or not lines:
            return
        path = self._segments_path(session.session_root, session.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        records: list[str] = []
        for line in lines:
            record = {
                "index": session._segment_index,
                "timestamp": datetime.now().astimezone().isoformat(),
                "content": line,
                "is_stderr": is_stderr,
            }
            records.append(json.dumps(record, ensure_ascii=False))
            session._segment_index += 1
        if records:
            try:
                with path.open("a", encoding="utf-8") as f:
                    f.write("\n".join(records) + "\n")
            except Exception as exc:
                logger.warning("写入 monitor segments 失败: %s", exc)

    @staticmethod
    def _parse_session_key(session_key: str) -> tuple[str, str] | None:
        """从 session_key 解析 user_id 和 session_id。格式: user_id:session_id"""
        if ":" not in session_key:
            return None
        parts = session_key.split(":", 1)
        return parts[0], parts[1]

    # ---- 注册 / 注销 SSE Queue --------------------------------------------

    def register_queue(self, session_key: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """为指定 session 注册 SSE 推送队列。"""
        self._queues[session_key] = queue
        logger.debug("Monitor queue 注册: session_key=%s", session_key)

    def unregister_queue(self, session_key: str) -> None:
        """注销 SSE 推送队列。"""
        self._queues.pop(session_key, None)
        logger.debug("Monitor queue 注销: session_key=%s", session_key)

    def _emit(self, session_key: str, event: dict[str, Any]) -> None:
        """将事件推送到 session 对应的 SSE queue（非阻塞，满则丢弃）。"""
        queue = self._queues.get(session_key)
        if queue is None:
            return
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Monitor queue 已满，丢弃事件: session_key=%s", session_key)

    # ---- 启动 monitor ------------------------------------------------------

    async def spawn(
        self,
        command: str,
        session_key: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: int | None = None,
        mode: str = "notify",
    ) -> MonitorSession:
        """在后台启动一个 shell 命令，返回 MonitorSession（status=running）。

        Args:
            mode: "notify" 表示任务完成后通知 Agent 关注结果；
                  "silent" 表示纯后台运行，Agent 不主动介入。
        """
        monitor_id = f"mon_{uuid.uuid4().hex[:12]}"

        # 解析 session_key 获取 session_root
        session_root: Path | None = None
        parsed = self._parse_session_key(session_key)
        if parsed:
            user_id, session_id = parsed
            try:
                session_root = get_workspace_registry_service().get_session_dir(user_id, session_id)
            except Exception as exc:
                logger.warning("获取 session_dir 失败（将不持久化）: %s", exc)

        # 创建输出文件路径
        if session_root:
            monitors_dir = self._get_monitors_dir(session_root)
            monitors_dir.mkdir(parents=True, exist_ok=True)
            stdout_path = monitors_dir / f"{monitor_id}.stdout.log"
            stderr_path = monitors_dir / f"{monitor_id}.stderr.log"
            out_file = stdout_path
        else:
            tmp_dir = Path(tempfile.gettempdir()) / "aiasys"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            stdout_path = tmp_dir / f"aiasys-monitor-{monitor_id}.stdout.log"
            stderr_path = tmp_dir / f"aiasys-monitor-{monitor_id}.stderr.log"
            out_file = stdout_path

        session = MonitorSession(
            id=monitor_id,
            command=command,
            session_key=session_key,
            out_file=out_file,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            session_root=session_root,
            mode=mode,
        )

        # 持久化初始 meta
        self._write_meta(session)

        async with self._lock:
            self._monitors[monitor_id] = session

        # 危险命令检测
        if _is_dangerous_command(command):
            logger.warning("Monitor 拦截危险命令: session_key=%s command=%r", session_key, command)
            session = MonitorSession(
                id=monitor_id,
                command=command,
                session_key=session_key,
                out_file=Path(os.devnull),
                mode=mode,
                status="error",
                exit_code=-1,
                completed_at=time.time(),
            )
            return session

        # 启动后台进程，stdout/stderr 直接重定向到磁盘文件
        stdout_f = None
        stderr_f = None
        try:
            merged_env = dict(env) if env is not None else os.environ.copy()
            stdout_f = open(stdout_path, "wb")
            stderr_f = open(stderr_path, "wb")
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=stdout_f,
                stderr=stderr_f,
                cwd=cwd or os.getcwd(),
                env=merged_env,
            )
            session.process = process
            session.stdout_f = stdout_f
            session.stderr_f = stderr_f
        except Exception:
            if stdout_f:
                stdout_f.close()
            if stderr_f:
                stderr_f.close()
            session.status = "error"
            session.completed_at = time.time()
            logger.exception("启动 monitor 进程失败: %s", command)
            self._write_meta(session)
            self._emit(session_key, self._build_event(session))
            return session

        # 启动 wait_task 等待进程结束
        _wait_task = asyncio.create_task(
            self._wait_task(session, timeout_seconds),
            name=f"monitor-wait-{monitor_id}",
        )
        _wait_task.add_done_callback(_log_task_exception)

        logger.info(
            "Monitor 启动: id=%s session_key=%s command=%r",
            monitor_id,
            session_key,
            command,
        )
        # 立即推送一条初始事件
        self._emit(session_key, self._build_event(session))
        return session

    # ---- wait_task：等待进程结束 ------------------------------------------

    async def _wait_task(
        self,
        session: MonitorSession,
        timeout_seconds: int | None,
    ) -> None:
        """后台 Task：等待进程结束，同步最后一批 segments，更新状态。"""
        process = session.process
        if process is None:
            return

        try:
            if timeout_seconds is not None:
                try:
                    exit_code = await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    logger.info("Monitor 超时: id=%s", session.id)
                    try:
                        process.kill()
                    except Exception:
                        pass
                    exit_code = await process.wait()
                    session.status = "killed"
                    session.exit_code = -1
            else:
                exit_code = await process.wait()

            if session.status == "running":
                session.exit_code = exit_code
                session.status = "completed" if exit_code == 0 else "error"

        except Exception:
            logger.exception("Monitor wait_task 异常: id=%s", session.id)
            session.status = "error"
            session.exit_code = -1
        finally:
            session.completed_at = time.time()
            # 关闭文件句柄
            if session.stdout_f:
                try:
                    session.stdout_f.close()
                except Exception:
                    pass
                session.stdout_f = None
            if session.stderr_f:
                try:
                    session.stderr_f.close()
                except Exception:
                    pass
                session.stderr_f = None
            # 同步最后一批 segments（包括可能不完整的最后一行）
            self._sync_segments_from_logs(session, is_ended=True)
            # 更新最终 meta
            self._write_meta(session)
            # 推送最终事件
            self._emit(session.session_key, self._build_event(session))
            logger.info(
                "Monitor 结束: id=%s status=%s exit_code=%s",
                session.id,
                session.status,
                session.exit_code,
            )

    # ---- 按需读取 segments ----------------------------------------------------

    def _sync_segments_from_logs(self, session: MonitorSession, is_ended: bool = False) -> None:
        """从 stdout.log 和 stderr.log 读取新增内容，生成 segments 并持久化。"""
        if session.session_root is None:
            return
        has_new = False
        if session.stdout_path and self._read_log_segments(
            session, session.stdout_path, is_ended, is_stderr=False
        ):
            has_new = True
        if session.stderr_path and self._read_log_segments(
            session, session.stderr_path, is_ended, is_stderr=True
        ):
            has_new = True
        if has_new:
            self._emit(session.session_key, self._build_event(session))

    def _read_log_segments(
        self,
        session: MonitorSession,
        path: Path,
        is_ended: bool,
        is_stderr: bool,
    ) -> bool:
        """读取日志文件的新增内容，生成 segments 并持久化。返回是否有新 segments。"""
        if not path or not path.exists():
            return False

        offset = session._stderr_offset if is_stderr else session._stdout_offset
        try:
            with open(path, "rb") as f:
                f.seek(offset)
                raw = f.read()
        except Exception as exc:
            logger.warning("读取 monitor 输出文件失败: %s", exc)
            return False

        if not raw:
            return False

        data = raw.decode("utf-8", errors="replace")

        # 如果进程还在运行，只处理完整行（以 \n 结尾）
        if not is_ended and not data.endswith("\n"):
            last_newline = data.rfind("\n")
            if last_newline == -1:
                return False
            complete_data = data[: last_newline + 1]
            new_offset = offset + len(complete_data.encode("utf-8"))
        else:
            complete_data = data
            if is_ended and complete_data and not complete_data.endswith("\n"):
                complete_data += "\n"
            new_offset = offset + len(raw)

        lines = complete_data.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]

        if lines:
            self._append_segments(session, lines, is_stderr=is_stderr)
            if is_stderr:
                session._stderr_offset = new_offset
            else:
                session._stdout_offset = new_offset
            return True
        return False

    def _build_event(self, session: MonitorSession) -> dict[str, Any]:
        """构造 SSE event dict。"""
        return {
            "type": "monitor.output",
            "monitor_id": session.id,
            "command": session.command,
            "status": session.status,
            "exit_code": session.exit_code,
            "mode": session.mode,
            "notify_completed": (
                session.mode == "notify" and session.status in ("completed", "error", "killed")
            ),
            "output": session._read_sse_output(),
            "output_offset": session._sse_offset,
            "created_at": session.created_at,
            "completed_at": session.completed_at,
        }

    # ---- 查询 / 控制 -------------------------------------------------------

    def get(self, monitor_id: str) -> MonitorSession | None:
        return self._monitors.get(monitor_id)

    def list_by_session(self, session_key: str) -> list[MonitorSession]:
        return [m for m in self._monitors.values() if m.session_key == session_key]

    def list_all(self) -> list[MonitorSession]:
        return list(self._monitors.values())

    def list_global_monitors(self, user_id: str) -> list[dict[str, Any]]:
        """列出指定用户所有 session 的 monitor（内存 + 持久化）。"""
        from app.services.workspace_registry import get_workspace_registry_service

        registry = get_workspace_registry_service()
        user_dir = Path(str(WORKSPACE_DIR)) / user_id

        # 收集内存中活跃的 monitor（按 session_key 分组）
        active_by_session: dict[str, dict[str, MonitorSession]] = {}
        for session in self._monitors.values():
            parsed = self._parse_session_key(session.session_key)
            if parsed and parsed[0] == user_id:
                active_by_session.setdefault(session.session_key, {})[session.id] = session

        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        # 扫描用户目录下所有 session 的 monitors 持久化
        if user_dir.exists():
            for candidate in user_dir.iterdir():
                if not candidate.is_dir() or candidate.name.startswith("."):
                    continue
                session_id = candidate.name
                monitors_dir = self._get_monitors_dir(candidate)
                if not monitors_dir.exists():
                    continue

                session_key = f"{user_id}:{session_id}"
                workspace_id = registry.find_workspace_id_by_session_id(user_id, session_id)
                workspace_title = ""
                if workspace_id:
                    try:
                        ws = registry.get_workspace(
                            user_id, workspace_id, include_conversations=False
                        )
                        workspace_title = ws.title or ""
                    except Exception:
                        pass

                active_map = active_by_session.get(session_key, {})

                for meta_path in sorted(
                    monitors_dir.glob(f"*{META_FILE_SUFFIX}"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                ):
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                        mid = meta.get("id")
                        if not mid or mid in seen_ids:
                            continue
                        seen_ids.add(mid)

                        # 内存状态优先（更实时）
                        if mid in active_map:
                            am = active_map[mid]
                            meta = {
                                "id": am.id,
                                "command": am.command,
                                "status": am.status,
                                "exit_code": am.exit_code,
                                "mode": am.mode,
                                "created_at": am.created_at,
                                "completed_at": am.completed_at,
                            }

                        results.append(
                            {
                                "id": meta.get("id", mid),
                                "command": meta.get("command", ""),
                                "status": meta.get("status", "unknown"),
                                "exit_code": meta.get("exit_code"),
                                "mode": meta.get("mode", "notify"),
                                "created_at": meta.get("created_at", 0),
                                "completed_at": meta.get("completed_at"),
                                "session_id": session_id,
                                "session_key": session_key,
                                "workspace_id": workspace_id or "",
                                "workspace_title": workspace_title,
                            }
                        )
                    except Exception:
                        continue

        # 补充内存中有但持久化已被清理的 monitor（极少见）
        for session_key, active_map in active_by_session.items():
            for mid, session in active_map.items():
                if mid not in seen_ids:
                    parsed = self._parse_session_key(session_key)
                    session_id = parsed[1] if parsed else ""
                    workspace_id = (
                        registry.find_workspace_id_by_session_id(user_id, session_id)
                        if session_id
                        else None
                    )
                    workspace_title = ""
                    if workspace_id:
                        try:
                            ws = registry.get_workspace(
                                user_id, workspace_id, include_conversations=False
                            )
                            workspace_title = ws.title or ""
                        except Exception:
                            pass
                    results.append(
                        {
                            "id": session.id,
                            "command": session.command,
                            "status": session.status,
                            "exit_code": session.exit_code,
                            "mode": session.mode,
                            "created_at": session.created_at,
                            "completed_at": session.completed_at,
                            "session_id": session_id,
                            "session_key": session_key,
                            "workspace_id": workspace_id or "",
                            "workspace_title": workspace_title,
                        }
                    )

        results.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return results

    async def kill(self, monitor_id: str) -> MonitorSession | None:
        """终止指定 monitor 进程。"""
        session = self._monitors.get(monitor_id)
        if session is None:
            return None
        if session.status != "running":
            return session
        if session.process is not None and session.process.returncode is None:
            try:
                session.process.kill()
            except Exception:
                pass
        session.status = "killed"
        session.exit_code = -1
        session.completed_at = time.time()
        self._sync_segments_from_logs(session, is_ended=True)
        self._write_meta(session)
        self._emit(session.session_key, self._build_event(session))
        return session

    def set_mode(self, monitor_id: str, mode: str) -> MonitorSession | None:
        """修改指定 monitor 的模式（notify/silent）。不重启进程。"""
        if mode not in ("notify", "silent"):
            return None
        session = self._monitors.get(monitor_id)
        if session is None:
            # 尝试从持久化加载并修改
            return None
        session.mode = mode
        self._write_meta(session)
        self._emit(session.session_key, self._build_event(session))
        return session

    def set_mode_by_session(self, session_key: str, monitor_id: str, mode: str) -> bool:
        """根据 session_key 修改 monitor 模式。支持内存和持久化中的 monitor。"""
        if mode not in ("notify", "silent"):
            return False

        session = self._monitors.get(monitor_id)
        if session is not None:
            if session.session_key != session_key:
                return False
            session.mode = mode
            self._write_meta(session)
            self._emit(session.session_key, self._build_event(session))
            return True

        # 从持久化修改
        parsed = self._parse_session_key(session_key)
        if parsed is None:
            return False
        user_id, session_id = parsed
        try:
            session_root = get_workspace_registry_service().get_session_dir(user_id, session_id)
        except Exception:
            return False

        meta_path = self._meta_path(session_root, monitor_id)
        if not meta_path.exists():
            return False

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["mode"] = mode
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception as exc:
            logger.warning("修改 monitor mode 失败: %s", exc)
            return False

    async def cleanup_session(self, session_key: str) -> None:
        """清理指定 session 的所有活跃 monitor 进程（不删除持久化文件）。"""
        to_remove: list[str] = []
        for monitor_id, session in list(self._monitors.items()):
            if session.session_key == session_key:
                if session.status == "running" and session.process is not None:
                    try:
                        session.process.kill()
                    except Exception:
                        pass
                self._sync_segments_from_logs(session, is_ended=True)
                session.completed_at = time.time()
                self._write_meta(session)
                # 保留持久化文件，只删除临时日志文件
                for log_path in (session.stdout_path, session.stderr_path):
                    if log_path and log_path.exists():
                        try:
                            log_path.unlink()
                        except Exception:
                            pass
                to_remove.append(monitor_id)

        for monitor_id in to_remove:
            self._monitors.pop(monitor_id, None)

        logger.info(
            "Monitor cleanup_session: session_key=%s removed=%d", session_key, len(to_remove)
        )

    async def cleanup_all(self) -> None:
        """清理所有 monitor（用于服务关闭）。"""
        for session in list(self._monitors.values()):
            if session.status == "running" and session.process is not None:
                try:
                    session.process.kill()
                except Exception:
                    pass
            self._sync_segments_from_logs(session, is_ended=True)
            session.completed_at = time.time()
            self._write_meta(session)
            for log_path in (session.stdout_path, session.stderr_path):
                if log_path and log_path.exists():
                    try:
                        log_path.unlink()
                    except Exception:
                        pass
        self._monitors.clear()
        self._queues.clear()

    async def delete(self, monitor_id: str) -> bool:
        """删除指定 monitor 的持久化文件并从内存中移除。"""
        session = self._monitors.get(monitor_id)
        if session is not None:
            # 如果还在运行，先杀掉
            if session.status == "running" and session.process is not None:
                try:
                    session.process.kill()
                except Exception:
                    pass
            # 清理文件
            if session.session_root is not None:
                for suffix in (
                    META_FILE_SUFFIX,
                    SEGMENTS_FILE_SUFFIX,
                    ".stdout.log",
                    ".stderr.log",
                ):
                    path = self._get_monitors_dir(session.session_root) / f"{monitor_id}{suffix}"
                    if path.exists():
                        try:
                            path.unlink()
                        except Exception:
                            pass
            self._monitors.pop(monitor_id, None)
            return True

        # 如果不在内存中，尝试从持久化目录删除
        # 需要找到对应的 session_key，这里通过扫描所有 session 来定位
        # 更简单的做法：由调用方提供 session_key
        return False

    async def delete_by_session(self, session_key: str, monitor_id: str) -> bool:
        """根据 session_key 删除 monitor（包括持久化文件）。"""
        session = self._monitors.get(monitor_id)
        if session is not None:
            if session.session_key != session_key:
                return False
            if session.status == "running" and session.process is not None:
                try:
                    session.process.kill()
                except Exception:
                    pass
            if session.session_root is not None:
                for suffix in (
                    META_FILE_SUFFIX,
                    SEGMENTS_FILE_SUFFIX,
                    ".stdout.log",
                    ".stderr.log",
                ):
                    path = self._get_monitors_dir(session.session_root) / f"{monitor_id}{suffix}"
                    if path.exists():
                        try:
                            path.unlink()
                        except Exception:
                            pass
            self._monitors.pop(monitor_id, None)
            return True

        # 从持久化中删除
        parsed = self._parse_session_key(session_key)
        if parsed is None:
            return False
        user_id, session_id = parsed
        try:
            session_root = get_workspace_registry_service().get_session_dir(user_id, session_id)
        except Exception:
            return False

        deleted = False
        for suffix in (META_FILE_SUFFIX, SEGMENTS_FILE_SUFFIX, ".stdout.log", ".stderr.log"):
            path = self._get_monitors_dir(session_root) / f"{monitor_id}{suffix}"
            if path.exists():
                try:
                    path.unlink()
                    deleted = True
                except Exception:
                    pass
        return deleted

    # ---- 从持久化读取（供 API 使用） ----------------------------------------

    def list_persistent_monitors(self, session_key: str) -> list[dict[str, Any]]:
        """从持久化目录读取指定 session 的所有 monitor meta（包含已结束的）。"""
        parsed = self._parse_session_key(session_key)
        if parsed is None:
            return []
        user_id, session_id = parsed
        try:
            session_root = get_workspace_registry_service().get_session_dir(user_id, session_id)
        except Exception:
            return []

        monitors_dir = self._get_monitors_dir(session_root)
        if not monitors_dir.exists():
            return []

        results: list[dict[str, Any]] = []
        for path in sorted(monitors_dir.glob(f"*{META_FILE_SUFFIX}")):
            try:
                raw = path.read_text(encoding="utf-8")
                meta = json.loads(raw)
                if isinstance(meta, dict):
                    results.append(meta)
            except Exception:
                continue
        return results

    def get_persistent_monitor_detail(
        self, session_key: str, monitor_id: str
    ) -> dict[str, Any] | None:
        """从持久化读取单个 monitor 的 meta 和全部 segments。"""
        parsed = self._parse_session_key(session_key)
        if parsed is None:
            return None
        user_id, session_id = parsed
        try:
            session_root = get_workspace_registry_service().get_session_dir(user_id, session_id)
        except Exception:
            return None

        meta_path = self._meta_path(session_root, monitor_id)
        segments_path = self._segments_path(session_root, monitor_id)

        if not meta_path.exists():
            return None

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None

        segments: list[dict[str, Any]] = []
        if segments_path.exists():
            try:
                for line in segments_path.read_text(encoding="utf-8").strip().splitlines():
                    line = line.strip()
                    if line:
                        seg = json.loads(line)
                        if isinstance(seg, dict):
                            segments.append(seg)
            except Exception:
                pass

        return {"info": meta, "segments": segments}

    def get_persistent_monitor_segments(
        self,
        session_key: str,
        monitor_id: str,
        since_index: int = 0,
    ) -> list[dict[str, Any]]:
        """从持久化读取单个 monitor 的增量 segments。"""
        parsed = self._parse_session_key(session_key)
        if parsed is None:
            return []
        user_id, session_id = parsed
        try:
            session_root = get_workspace_registry_service().get_session_dir(user_id, session_id)
        except Exception:
            return []

        segments_path = self._segments_path(session_root, monitor_id)
        if not segments_path.exists():
            return []

        results: list[dict[str, Any]] = []
        try:
            for line in segments_path.read_text(encoding="utf-8").strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                seg = json.loads(line)
                if isinstance(seg, dict) and seg.get("index", 0) >= since_index:
                    results.append(seg)
        except Exception:
            pass
        return results


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_monitor_service: MonitorService | None = None


def get_monitor_service() -> MonitorService:
    global _monitor_service
    if _monitor_service is None:
        _monitor_service = MonitorService()
    return _monitor_service


# ---------------------------------------------------------------------------
# Monitor 工具 —— LLM 可调用的 tool
# ---------------------------------------------------------------------------


def _resolve_monitor_session_ctx(ctx: dict[str, Any]) -> tuple[str, str, str]:
    """从上下文中解析 user_id、session_id 和 session_key。"""
    user_id = str(ctx.get("user_id") or current_user_id.get() or "")
    session_id = str(ctx.get("session_id") or current_session_id.get() or "")
    session_key = f"{user_id}:{session_id}"
    return user_id, session_id, session_key


class SpawnMonitorTool(AiasysTool):
    """在后台异步启动 shell 命令并实时推送输出。

    立即返回 tool_result（包含 monitor_id），不阻塞 ReAct 循环。
    命令在后台 asyncio.Task 中运行，stdout 按行分割为 segment 持久化。
    前端可通过"监听"Tab 查看实时输出流。
    """

    name = "SpawnMonitor"
    description = (
        "在后台异步启动 shell 命令，立即返回 monitor_id。"
        "支持管道、重定向等 shell 特性。可通过 mode 参数指定 notify（默认）"
        "或 silent 模式。notify 模式下任务完成后 Agent 会自动关注结果，"
        "silent 模式下任务静默运行不打扰 Agent。"
        "如需查询输出、终止或删除，使用 ManageMonitor 工具。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要在后台执行的 shell 命令。支持管道、重定向等 shell 特性。",
            },
            "description": {
                "type": "string",
                "description": "命令用途简述，用于 UI 展示和日志",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "命令超时时间（秒），默认不超时",
            },
            "mode": {
                "type": "string",
                "enum": ["notify", "silent"],
                "description": (
                    "任务模式。notify（默认）：任务完成后通知 Agent 关注结果；"
                    "silent：纯后台静默运行，Agent 不主动介入"
                ),
            },
        },
        "required": ["command"],
    }

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        ctx = ctx or {}
        command = str(kwargs.get("command") or "").strip()
        description = str(kwargs.get("description") or "").strip()
        timeout = kwargs.get("timeout_seconds")
        if timeout is not None:
            try:
                timeout = int(timeout)
            except (ValueError, TypeError):
                timeout = None
        mode = str(kwargs.get("mode") or "notify").strip().lower()
        if mode not in ("notify", "silent"):
            mode = "notify"

        if not command:
            return ToolResult(content="缺少 command 参数", is_error=True)
        if _is_dangerous_command(command):
            return ToolResult(
                content=f"命令包含危险操作，已被拦截: `{command[:80]}`",
                is_error=True,
            )

        user_id, session_id, session_key = _resolve_monitor_session_ctx(ctx)
        if not user_id or not session_id:
            return ToolResult(content="无法确定当前会话上下文", is_error=True)

        workspace = ctx.get("workspace") or current_workspace.get()
        workspace_path = Path(str(workspace)) if workspace else None
        try:
            plan = resolve_runtime_execution_plan(workspace=workspace_path)
            command, runtime_cwd = wrap_shell_command_for_runtime(
                command,
                plan=plan,
            )
        except Exception as exc:
            return ToolResult(content=f"解析运行环境失败: {exc}", is_error=True)
        cwd = str(runtime_cwd) if runtime_cwd else None
        runtime_env = build_runtime_shell_env(
            build_sanitized_kernel_env(),
            plan=plan,
        )

        service = get_monitor_service()
        session = await service.spawn(
            command=command,
            session_key=session_key,
            cwd=cwd,
            env=runtime_env,
            timeout_seconds=timeout,
            mode=mode,
        )

        if mode == "silent":
            brief = (
                f"已启动后台静默任务 [{session.id}]\n"
                f"命令: {command}\n"
                f"状态: {session.status}\n"
                "该任务在后台静默运行，我不会主动介入。"
                "用户可在监听面板查看进度，需要时可用 ManageMonitor 查询输出。"
            )
        else:
            brief = (
                f"已启动后台监听 [{session.id}]\n"
                f"命令: {command}\n"
                f"状态: {session.status}\n"
                "任务完成后我会主动关注结果。"
                "如需立即查看输出，可用 ManageMonitor({'action':'poll','monitor_id':'"
                f"{session.id}"
                "'}) 查询。"
            )
        if description:
            brief = f"描述: {description}\n{brief}"

        return ToolResult(
            content=brief,
            artifacts=[
                {
                    "monitor_id": session.id,
                    "command": command,
                    "description": description,
                    "status": session.status,
                    "mode": session.mode,
                    "output_file": str(session.out_file),
                }
            ],
        )


class ManageMonitorTool(AiasysTool):
    """管理已有的后台 monitor：查询输出、终止进程、删除记录。"""

    name = "ManageMonitor"
    description = "管理已有的后台 monitor 进程。支持 poll（查询增量输出）、kill（终止进程）、delete（删除记录）。"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["poll", "kill", "delete"],
                "description": "操作类型：poll 查询增量输出，kill 终止进程，delete 删除 monitor 及持久化文件",
            },
            "monitor_id": {
                "type": "string",
                "description": "monitor ID",
            },
        },
        "required": ["action", "monitor_id"],
    }

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        ctx = ctx or {}
        action = str(kwargs.get("action") or "").strip().lower()
        monitor_id = str(kwargs.get("monitor_id") or "").strip()

        if not action:
            return ToolResult(content="缺少 action 参数（poll/kill/delete）", is_error=True)
        if not monitor_id:
            return ToolResult(content="缺少 monitor_id 参数", is_error=True)

        user_id, session_id, session_key = _resolve_monitor_session_ctx(ctx)
        if not user_id or not session_id:
            return ToolResult(content="无法确定当前会话上下文", is_error=True)

        service = get_monitor_service()
        session = service.get(monitor_id)

        if action == "poll":
            if session is None:
                return ToolResult(content=f"Monitor {monitor_id} 不存在", is_error=True)
            if session.session_key != session_key:
                return ToolResult(content="无权查询该 monitor", is_error=True)

            new_output = session.read_new_output()
            lines = new_output.splitlines() if new_output else []

            brief_lines = [
                f"Monitor [{monitor_id}] 状态: {session.status}",
            ]
            if session.exit_code is not None:
                brief_lines.append(f"退出码: {session.exit_code}")
            if new_output:
                brief_lines.append(f"新增输出 ({len(lines)} 行):")
                brief_lines.append("---")
                brief_lines.append(new_output)
                brief_lines.append("---")
            else:
                brief_lines.append("暂无新输出。")

            return ToolResult(
                content="\n".join(brief_lines),
                artifacts=[
                    {
                        "monitor_id": session.id,
                        "status": session.status,
                        "exit_code": session.exit_code,
                        "new_output": new_output,
                        "new_lines": lines,
                        "output_offset": session.output_offset,
                    }
                ],
            )

        if action == "kill":
            if session is None:
                return ToolResult(content=f"Monitor {monitor_id} 不存在", is_error=True)
            if session.session_key != session_key:
                return ToolResult(content="无权终止该 monitor", is_error=True)

            await service.kill(monitor_id)
            session_after = service.get(monitor_id)
            status = session_after.status if session_after else "unknown"

            return ToolResult(
                content=f"Monitor [{monitor_id}] 已终止，当前状态: {status}",
                artifacts=[
                    {
                        "monitor_id": monitor_id,
                        "status": status,
                    }
                ],
            )

        if action == "delete":
            if session is not None and session.session_key != session_key:
                return ToolResult(content="无权删除该 monitor", is_error=True)

            deleted = await service.delete_by_session(session_key, monitor_id)
            if not deleted:
                return ToolResult(content=f"Monitor {monitor_id} 不存在或删除失败", is_error=True)

            return ToolResult(
                content=f"Monitor [{monitor_id}] 已删除（包括所有持久化文件）。",
                artifacts=[{"monitor_id": monitor_id, "deleted": True}],
            )

        return ToolResult(content=f"未知的 action: {action}", is_error=True)

    async def invoke_stream(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[ToolResult, None]:
        """流式调用 —— 与 invoke 行为一致。"""
        result = await self.invoke(ctx, **kwargs)
        yield result

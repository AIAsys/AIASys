"""
Local IPython Box - 本地 IPython Kernel 执行工具

使用 jupyter_client 启动本地 IPython Kernel，
提供当前主线需要的执行环境，支持魔法命令、丰富输出等 IPython 特性。

当前实现特点：
- 本地执行：直接使用主机 Python 环境
- 启动更快：无额外运行时准备开销
- 隔离性较弱：共享主机环境，适合当前单机模式
"""

import asyncio
import base64
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult

logger = logging.getLogger(__name__)

from app.services.database import (
    build_runtime_database_helper_env,
    get_connector_credentials_path,
    get_default_runtime_database_broker_url_for_local,
)
from app.services.history import (
    current_agent_config_snapshot,
    current_env_id,
    current_runtime_env_vars,
    current_session_id,
    current_session_root,
    current_user_id,
    current_workspace,
)
from app.services.history.session_execution_journal import SessionExecutionJournal
from app.services.runtime.execution_support import (
    ExecutionJournalContext,
    append_execution_record_if_possible,
    build_local_runtime_bootstrap_code,
    restore_logical_workspace_path,
    rewrite_local_runtime_code,
    sanitize_ansi_text,
)
from app.services.runtime.runtime_execution import (
    kernel_name_for_runtime,
    plan_for_python_execution,
    resolve_runtime_execution_plan,
    runtime_kernel_dirs,
)

try:
    from jupyter_client.multikernelmanager import MultiKernelManager

    JUPYTER_AVAILABLE = True
except ImportError:
    JUPYTER_AVAILABLE = False
    MultiKernelManager = Any  # 占位符类型
    logger.warning("jupyter_client 未安装，LocalIPythonBox 将不可用")

DEFAULT_ENV_ID = "python-data-analysis"
SENSITIVE_KERNEL_ENV_KEYS = {
    "AIASYS_EMBEDDING_API_KEY",
    "AIASYS_AUTH_JWT_SECRET",
    "AIASYS_DOCUMENT_EXTRACTION_PDF_PASSWORD",
    "KIMI_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "EMBEDDING_API_KEY",
    "JWT_SECRET",
    "DB_PASSWORD",
}
SENSITIVE_KERNEL_ENV_SUFFIXES = (
    "_API_KEY",
    "_TOKEN",
    "_SECRET",
    "_PASSWORD",
)
NOTEBOOK_BOOTSTRAP_VARIABLE_NAMES = {
    "In",
    "Out",
    "PS1",
    "Path",
    "REPLHooks",
    "db",
    "exit",
    "get_db",
    "get_last_command",
    "get_ipython",
    "is_wsl",
    "matplotlib",
    "np",
    "open",
    "original_ps1",
    "os",
    "pd",
    "platform",
    "plt",
    "quit",
    "readline",
    "setup_chinese_font",
    "setup_cn_font",
    "sys",
}
SENSITIVE_NOTEBOOK_VARIABLE_NAME_MARKERS = (
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
)
SENSITIVE_NOTEBOOK_PREVIEW_PATTERNS = (
    re.compile(r"session_token\s*=\s*(['\"]).*?\1", re.IGNORECASE),
    re.compile(r"(?:api[_-]?key|token|secret|password)\s*=\s*(['\"]).*?\1", re.IGNORECASE),
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+"),
)
REDACTED_NOTEBOOK_VARIABLE_PREVIEW = "[已隐藏敏感变量预览]"


def should_strip_kernel_env_var(name: str) -> bool:
    normalized = name.upper()
    if normalized in SENSITIVE_KERNEL_ENV_KEYS:
        return True
    if normalized.startswith("AIASYS_LLM_PROVIDER_") and normalized.endswith("_API_KEY"):
        return True
    return normalized.endswith(SENSITIVE_KERNEL_ENV_SUFFIXES)


def build_sanitized_kernel_env(
    source_env: Optional[dict[str, str]] = None,
    custom_env_vars: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    env = dict(source_env or os.environ)
    sanitized = {key: value for key, value in env.items() if not should_strip_kernel_env_var(key)}
    if custom_env_vars:
        sanitized.update(custom_env_vars)
    return sanitized


def should_expose_notebook_variable(name: str) -> bool:
    return name not in NOTEBOOK_BOOTSTRAP_VARIABLE_NAMES and not name.startswith("_aiasys_")


def should_redact_notebook_variable_preview(name: str, preview: str | None) -> bool:
    normalized_name = name.lower()
    if any(marker in normalized_name for marker in SENSITIVE_NOTEBOOK_VARIABLE_NAME_MARKERS):
        return True
    if not preview:
        return False
    return any(pattern.search(preview) for pattern in SENSITIVE_NOTEBOOK_PREVIEW_PATTERNS)


def sanitize_notebook_variable_preview(name: str, preview: str | None) -> str | None:
    if preview is None:
        return None
    if should_redact_notebook_variable_preview(name, preview):
        return REDACTED_NOTEBOOK_VARIABLE_PREVIEW
    return preview


def normalize_notebook_variable_payload(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_items: list[dict[str, Any]] = []
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name or not should_expose_notebook_variable(name):
            continue
        normalized_item = dict(item)
        preview = normalized_item.get("preview")
        if isinstance(preview, str) or preview is None:
            normalized_item["preview"] = sanitize_notebook_variable_preview(
                name,
                preview,
            )
        normalized_items.append(normalized_item)
    return normalized_items


class LocalIPythonBoxParams(BaseModel):
    """本地 IPython Box 参数"""

    code: str = Field(description="要执行的 Python/IPython 代码")
    restart: bool = Field(default=False, description="是否重启内核")


class LocalIPythonBox(AiasysTool):
    """
    本地 IPython Kernel 执行工具

    使用 jupyter_client 在本地启动 IPython Kernel，提供：
    - 魔法命令支持（%matplotlib, %time 等）
    - 丰富输出（图片、HTML、表格）
    - 变量持久化（同一会话内变量保持）
    - 与既有执行链保持兼容的接口

    使用示例：
        box = LocalIPythonBox()
        result = await box({"code": "import pandas as pd; df = pd.DataFrame({'a': [1,2,3]}); df"})
    """

    name: str = "LocalIPythonBox"
    description: str = """在本地 IPython Kernel 中执行 Python 代码。

支持 IPython 魔法命令、丰富输出、变量持久化。

适用场景：
- 需要魔法命令（%matplotlib, %time 等）
- 需要丰富输出（图片、HTML）
- 需要变量持久化
- 本地执行链路，快速启动

Kernel 索引规则：
- 若设置了 notebook_path，kernel 按 notebook 级共享（多 session 共用同一 notebook 的变量）
- 否则按 session 级隔离

预装库：
- pandas, numpy, matplotlib
- 其他后端环境中已安装的库

限制：
- 共享主机 Python 环境，无额外容器隔离
- 建议只在受信任环境中使用
"""
    params: type[BaseModel] = LocalIPythonBoxParams
    parameters: dict[str, Any] = LocalIPythonBoxParams.model_json_schema()

    # 类级别的内核管理器（notebook 间共享）
    _kernel_managers: dict[str, MultiKernelManager] = {}
    _clients: dict[str, Any] = {}
    _last_activity: dict[str, float] = {}
    # 临界区只涉及字典读写，没有 await，使用 threading.Lock 避免跨事件循环绑定问题。
    _lock: threading.Lock = threading.Lock()
    _IDLE_KERNEL_TTL_SECONDS: int = 30 * 60  # 30 分钟无活跃则自动关闭
    _MAX_CACHED_KERNELS: int = 100

    def __init__(self):
        self.workspace: Optional[Path] = None
        self.session_id: Optional[str] = None
        self.notebook_path: Optional[str] = None
        self.kernel_name: str = "python3"
        self.record_execution: bool = True

    def _apply_invoke_context(
        self,
        ctx: dict[str, Any] | None,
    ) -> tuple[Optional[Path], Optional[str], bool]:
        previous_state = (
            self.workspace,
            self.session_id,
            self.record_execution,
        )
        if not ctx:
            return previous_state

        if "workspace" in ctx and ctx["workspace"] is not None:
            self.workspace = Path(str(ctx["workspace"]))
        if "session_id" in ctx and ctx["session_id"] is not None:
            self.session_id = str(ctx["session_id"])
        if "record_execution" in ctx:
            self.record_execution = bool(ctx["record_execution"])
        return previous_state

    def _restore_invoke_context(
        self,
        previous_state: tuple[Optional[Path], Optional[str], bool],
    ) -> None:
        self.workspace, self.session_id, self.record_execution = previous_state

    def _resolve_workspace(self) -> Optional[Path]:
        if self.workspace:
            return self.workspace
        context_workspace = current_workspace.get()
        if context_workspace:
            return Path(context_workspace)
        return None

    def _resolve_session_root(self) -> Optional[Path]:
        context_session_root = current_session_root.get()
        if context_session_root:
            return Path(context_session_root)
        return None

    def _resolve_session_id(self) -> str:
        return self.session_id or current_session_id.get() or "default_session"

    def _resolve_user_id(self) -> str:
        workspace = self._resolve_workspace()
        if workspace:
            parts = workspace.resolve().parts
            for index, part in enumerate(parts):
                if part == "workspaces" and index + 1 < len(parts):
                    return parts[index + 1]
        session_root = self._resolve_session_root()
        if session_root:
            parts = session_root.resolve().parts
            for index, part in enumerate(parts):
                if part == "workspaces" and index + 1 < len(parts):
                    return parts[index + 1]
        return current_user_id.get() or "default_user"

    def _resolve_runtime_helper_env(self) -> dict[str, str]:
        session_id = self._resolve_session_id()
        user_id = self._resolve_user_id()
        env = build_runtime_database_helper_env(
            user_id=user_id,
            session_id=session_id,
            sandbox_mode="local",
            backend_base_url=get_default_runtime_database_broker_url_for_local(),
        )
        creds_path = get_connector_credentials_path(session_id)
        if creds_path.exists():
            env["AIASYS_CONNECTOR_CONFIG_PATH"] = str(creds_path)
        return env

    def _resolve_execution_journal(self) -> Optional[SessionExecutionJournal]:
        session_root = self._resolve_session_root()
        session_id = self.session_id or current_session_id.get()
        if not session_root or not session_id:
            return None
        return SessionExecutionJournal(session_root, session_id)

    def _append_execution_record(
        self,
        *,
        code: str,
        started_at: str,
        status: str,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        error: Optional[str] = None,
        result_preview_text: Optional[str] = None,
    ) -> None:
        append_execution_record_if_possible(
            enabled=self.record_execution,
            context=ExecutionJournalContext(
                workspace=self._resolve_workspace(),
                session_id=self.session_id or current_session_id.get(),
                sandbox_mode="local",
                env_id=current_env_id.get(),
                origin_source="local_ipython_box",
                tool_name="LocalIPythonBox",
                agent_config_snapshot=current_agent_config_snapshot.get(),
            ),
            code=code,
            started_at=started_at,
            status=status,
            stdout=stdout,
            stderr=stderr,
            error=error,
            result_preview_text=result_preview_text,
        )

    def _rewrite_workspace_literals(
        self,
        code: str,
        workspace: Optional[Path],
    ) -> str:
        """将本地模式中的逻辑 `/workspace` 路径映射到真实会话目录。"""
        return rewrite_local_runtime_code(code, workspace=workspace)

    def _restore_workspace_display_paths(
        self,
        text: Optional[str],
        workspace: Optional[Path],
    ) -> Optional[str]:
        """将真实宿主机路径还原为前端约定的 `/workspace` 展示路径。"""
        return restore_logical_workspace_path(text, workspace)

    def _sanitize_display_text(self, text: Optional[str]) -> Optional[str]:
        return sanitize_ansi_text(text)

    def _apply_post_execution_policy(
        self,
        session_id: str,
        user_id: str,
        notebook_path: str | None = None,
    ) -> None:
        journal = self._resolve_execution_journal()
        if not journal:
            return
        try:
            recovery_policy = journal.get_recovery_config().get(
                "recovery_policy",
                "journal_only",
            )
            if recovery_policy != "discard":
                return
            self.shutdown_kernel(session_id, notebook_path, user_id, kernel_name=self.kernel_name)
            journal.update_recovery_config(last_runtime_state="discarded")
        except Exception as exc:
            logger.error(
                f"[LocalIPythonBox] 执行 discard 恢复策略失败: {exc}",
                exc_info=True,
            )
            raise

    @classmethod
    def _get_kernel_key(
        cls,
        session_id: str | None = None,
        notebook_path: str | None = None,
        user_id: str = "default",
        kernel_name: str = "python3",
    ) -> str:
        """生成内核唯一标识。kernel_name 参与 key，确保不同环境的内核隔离。"""
        if notebook_path:
            normalized = Path(notebook_path).as_posix()
            return f"{user_id}_nb:{normalized}#{kernel_name}"
        return f"{user_id}_{session_id or 'default_session'}#{kernel_name}"

    @classmethod
    def _evict_oldest_kernel(cls) -> None:
        """按最后活跃时间淘汰最旧的内核，防止类级缓存无限增长。"""
        if not cls._last_activity:
            return
        oldest_key = min(cls._last_activity, key=cls._last_activity.get)
        cls._shutdown_kernel_by_key(oldest_key)

    @classmethod
    def _shutdown_kernel_by_key(cls, key: str) -> None:
        """按 key 关闭并移除缓存的内核（调用方需自行持锁）。"""
        km = cls._kernel_managers.pop(key, None)
        client = cls._clients.pop(key, None)
        cls._last_activity.pop(key, None)
        try:
            if client:
                client.stop_channels()
            if km:
                km.shutdown_kernel(now=True)
            logger.info("[LocalIPythonBox] 缓存已满，淘汰旧内核: %s", key)
        except Exception as exc:
            logger.warning("[LocalIPythonBox] 淘汰旧内核失败 %s: %s", key, exc)

    @classmethod
    def has_kernel(
        cls,
        session_id: str | None = None,
        notebook_path: str | None = None,
        user_id: str = "default",
        kernel_name: str = "python3",
    ) -> bool:
        """判断指定 notebook 或 session 是否持有活跃本地内核。"""
        return (
            cls._get_kernel_key(session_id, notebook_path, user_id, kernel_name=kernel_name)
            in cls._kernel_managers
        )

    @classmethod
    async def _get_or_create_kernel(
        cls,
        session_id: str | None = None,
        notebook_path: str | None = None,
        user_id: str = "default",
        cwd: Optional[str] = None,
        kernel_name: str = "python3",
    ) -> tuple[Any, Any]:
        """
        获取或创建 IPython Kernel

        Returns:
            (kernel_manager, client)
        """
        if not JUPYTER_AVAILABLE:
            raise RuntimeError("jupyter_client 未安装，无法创建 IPython Kernel")

        key = cls._get_kernel_key(session_id, notebook_path, user_id, kernel_name=kernel_name)

        # 先在锁内快速检查是否已有内核，避免重复创建
        with cls._lock:
            if key in cls._kernel_managers:
                logger.info(f"[LocalIPythonBox] 复用现有内核: {key}")
                cls._last_activity[key] = time.time()
                return cls._kernel_managers[key], cls._clients[key]

        # 在锁外执行同步阻塞的 start_new_kernel，避免长时间持锁
        logger.info(f"[LocalIPythonBox] 创建新内核: {key} (kernel_name={kernel_name})")

        try:
            custom_vars = current_runtime_env_vars.get()
            from jupyter_client.kernelspec import KernelSpecManager
            from jupyter_client.manager import KernelManager

            kernel_spec_manager = KernelSpecManager(
                kernel_dirs=runtime_kernel_dirs(),
            )

            def _start_kernel():
                km = KernelManager(
                    kernel_name=kernel_name,
                    kernel_spec_manager=kernel_spec_manager,
                )
                km.start_kernel(
                    cwd=cwd,
                    env=build_sanitized_kernel_env(custom_env_vars=custom_vars),
                )
                kc = km.client()
                kc.start_channels()
                try:
                    kc.wait_for_ready(timeout=60)
                except RuntimeError:
                    kc.stop_channels()
                    km.shutdown_kernel()
                    raise
                return km, kc

            kernel_manager, client = await asyncio.to_thread(_start_kernel)

            # 初始化环境
            cls._init_kernel_env(client)

        except Exception as e:
            logger.error(f"[LocalIPythonBox] 创建内核失败: {e}")
            raise RuntimeError(f"无法创建 IPython Kernel: {e}")

        # 在锁内原子性地存储内核引用；超出上限时淘汰最旧的缓存
        with cls._lock:
            if len(cls._kernel_managers) >= cls._MAX_CACHED_KERNELS:
                cls._evict_oldest_kernel()
            cls._kernel_managers[key] = kernel_manager
            cls._clients[key] = client
            cls._last_activity[key] = time.time()

        return kernel_manager, client

    @classmethod
    def _init_kernel_env(cls, client, helper_env: Optional[dict[str, str]] = None):
        """初始化内核环境（预导入常用库，配置 matplotlib）"""
        init_code = build_local_runtime_bootstrap_code(helper_env)
        try:
            client.execute(init_code, silent=True)
        except Exception as e:
            logger.error(f"[LocalIPythonBox] 初始化环境失败: {e}", exc_info=True)

    @classmethod
    async def start_kernel(
        cls,
        session_id: str | None = None,
        notebook_path: str | None = None,
        user_id: str = "default",
        cwd: Optional[str] = None,
        helper_env: Optional[dict[str, str]] = None,
        kernel_name: str = "python3",
    ) -> bool:
        """显式启动内核，并按需执行一次环境引导。"""
        key = cls._get_kernel_key(session_id, notebook_path, user_id, kernel_name=kernel_name)
        created = key not in cls._kernel_managers
        _, client = await cls._get_or_create_kernel(
            session_id=session_id,
            notebook_path=notebook_path,
            user_id=user_id,
            cwd=cwd,
            kernel_name=kernel_name,
        )
        if created or helper_env is not None:
            cls._init_kernel_env(client, helper_env=helper_env)
        return created

    @classmethod
    def shutdown_kernel(
        cls,
        session_id: str | None = None,
        notebook_path: str | None = None,
        user_id: str = "default",
        kernel_name: str = "python3",
    ):
        """关闭指定 notebook 或 session 的内核"""
        key = cls._get_kernel_key(session_id, notebook_path, user_id, kernel_name=kernel_name)

        if key in cls._kernel_managers:
            try:
                kernel_manager = cls._kernel_managers[key]
                client = cls._clients[key]

                client.stop_channels()
                kernel_manager.shutdown_kernel(now=True)

                del cls._kernel_managers[key]
                del cls._clients[key]
                cls._last_activity.pop(key, None)

                logger.info(f"[LocalIPythonBox] 内核已关闭: {key}")
            except Exception as e:
                logger.error(f"[LocalIPythonBox] 关闭内核失败: {e}", exc_info=True)

    @classmethod
    def interrupt_kernel(
        cls,
        session_id: str | None = None,
        notebook_path: str | None = None,
        user_id: str = "default",
        kernel_name: str = "python3",
    ) -> bool:
        """向指定 notebook 或 session 的 kernel 发送中断信号。"""
        key = cls._get_kernel_key(session_id, notebook_path, user_id, kernel_name=kernel_name)
        kernel_manager = cls._kernel_managers.get(key)
        if kernel_manager is None:
            return False
        try:
            kernel_manager.interrupt_kernel()
            logger.info("[LocalIPythonBox] 已中断内核: %s", key)
            return True
        except Exception as exc:
            logger.warning("[LocalIPythonBox] 中断内核失败: %s", exc)
            return False

    @classmethod
    async def restart_kernel(
        cls,
        session_id: str | None = None,
        notebook_path: str | None = None,
        user_id: str = "default",
        *,
        cwd: Optional[str] = None,
        helper_env: Optional[dict[str, str]] = None,
    ) -> bool:
        """重启指定 notebook 或 session 的 kernel。若不存在则创建一个新的。"""
        key = cls._get_kernel_key(session_id, notebook_path, user_id)
        had_kernel = key in cls._kernel_managers
        cls.shutdown_kernel(session_id, notebook_path, user_id)
        await cls.start_kernel(
            session_id=session_id,
            notebook_path=notebook_path,
            user_id=user_id,
            cwd=cwd,
            helper_env=helper_env,
        )
        logger.info("[LocalIPythonBox] 已重启内核: %s", key)
        return had_kernel

    @classmethod
    def stop_kernel(
        cls,
        session_id: str | None = None,
        notebook_path: str | None = None,
        user_id: str = "default",
    ) -> bool:
        """停止指定 notebook 或 session 的 kernel，并返回停止前是否存在活跃 kernel。"""
        key = cls._get_kernel_key(session_id, notebook_path, user_id)
        had_kernel = key in cls._kernel_managers
        cls.shutdown_kernel(session_id, notebook_path, user_id)
        return had_kernel

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        previous_state = self._apply_invoke_context(ctx)
        try:
            params = LocalIPythonBoxParams.model_validate(kwargs)
            return await self._execute_tool(params)
        finally:
            self._restore_invoke_context(previous_state)

    async def _execute_tool(
        self,
        params: LocalIPythonBoxParams,
    ) -> ToolResult:
        if not JUPYTER_AVAILABLE:
            error_message = (
                "jupyter_client 未安装，无法执行代码。请安装: pip install jupyter_client"
            )
            return ToolResult(content=error_message, is_error=True)

        session_id = self._resolve_session_id()
        user_id = self._resolve_user_id()
        workspace = self._resolve_workspace()
        notebook_path = self.notebook_path
        started_at = datetime.now().isoformat()

        try:
            plan = plan_for_python_execution(
                resolve_runtime_execution_plan(workspace=workspace),
            )
            self.kernel_name = kernel_name_for_runtime(
                self.kernel_name,
                plan=plan,
            )
            helper_env = self._resolve_runtime_helper_env()
            _, client = await self._get_or_create_kernel(
                session_id=session_id,
                notebook_path=notebook_path,
                user_id=user_id,
                cwd=str(workspace) if workspace else None,
                kernel_name=self.kernel_name,
            )
            self._init_kernel_env(client, helper_env=helper_env)

            if params.restart:
                logger.info("[LocalIPythonBox] 重启内核")
                self.shutdown_kernel(
                    session_id, notebook_path, user_id, kernel_name=self.kernel_name
                )
                _, client = await self._get_or_create_kernel(
                    session_id=session_id,
                    notebook_path=notebook_path,
                    user_id=user_id,
                    cwd=str(workspace) if workspace else None,
                    kernel_name=self.kernel_name,
                )
                self._init_kernel_env(client, helper_env=helper_env)

            executable_code = self._rewrite_workspace_literals(
                params.code,
                workspace,
            )
            if executable_code != params.code:
                logger.info(
                    "[LocalIPythonBox] 已将逻辑 /workspace 路径映射到本地会话目录: session=%s",
                    session_id,
                )

            from app.core.config import validate_code_timeout
            from app.services.history import resolve_current_code_timeout

            session_timeout = resolve_current_code_timeout()
            effective_timeout = validate_code_timeout(
                session_timeout,
                "local",
            )

            logger.info(
                "[LocalIPythonBox] 执行代码 (session_timeout=%s, effective_timeout=%ss): %s...",
                session_timeout,
                effective_timeout,
                params.code[:100],
            )
            try:
                execution_result = await asyncio.to_thread(
                    self._execute_code_via_kernel,
                    client=client,
                    executable_code=executable_code,
                    effective_timeout=effective_timeout,
                    workspace=workspace,
                    session_id=session_id,
                    user_id=user_id,
                    notebook_path=notebook_path,
                )
            except TimeoutError:
                timeout_message = f"代码执行超时（{effective_timeout}秒），已中断执行"
                self._append_execution_record(
                    code=params.code,
                    started_at=started_at,
                    status="failed",
                    stderr=timeout_message,
                    error=timeout_message,
                    result_preview_text=timeout_message,
                )
                self._apply_post_execution_policy(session_id, user_id, notebook_path)
                return ToolResult(content=timeout_message, is_error=True)

            error_output = execution_result["error_output"]
            outputs = execution_result["outputs"]

            if error_output:
                error_output = self._restore_workspace_display_paths(
                    error_output,
                    workspace,
                )
                error_output = self._sanitize_display_text(error_output)
                normalized_output = (
                    self._restore_workspace_display_paths(
                        "".join(outputs),
                        workspace,
                    )
                    or ""
                )
                normalized_output = self._sanitize_display_text(normalized_output) or ""
                self._append_execution_record(
                    code=params.code,
                    started_at=started_at,
                    status="failed",
                    stdout=normalized_output,
                    stderr=error_output,
                    error=error_output,
                    result_preview_text=error_output,
                )
                self._apply_post_execution_policy(session_id, user_id, notebook_path)
                return ToolResult(
                    content=error_output or normalized_output,
                    is_error=True,
                )

            final_output = "".join(outputs)
            final_output = self._restore_workspace_display_paths(
                final_output,
                workspace,
            )
            final_output = self._sanitize_display_text(final_output) or ""
            if not final_output.strip():
                final_output = "(代码执行成功，无输出)"

            self._append_execution_record(
                code=params.code,
                started_at=started_at,
                status="completed",
                stdout=final_output,
                result_preview_text=final_output,
            )
            self._apply_post_execution_policy(session_id, user_id, notebook_path)

            logger.info("[LocalIPythonBox] 执行成功")
            return ToolResult(content=final_output)

        except Exception as exc:
            logger.error("[LocalIPythonBox] 执行失败: %s", exc)
            error_message = f"执行失败: {str(exc)}"
            self._append_execution_record(
                code=params.code,
                started_at=started_at,
                status="failed",
                stderr=str(exc),
                error=str(exc),
                result_preview_text=str(exc),
            )
            self._apply_post_execution_policy(session_id, user_id, notebook_path)
            return ToolResult(content=error_message, is_error=True)

    async def execute_notebook_code(
        self,
        *,
        code: str,
        restart: bool = False,
    ) -> dict[str, Any]:
        """
        以 notebook 语义执行代码并返回结构化 outputs。

        该接口供 notebook workbench API 使用。
        """
        if not JUPYTER_AVAILABLE:
            raise RuntimeError("jupyter_client 未安装，无法执行 notebook 代码。")

        session_id = self._resolve_session_id()
        user_id = self._resolve_user_id()
        workspace = self._resolve_workspace()
        notebook_path = self.notebook_path
        plan = plan_for_python_execution(
            resolve_runtime_execution_plan(workspace=workspace),
        )
        self.kernel_name = kernel_name_for_runtime(
            self.kernel_name,
            plan=plan,
        )
        helper_env = self._resolve_runtime_helper_env()

        _kernel_manager, client = await self._get_or_create_kernel(
            session_id=session_id,
            notebook_path=notebook_path,
            user_id=user_id,
            cwd=str(workspace) if workspace else None,
        )
        self._init_kernel_env(client, helper_env=helper_env)

        if restart:
            logger.info("[LocalIPythonBox] notebook workbench 请求重启内核")
            self.shutdown_kernel(session_id, notebook_path, user_id, kernel_name=self.kernel_name)
            _kernel_manager, client = await self._get_or_create_kernel(
                session_id=session_id,
                notebook_path=notebook_path,
                user_id=user_id,
                cwd=str(workspace) if workspace else None,
            )
            self._init_kernel_env(client, helper_env=helper_env)

        executable_code = self._rewrite_workspace_literals(code, workspace)
        from app.core.config import validate_code_timeout
        from app.services.history import resolve_current_code_timeout

        session_timeout = resolve_current_code_timeout()
        effective_timeout = validate_code_timeout(session_timeout, "local")

        return await asyncio.to_thread(
            self._execute_code_via_kernel_notebook,
            client=client,
            executable_code=executable_code,
            effective_timeout=effective_timeout,
            workspace=workspace,
            session_id=session_id,
            user_id=user_id,
            notebook_path=notebook_path,
        )

    async def inspect_kernel_variables(self) -> list[dict[str, Any]]:
        """
        读取当前 kernel 中的变量摘要。

        该接口不写 execution journal，也不修改 notebook 文档。
        """
        if not JUPYTER_AVAILABLE:
            raise RuntimeError("jupyter_client 未安装，无法读取变量摘要。")

        session_id = self._resolve_session_id()
        user_id = self._resolve_user_id()
        workspace = self._resolve_workspace()
        notebook_path = self.notebook_path
        plan = plan_for_python_execution(
            resolve_runtime_execution_plan(workspace=workspace),
        )
        self.kernel_name = kernel_name_for_runtime(
            self.kernel_name,
            plan=plan,
        )
        helper_env = self._resolve_runtime_helper_env()

        _, client = await self._get_or_create_kernel(
            session_id=session_id,
            notebook_path=notebook_path,
            user_id=user_id,
            cwd=str(workspace) if workspace else None,
        )
        self._init_kernel_env(client, helper_env=helper_env)

        from app.core.config import validate_code_timeout
        from app.services.history import resolve_current_code_timeout

        session_timeout = resolve_current_code_timeout()
        effective_timeout = validate_code_timeout(session_timeout, "local")
        probe_code = """
import json as __aiasys_json
from IPython.display import JSON as __aiasys_JSON, display as __aiasys_display

def __aiasys_notebook_preview(value):
    try:
        preview = repr(value)
    except Exception as exc:
        preview = f"<repr failed: {exc}>"
    if len(preview) > 240:
        preview = preview[:240].rstrip() + "..."
    return preview

def __aiasys_notebook_shape(value):
    shape = getattr(value, "shape", None)
    if shape is None:
        return None
    try:
        return list(shape)
    except Exception:
        return repr(shape)

def __aiasys_notebook_size(value):
    try:
        return len(value)
    except Exception:
        return None

def __aiasys_notebook_is_user_value(name, value):
    if name.startswith("_"):
        return False
    excluded_names = set(__AIASYS_NOTEBOOK_BOOTSTRAP_VARIABLE_NAMES__)
    if name in excluded_names:
        return False
    module_name = getattr(type(value), "__module__", "") or ""
    if module_name.startswith("IPython."):
        return False
    return True

__aiasys_payload = []
for __aiasys_name in sorted(globals()):
    if __aiasys_name.startswith("__aiasys_"):
        continue
    try:
        __aiasys_value = globals()[__aiasys_name]
    except Exception:
        continue
    if not __aiasys_notebook_is_user_value(__aiasys_name, __aiasys_value):
        continue
    __aiasys_payload.append({
        "name": __aiasys_name,
        "type_name": type(__aiasys_value).__name__,
        "module_name": getattr(type(__aiasys_value), "__module__", None),
        "size": __aiasys_notebook_size(__aiasys_value),
        "shape": __aiasys_notebook_shape(__aiasys_value),
        "preview": __aiasys_notebook_preview(__aiasys_value),
    })

__aiasys_display(__aiasys_JSON(__aiasys_payload))
"""
        probe_code = probe_code.replace(
            "__AIASYS_NOTEBOOK_BOOTSTRAP_VARIABLE_NAMES__",
            json.dumps(sorted(NOTEBOOK_BOOTSTRAP_VARIABLE_NAMES)),
        )

        result = await asyncio.to_thread(
            self._execute_code_via_kernel_notebook,
            client=client,
            executable_code=probe_code,
            effective_timeout=effective_timeout,
            workspace=workspace,
            session_id=session_id,
            user_id=user_id,
            notebook_path=notebook_path,
        )

        if result.get("error_output"):
            raise RuntimeError(str(result["error_output"]))

        for output in result.get("notebook_outputs") or []:
            if output.get("output_type") not in {"display_data", "execute_result"}:
                continue
            data = output.get("data") or {}
            payload = data.get("application/json")
            if isinstance(payload, list):
                return normalize_notebook_variable_payload(
                    [item for item in payload if isinstance(item, dict)]
                )
            if isinstance(payload, str):
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, list):
                    return normalize_notebook_variable_payload(
                        [item for item in parsed if isinstance(item, dict)]
                    )
        return []

    def _execute_code_via_kernel(
        self,
        *,
        client: Any,
        executable_code: str,
        effective_timeout: int,
        workspace: Path | None,
        session_id: str,
        user_id: str,
        notebook_path: str | None = None,
    ) -> dict[str, str | None]:
        msg_id = client.execute(executable_code)

        outputs: list[str] = []
        error_output = None
        deadline = time.monotonic() + effective_timeout

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"代码执行超时（{effective_timeout}秒）")

            try:
                msg = client.get_iopub_msg(timeout=remaining)
                parent_header = msg.get("parent_header") or {}
                parent_msg_id = parent_header.get("msg_id")
                if parent_msg_id and parent_msg_id != msg_id:
                    continue

                msg_type = msg["msg_type"]
                content = msg["content"]

                if msg_type == "stream":
                    text = content.get("text", "")
                    outputs.append(text)

                elif msg_type == "execute_result":
                    data = content.get("data", {})
                    text = data.get("text/plain", "")
                    if text:
                        outputs.append(text)

                    if "image/png" in data:
                        img_data = data["image/png"]
                        if workspace:
                            img_path = self._save_image(img_data)
                            outputs.append(f"[图片已保存: {img_path}]")
                        else:
                            outputs.append("[图片输出 (未配置工作区)]")

                elif msg_type == "error":
                    ename = content.get("ename", "Error")
                    evalue = content.get("evalue", "")
                    traceback = content.get("traceback", [])
                    error_output = f"{ename}: {evalue}\n" + "\n".join(traceback)

                elif msg_type == "status" and content.get("execution_state") == "idle":
                    break

            except TimeoutError:
                self._interrupt_kernel_after_timeout(
                    client=client,
                    session_id=session_id,
                    user_id=user_id,
                    notebook_path=notebook_path,
                )
                raise

        return {
            "outputs": "".join(outputs),
            "error_output": error_output,
        }

    def _filter_notebook_mime_bundle(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {}

        allowed_keys = (
            "text/plain",
            "text/html",
            "image/png",
            "image/jpeg",
            "application/json",
        )
        filtered: dict[str, Any] = {}
        for key in allowed_keys:
            if key not in data:
                continue
            value = data[key]
            if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
                filtered[key] = value
        return filtered

    def _execute_code_via_kernel_notebook(
        self,
        *,
        client: Any,
        executable_code: str,
        effective_timeout: int,
        workspace: Path | None,
        session_id: str,
        user_id: str,
        notebook_path: str | None = None,
    ) -> dict[str, Any]:
        msg_id = client.execute(executable_code)

        notebook_outputs: list[dict[str, Any]] = []
        stdout_fragments: list[str] = []
        error_output = None
        deadline = time.monotonic() + effective_timeout

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"代码执行超时（{effective_timeout}秒）")

            try:
                msg = client.get_iopub_msg(timeout=remaining)
                parent_header = msg.get("parent_header") or {}
                parent_msg_id = parent_header.get("msg_id")
                if parent_msg_id and parent_msg_id != msg_id:
                    continue

                msg_type = msg["msg_type"]
                content = msg["content"]

                if msg_type == "stream":
                    text = str(content.get("text", "") or "")
                    name = str(content.get("name", "stdout") or "stdout")
                    stdout_fragments.append(text)
                    notebook_outputs.append(
                        {
                            "output_type": "stream",
                            "name": name,
                            "text": text,
                        }
                    )
                    continue

                if msg_type in {"execute_result", "display_data"}:
                    data = self._filter_notebook_mime_bundle(content.get("data"))
                    if not data:
                        continue

                    text_plain = data.get("text/plain")
                    if isinstance(text_plain, list):
                        stdout_fragments.append("".join(str(item) for item in text_plain))
                    elif isinstance(text_plain, str):
                        stdout_fragments.append(text_plain)

                    notebook_outputs.append(
                        {
                            "output_type": msg_type,
                            "data": data,
                            "metadata": content.get("metadata") or {},
                        }
                    )
                    continue

                if msg_type == "error":
                    ename = str(content.get("ename", "Error") or "Error")
                    evalue = str(content.get("evalue", "") or "")
                    traceback = [
                        str(item) for item in (content.get("traceback") or []) if item is not None
                    ]
                    error_output = f"{ename}: {evalue}".strip()
                    notebook_outputs.append(
                        {
                            "output_type": "error",
                            "name": ename,
                            "text": error_output,
                            "traceback": traceback,
                        }
                    )
                    continue

                if msg_type == "status" and content.get("execution_state") == "idle":
                    break

            except TimeoutError:
                self._interrupt_kernel_after_timeout(
                    client=client,
                    session_id=session_id,
                    user_id=user_id,
                    notebook_path=notebook_path,
                )
                raise

        stdout_text = "".join(stdout_fragments)
        stdout_text = self._restore_workspace_display_paths(stdout_text, workspace) or ""
        stdout_text = self._sanitize_display_text(stdout_text) or ""
        if error_output:
            error_output = self._restore_workspace_display_paths(error_output, workspace)
            error_output = self._sanitize_display_text(error_output)

        return {
            "notebook_outputs": notebook_outputs,
            "stdout_text": stdout_text,
            "error_output": error_output,
        }

    def _interrupt_kernel_after_timeout(
        self,
        *,
        client: Any,
        session_id: str,
        user_id: str,
        notebook_path: str | None = None,
    ) -> None:
        try:
            key = self._get_kernel_key(
                session_id, notebook_path, user_id, kernel_name=self.kernel_name
            )
            km = self._kernel_managers.get(key)
            if km:
                km.interrupt_kernel()
                logger.info(
                    "[LocalIPythonBox] 已发送中断信号到 Kernel: notebook=%s session=%s",
                    notebook_path,
                    session_id,
                )
                try:
                    client.get_iopub_msg(timeout=3)
                except TimeoutError:
                    logger.warning("[LocalIPythonBox] Kernel 未响应中断，强制重启")
                    km.restart_kernel(now=True)
        except Exception as interrupt_err:
            logger.warning("[LocalIPythonBox] 中断 Kernel 失败: %s", interrupt_err)

    def _save_image(self, img_data: str) -> str:
        """保存 base64 图片到工作区"""
        try:
            img_bytes = base64.b64decode(img_data)
            img_name = f"output_{uuid.uuid4().hex[:8]}.png"

            workspace = self._resolve_workspace()
            if not workspace:
                logger.warning("无法保存图片：未配置工作区")
                return "output.png"
            img_path = workspace / img_name
            img_path.write_bytes(img_bytes)
            return str(img_name)
        except Exception as e:
            logger.warning("保存图片失败: %s", e)
            return "output.png"

    @classmethod
    def cleanup_idle_kernels(cls, max_idle_seconds: int | None = None) -> int:
        """关闭超过指定时间无活跃的 kernel，返回关闭数量。

        建议在应用启动时通过 asyncio.create_task 启动周期性调用，例如：
        ```python
        async def _kernel_cleanup_loop():
            while True:
                await asyncio.sleep(300)
                LocalIPythonBox.cleanup_idle_kernels()
        ```
        """
        ttl = max_idle_seconds or cls._IDLE_KERNEL_TTL_SECONDS
        now = time.time()
        keys_to_remove = [
            key for key, last_active in list(cls._last_activity.items()) if now - last_active > ttl
        ]
        for key in keys_to_remove:
            try:
                km = cls._kernel_managers.get(key)
                client = cls._clients.get(key)
                if client:
                    client.stop_channels()
                if km:
                    km.shutdown_kernel(now=True)
                cls._kernel_managers.pop(key, None)
                cls._clients.pop(key, None)
                cls._last_activity.pop(key, None)
                logger.info("[LocalIPythonBox] 自动清理空闲内核: %s", key)
            except Exception as exc:
                logger.warning("[LocalIPythonBox] 自动清理内核失败 %s: %s", key, exc)
        return len(keys_to_remove)

"""
代码执行运行时共享 support。

目标：
- 让本地执行链路共享公共能力，而不是散落到各个工具里
- 保持 transport / lifecycle 差异仍由具体 runtime 自己负责
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.services.history.session_execution_journal import SessionExecutionJournal

logger = logging.getLogger(__name__)

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
LOGICAL_WORKSPACE_ROOT = "/workspace"


@dataclass(frozen=True, slots=True)
class ExecutionJournalContext:
    """执行记录追加时所需的最小上下文。"""

    workspace: Path | None
    session_id: str | None
    sandbox_mode: str | None
    env_id: str | None
    origin_source: str
    tool_name: str
    agent_config_snapshot: Optional[dict[str, Any]] = None


def sanitize_ansi_text(text: Optional[str]) -> Optional[str]:
    """去掉 ANSI 控制序列，避免前端显示异常字符。"""
    if text is None:
        return None
    return ANSI_ESCAPE_RE.sub("", text)


def restore_logical_workspace_path(
    text: Optional[str],
    workspace: Path | None,
) -> Optional[str]:
    """将真实宿主机路径还原成对 agent 稳定的逻辑 `/workspace`。"""
    if text is None or workspace is None:
        return text
    return text.replace(str(workspace.resolve()), LOGICAL_WORKSPACE_ROOT)


def build_visible_error_output(
    stdout: Optional[str],
    error_message: Optional[str],
) -> str:
    """
    为前端结果区生成更稳定的可见输出。

    规则：
    - stdout 有内容时优先展示 stdout
    - 仅当 stdout 为空且错误像超时时，才直接展示错误文本
    """
    normalized_stdout = stdout or ""
    if normalized_stdout.strip():
        return normalized_stdout

    normalized_error = error_message or ""
    lowered = normalized_error.lower()
    if "超时" in normalized_error or "timeout" in lowered:
        return normalized_error
    return normalized_stdout


def resolve_backend_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def resolve_runtime_helper_dir() -> Path:
    return resolve_backend_root() / "agent_runtime_helpers"


def rewrite_local_runtime_code(
    code: str,
    *,
    workspace: Path | None,
) -> str:
    """
    将 local runtime 中的逻辑路径改写为宿主机真实路径。

    这里保留“逻辑 `/workspace`”语义，避免 prompt 或历史代码感知宿主机目录。
    """
    normalized = code

    if workspace and LOGICAL_WORKSPACE_ROOT in normalized:
        workspace_root = str(workspace.resolve())
        prefixes = (
            "",
            "f",
            "F",
            "r",
            "R",
            "rf",
            "rF",
            "Rf",
            "RF",
            "fr",
            "fR",
            "Fr",
            "FR",
            "b",
            "B",
            "br",
            "bR",
            "Br",
            "BR",
            "rb",
            "rB",
            "Rb",
            "RB",
        )

        for prefix in prefixes:
            for quote in ('"', "'"):
                normalized = normalized.replace(
                    f"{prefix}{quote}{LOGICAL_WORKSPACE_ROOT}/{quote}",
                    f"{prefix}{quote}{workspace_root}/{quote}",
                )
                normalized = normalized.replace(
                    f"{prefix}{quote}{LOGICAL_WORKSPACE_ROOT}/",
                    f"{prefix}{quote}{workspace_root}/",
                )
                normalized = normalized.replace(
                    f"{prefix}{quote}{LOGICAL_WORKSPACE_ROOT}{quote}",
                    f"{prefix}{quote}{workspace_root}{quote}",
                )

    return normalized


def build_local_runtime_bootstrap_code(
    helper_env: Optional[dict[str, str]] = None,
) -> str:
    """生成 local IPython kernel 的统一 bootstrap 代码。"""
    helper_env_code = ""
    if helper_env:
        for key, value in helper_env.items():
            helper_env_code += f"os.environ[{json.dumps(key)}] = {json.dumps(value)}\n"

    helper_dir = resolve_runtime_helper_dir()

    return f"""
# 预导入常用库
import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
_aiasys_helper_dir = {json.dumps(str(helper_dir))}
if _aiasys_helper_dir not in sys.path:
    sys.path.insert(0, _aiasys_helper_dir)
try:
    from font_helper import setup_cn_font
    setup_chinese_font = setup_cn_font
    _aiasys_font_info = setup_cn_font(quiet=True)
except Exception as _aiasys_font_exc:
    print(f"[AIASys] font helper 初始化失败: {{_aiasys_font_exc}}")

# 设置 inline 模式
%matplotlib inline
{helper_env_code}
try:
    from db_helper import get_db
    db = get_db()
except Exception as _aiasys_db_exc:
    print(f"[AIASys] db helper 初始化失败: {{_aiasys_db_exc}}")
"""


def append_execution_record_if_possible(
    *,
    enabled: bool,
    context: ExecutionJournalContext,
    code: str,
    started_at: str,
    status: str,
    stdout: Optional[str] = None,
    stderr: Optional[str] = None,
    error: Optional[str] = None,
    result_preview_text: Optional[str] = None,
    artifact_refs: Optional[list[str]] = None,
) -> bool:
    """按统一方式写 execution journal，缺上下文时安静降级。"""
    if not enabled or context.workspace is None or not context.session_id:
        return False

    try:
        journal = SessionExecutionJournal(context.workspace, context.session_id)
        journal.append_record(
            code=code,
            started_at=started_at,
            finished_at=datetime.now().isoformat(),
            status=status,
            sandbox_mode=context.sandbox_mode,
            env_id=context.env_id,
            stdout=stdout,
            stderr=stderr,
            error=error,
            result_preview_text=result_preview_text,
            artifact_refs=artifact_refs,
            origin_source=context.origin_source,
            tool_name=context.tool_name,
            agent_config_snapshot=context.agent_config_snapshot,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[%s] 追加 execution journal 失败: %s", context.tool_name, exc)
        return False

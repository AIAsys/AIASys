"""Shell 命令执行工具。

提供 Agent 执行单次同步 Shell 命令的能力。
后台长时间运行任务请使用 Monitor 工具。
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agents.tools.local_ipython_box import build_sanitized_kernel_env
from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.history import current_runtime_env_vars, current_session_root, current_workspace
from app.services.runtime.runtime_execution import (
    build_runtime_shell_env,
    resolve_runtime_execution_plan,
    wrap_shell_command_for_runtime,
)

MAX_OUTPUT_BYTES = 16_384  # 16KB，参考 Codex CLI
DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 300  # 5分钟


def _build_shell_exec_env() -> dict[str, str] | None:
    """构建 Shell 执行环境：os.environ 去敏 + 工作区自定义 env vars。"""
    env = build_sanitized_kernel_env()
    custom = current_runtime_env_vars.get()
    if custom:
        env.update(custom)
    # 注入工作区路径，供 skill 脚本读取 config.json
    workspace = current_workspace.get()
    if workspace:
        env["AIASYS_WORKSPACE_ROOT"] = str(workspace)
    return env


# 危险命令模式（参考 Claude Code + Hermes）
# re.search 匹配命令中任意位置的危险子命令
_DANGEROUS_PATTERNS = [
    r"\brm\s+(?:-r(?:f)?|-f\s*-r|--recursive)\s+/(?:\s|$|\*|~)",  # rm -rf / 及其变体
    r"\brm\s+(?:-r(?:f)?|-f\s*-r|--recursive)\s+~(?:\s|$)",  # rm -rf ~
    r"\bmkfs\s+",
    r"\bdd\s+if=.*\bof=/dev/",
    r":\(\)\{\s*:\|\:\&\s*\};\s*:",  # fork bomb
    r"\bchmod\s+(?:777|a\+rwx)\s+/",
    r">\s*/dev/sd",
    r"\bmv\s+/\S+\s+/dev/null",
    r"\$\s*\(\s*rm\s+-rf\s+/",  # $(rm -rf /) command substitution
    r"`\s*rm\s+-rf\s+/",  # `rm -rf /` backtick command substitution
    # 补充遗漏的危险模式
    r"\bsudo\s+.*\brm\s+(?:-r(?:f)?|--recursive)\s+(?:/|~)",  # sudo rm -rf / 绕过
    r"\bsudo\s+su\b",  # sudo su 提权
    r"\b(?:sh|bash|zsh|dash)\s+-c\s+['\"].*\brm\b",  # sh -c "rm ..." 绕过
    r"\bsh\s+-c\s+['\"].*curl\b.*\|.*\b(?:sh|bash)\b",  # sh -c "curl ... | bash"
    r"\bcurl\b.*\|\s*(?:sh|bash|zsh|dash)\b",  # curl ... | bash
    r"\bwget\b.*-O\s*-\s*\|\s*(?:sh|bash|zsh|dash)\b",  # wget -O - | sh
    # 十六进制/编码绕过
    r"(?:\\x[0-9a-fA-F]{2}){4,}",  # \x 十六进制编码序列（4+连续）
    r"(?:\\u[0-9a-fA-F]{4}){2,}",  # \u Unicode 编码序列（2+连续）
    r"\b(?:eval|exec)\s+.*(?:\\x|base64\s+-d|base64\s+--decode)",  # eval $(echo ...|base64 -d) 绕过
]


def _resolve_working_dir() -> Path:
    """获取当前工作目录，优先 workspace，其次 session root，最后 cwd。"""
    workspace = current_workspace.get()
    if workspace:
        return Path(workspace)
    session_root = current_session_root.get()
    if session_root:
        return Path(session_root)
    return Path.cwd()


class ShellParams(BaseModel):
    """Shell 命令执行参数。"""

    command: str = Field(description="要执行的 shell 命令")
    timeout: int = Field(
        default=DEFAULT_TIMEOUT,
        description=f"命令执行超时秒数，默认 {DEFAULT_TIMEOUT}，最大 {MAX_TIMEOUT}",
        ge=1,
        le=MAX_TIMEOUT,
    )
    container: str | None = Field(
        default=None,
        description="Docker 容器 ID 或名称。指定后命令将在该容器内执行，而不是默认的 UV 环境",
    )


class Shell(AiasysTool):
    """在当前工作区执行单次 Shell 命令。

    同步等待命令完成并返回输出。不支持交互式命令（stdin 已关闭）。
    如需后台长时间运行任务，请使用 Monitor 工具。
    """

    name: str = "Shell"
    description: str = f"""在当前工作区执行单次 Shell 命令，同步等待完成并返回结果。

适用场景：
- 查看目录内容（`ls`、`find`）
- 查看文件元数据（`head`、`tail`、`wc`）
- 运行构建/测试命令（`npm test`、`pytest`）
- 执行 Git 操作（`git status`、`git diff`）

限制：
- 不支持交互式命令（stdin 已关闭，如需要密码输入会失败）
- 默认超时 {DEFAULT_TIMEOUT} 秒，最大 {MAX_TIMEOUT} 秒
- 输出超过 {MAX_OUTPUT_BYTES} 字节会被截断
- 每次调用在独立 shell 环境中执行，不保留变量和 cd 状态
- 禁止执行可能破坏系统的危险命令（如 `rm -rf /`）

返回：stdout + stderr 合并输出、exit_code
"""
    params: type[BaseModel] = ShellParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = ShellParams.model_validate(kwargs)

        if not params.command or not params.command.strip():
            return ToolResult(content="命令不能为空", is_error=True)

        # 危险命令检测
        for pattern in _DANGEROUS_PATTERNS:
            if re.search(pattern, params.command):
                return ToolResult(
                    content=f"命令包含危险操作，已被拦截: `{params.command[:80]}`",
                    is_error=True,
                )

        if params.container:
            import shlex

            workdir = "/workspace"
            command = (
                f"docker exec -w {shlex.quote(workdir)} "
                f"{shlex.quote(params.container)} sh -lc {shlex.quote(params.command)}"
            )
            cwd = _resolve_working_dir()
            env = _build_shell_exec_env() or {}
        else:
            plan = resolve_runtime_execution_plan()
            try:
                command, runtime_cwd = wrap_shell_command_for_runtime(
                    params.command,
                    plan=plan,
                )
            except Exception as exc:
                return ToolResult(content=f"解析运行环境失败: {exc}", is_error=True)
            cwd = runtime_cwd or _resolve_working_dir()
            env = build_runtime_shell_env(
                _build_shell_exec_env() or {},
                plan=plan,
            )

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,  # 立即关闭 stdin
                cwd=str(cwd),
                env=env,
            )
        except Exception as e:
            return ToolResult(content=f"启动进程失败: {e}", is_error=True)

        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                proc.communicate(), timeout=params.timeout
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return ToolResult(
                content=f"命令执行超时（{params.timeout}秒），已终止",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(content=f"执行异常: {e}", is_error=True)

        stdout = stdout_data.decode("utf-8", errors="replace")
        stderr = stderr_data.decode("utf-8", errors="replace")

        # 合并输出
        output = stdout
        if stderr:
            if output:
                output += "\n"
            output += f"[stderr]\n{stderr}"

        # 截断
        if len(output) > MAX_OUTPUT_BYTES:
            output = output[:MAX_OUTPUT_BYTES] + "\n\n[output truncated — exceeded limit]"

        exit_code = proc.returncode or 0
        if exit_code == 0:
            return ToolResult(
                content=output or f"命令执行成功，退出码: {exit_code}",
            )
        else:
            return ToolResult(
                content=output or f"命令执行失败，退出码: {exit_code}",
                is_error=True,
            )

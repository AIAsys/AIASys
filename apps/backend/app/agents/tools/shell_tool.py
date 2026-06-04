"""Shell 命令执行工具。

提供 Agent 执行单次同步 Shell 命令的能力。
后台长时间运行任务请使用 Monitor 工具。
"""

from __future__ import annotations

import asyncio
import locale
import os
import re
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agents.tools.local_ipython_box import build_sanitized_kernel_env
from app.core.agent_tool import AiasysTool
from app.core.encoding_utils import smart_decode
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


def _resolve_bash_path() -> str | None:
    """Windows 上优先查找 Git Bash，排除 WSL bash。"""
    if os.name != "nt":
        return "bash"
    git_bash_paths = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ]
    for p in git_bash_paths:
        if os.path.exists(p):
            return p
    which_bash = shutil.which("bash")
    if which_bash and "System32" not in which_bash and "system32" not in which_bash:
        return which_bash
    return None


def smart_decode(data: bytes) -> str:
    """尝试多种编码解码子进程输出，避免 Windows GBK 乱码。"""
    if not data:
        return ""
    for encoding in ("utf-8", locale.getpreferredencoding(False), "gbk", "gb18030"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


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
    # Windows 中文编码兜底
    if os.name == "nt":
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("LC_ALL", "C.UTF-8")
        env.setdefault("LANG", "C.UTF-8")
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

# Windows 危险命令模式
_DANGEROUS_PATTERNS_WINDOWS = [
    r"\bdel\s+(?:/\w+\s+)*[A-Z]:\\",  # del /f /s /q C:\
    r"\b(?:rd|rmdir)\s+(?:/\w+\s+)*[A-Z]:\\",  # rd /s /q C:\
    r"\bformat\s+[A-Z]:",  # format C:
    r"\bdiskpart\b",  # diskpart
    r"\bdeltree\s+[A-Z]:\\",  # deltree C:\
    r"\bshutdown\s+/[sr]\b",  # shutdown /s, shutdown /r
    r"\bbcdedit\s+/delete",  # bcdedit /delete
    r"\breg\s+delete\s+HKLM",  # reg delete HKLM
    r"\breg\s+delete\s+HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",  # 删除启动项
    r"powershell(?:\.exe)?\s+.*Remove-Item\s+.*-Recurse",  # PowerShell Remove-Item -Recurse
    r"pwsh(?:\.exe)?\s+.*Remove-Item\s+.*-Recurse",  # pwsh Remove-Item -Recurse
    r"\bcipher\s+/w:[A-Z]:",  # cipher /w:C: 擦除磁盘
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


def _shell_quote(arg: str) -> str:
    """跨平台 shell 参数引用。

    Windows 上用双引号包裹（cmd 不识别单引号），POSIX 上用 shlex.quote。
    """
    if os.name == "nt":
        # Windows: 双引号包裹，内部双引号用反斜杠转义
        escaped = arg.replace('"', '\\"')
        return f'"{escaped}"'
    import shlex

    return shlex.quote(arg)


async def _create_shell_process(command: str, **kwargs: Any) -> asyncio.subprocess.Process:
    """跨平台创建 shell 子进程。

    Windows 下默认 asyncio.create_subprocess_shell 调用 cmd.exe，
    无法执行 ls/cat/2>/dev/null 等 POSIX 命令。
    若系统存在 bash（如 Git Bash）则显式使用 bash -c 执行命令。
    Linux/macOS 保持原行为。
    """
    # 强制 UTF-8 编码，避免 Windows 中文乱码
    env = dict(kwargs.get("env") or {})
    env.setdefault("LC_ALL", "C.UTF-8")
    env.setdefault("LANG", "C.UTF-8")
    kwargs["env"] = env

    if os.name == "nt":
        import shutil

        bash_path = shutil.which("bash")
        if bash_path:
            return await asyncio.create_subprocess_exec(bash_path, "-c", command, **kwargs)
    return await asyncio.create_subprocess_shell(command, **kwargs)


async def _create_shell_process_with_interpreter(
    command: str, interpreter: str, **kwargs: Any
) -> asyncio.subprocess.Process:
    """根据 interpreter 参数创建 shell 子进程。"""
    if interpreter == "auto":
        return await _create_shell_process(command, **kwargs)

    if interpreter == "bash":
        import shutil

        bash_path = shutil.which("bash")
        if not bash_path:
            raise RuntimeError("系统未找到 bash，无法使用 interpreter='bash'")
        # 强制 UTF-8 编码
        env = dict(kwargs.get("env") or {})
        env.setdefault("LC_ALL", "C.UTF-8")
        env.setdefault("LANG", "C.UTF-8")
        kwargs["env"] = env
        return await asyncio.create_subprocess_exec(bash_path, "-c", command, **kwargs)

    if interpreter == "cmd":
        if os.name != "nt":
            raise RuntimeError("interpreter='cmd' 仅在 Windows 上可用")
        return await asyncio.create_subprocess_shell(command, **kwargs)

    if interpreter == "powershell":
        if os.name != "nt":
            raise RuntimeError("interpreter='powershell' 仅在 Windows 上可用")
        import shutil

        ps_path = shutil.which("powershell") or shutil.which("pwsh")
        if not ps_path:
            raise RuntimeError("系统未找到 PowerShell（powershell 或 pwsh）")
        return await asyncio.create_subprocess_exec(ps_path, "-Command", command, **kwargs)

    raise ValueError(f"不支持的 interpreter: {interpreter}，可选值: auto、bash、cmd、powershell")


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
    interpreter: str = Field(
        default="auto",
        description="指定使用的 shell 解释器。auto（自动检测，默认）、bash、cmd、powershell。Windows 上 bash 不可用时 fallback 到 cmd。",
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

        # 危险命令检测：按平台合并检测模式
        patterns = list(_DANGEROUS_PATTERNS)
        if os.name == "nt":
            patterns.extend(_DANGEROUS_PATTERNS_WINDOWS)
        for pattern in patterns:
            if re.search(pattern, params.command):
                return ToolResult(
                    content=f"命令包含危险操作，已被拦截: `{params.command[:80]}`",
                    is_error=True,
                )

        if params.container:
            workdir = "/workspace"
            container_quoted = _shell_quote(params.container)
            cmd_quoted = _shell_quote(params.command)
            command = f"docker exec -w {workdir} {container_quoted} sh -lc {cmd_quoted}"
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

        bash_path = _resolve_bash_path() if os.name == "nt" else None

        try:
            if bash_path:
                # Windows: 使用 Git Bash 执行，避免 cmd.exe 不支持 POSIX 命令
                proc = await asyncio.create_subprocess_exec(
                    bash_path,
                    "-c",
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.DEVNULL,  # 立即关闭 stdin
                    cwd=str(cwd),
                    env=env,
                )
            else:
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

        stdout = smart_decode(stdout_data)
        stderr = smart_decode(stderr_data)

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

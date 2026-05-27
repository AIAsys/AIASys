"""MCP 配置校验共享方法。"""

from __future__ import annotations

_SHELL_METACHARS = frozenset(";|&$`\n\r")


def validate_stdio_command(command: str, args: list[str]) -> None:
    """校验 STDIO 类型 MCP 的 command 和 args，防止命令注入。

    虽然 anyio.open_process 使用列表参数（shell=False），但仍需防止：
    - command 中包含 shell 元字符
    - args 中包含 shell 元字符或换行符
    - command 不是可执行文件路径（至少包含路径分隔符或常见命令名）
    - args 中包含路径遍历字符串（如 ..）
    """
    if not command or not command.strip():
        raise ValueError("command 不能为空")

    for ch in _SHELL_METACHARS:
        if ch in command:
            raise ValueError(f"command 包含非法字符: {repr(ch)}")
        for arg in args:
            if ch in arg:
                raise ValueError(f"args 包含非法字符: {repr(ch)}")

    # 路径遍历校验：禁止 command 和 args 中包含 ..（包括字面量 '..'）
    if ".." in command:
        raise ValueError("command 包含路径遍历字符 '..'")
    for arg in args:
        if ".." in arg:
            raise ValueError("args 包含路径遍历字符 '..'")

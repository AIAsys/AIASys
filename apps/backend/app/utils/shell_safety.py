"""Shell 命令安全检测模块。

提供统一的危险命令模式匹配，供 Shell 工具和 Monitor 工具共用。
"""

from __future__ import annotations

import re

# 危险命令模式（参考 Claude Code + Hermes）
# re.search 匹配命令中任意位置的危险子命令
DANGEROUS_PATTERNS: list[str] = [
    # === 破坏性文件操作 ===
    r"\brm\s+(?:-r(?:f)?|-f\s*-r|--recursive)\s+/(?:\s|$|\*|~)",  # rm -rf / 及其变体
    r"\brm\s+(?:-r(?:f)?|-f\s*-r|--recursive)\s+~(?:\s|$)",  # rm -rf ~
    r">\s*/dev/sd",  # 重定向覆盖磁盘设备
    r"\bmv\s+/\S+\s+/dev/null",  # mv /... /dev/null
    r"\bchmod\s+(?:777|a\+rwx)\s+/",  # chmod 777 /
    r"\bchown\s+-R\s+\S+\s+/",  # chown -R ... /
    # === 磁盘/文件系统破坏 ===
    r"\bmkfs\s+",  # mkfs 格式化
    r"\bdd\s+if=.*\bof=/dev/",  # dd 覆写块设备
    # === 资源耗尽 ===
    r":\(\)\{\s*:\|\:\&\s*\};\s*:",  # fork bomb
    # === 命令替换绕过 ===
    r"\$\s*\(\s*rm\s+-rf\s+/",  # $(rm -rf /)
    r"`\s*rm\s+-rf\s+/",  # `rm -rf /` backtick
    # === 提权绕过 ===
    r"\bsudo\s+.*\brm\s+(?:-r(?:f)?|--recursive)\s+(?:/|~)",  # sudo rm -rf /
    r"\bsudo\s+su\b",  # sudo su
    r"\bsudo\s+-i\b",  # sudo -i
    # === Shell 解释器绕过 ===
    r"\b(?:sh|bash|zsh|dash)\s+-c\s+['\"].*\brm\b",  # sh -c "rm ..."
    # === 管道下载执行 ===
    r"\bcurl\b.*\|\s*(?:sh|bash|zsh|dash)\b",  # curl ... | bash
    r"\bwget\b.*\|\s*(?:sh|bash|zsh|dash)\b",  # wget ... | bash
    r"\bwget\b.*-O\s*-\s*\|\s*(?:sh|bash|zsh|dash)\b",  # wget -O - | sh
    r"\bsh\s+-c\s+['\"].*curl\b.*\|.*\b(?:sh|bash)\b",  # sh -c "curl ... | bash"
    # === eval / exec 绕过 ===
    r"\beval\s+",  # eval 命令
    r"\bexec\s+\d+>",  # exec 文件描述符重定向攻击
    r"\beval\s+.*(?:base64\s+-d|base64\s+--decode)",  # eval ... | base64 -d
    r"\beval\s+.*(?:\\x|\\u)",  # eval 配合编码字符
    # === 文件描述符重定向攻击 ===
    r"\bexec\s+\d+<>",  # exec fd<> 读写重定向
    r"\becho\s+.*>\s*/proc/",  # echo 写入 /proc
    r">\s*/proc/sys/",  # 重定向到 /proc/sys
    # === 十六进制/编码绕过 ===
    r"(?:\\x[0-9a-fA-F]{2}){4,}",  # \x 十六进制编码序列（4+连续）
    r"(?:\\u[0-9a-fA-F]{4}){2,}",  # \u Unicode 编码序列（2+连续）
    # === 下载 + 执行组合（无管道） ===
    r"\bcurl\b.*-o\s*\S+\s*&&\s*(?:sh|bash|\.\/)",  # curl -o file && sh file
    r"\bwget\b.*-O\s*\S+\s*&&\s*(?:sh|bash|\.\/)",  # wget -O file && sh file
    # === 系统关键路径写入 ===
    r">\s*/etc/(?:passwd|shadow|sudoers|crontab|hosts)",  # 重定向覆盖系统文件
    r">>\s*/etc/(?:passwd|shadow|sudoers|crontab)",  # 追加重定向到系统文件
    r"\bchattr\b",  # chattr 修改文件属性
]


def check_dangerous_command(command: str) -> str | None:
    """检测命令是否包含危险操作模式。

    Args:
        command: 要检测的 shell 命令字符串

    Returns:
        如果检测到危险模式，返回描述字符串；否则返回 None
    """
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return f"命令包含危险操作模式: {pattern}"
    return None

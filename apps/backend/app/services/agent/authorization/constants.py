"""授权决策常量：白名单、危险模式、安全模式。"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# 只读工具白名单：任何模式下都自动放行
# ---------------------------------------------------------------------------
READONLY_TOOL_ALLOWLIST: set[str] = {
    "ReadFile",
    "ListDirectory",
    "ListSkills",
    "LoadSkill",
    "SearchStoreSkills",
    "tool_search",
    "AskUser",
    "task_list",
    "exit_plan_mode",
}

# ---------------------------------------------------------------------------
# 高风险工具：smart 模式下默认询问
# ---------------------------------------------------------------------------
HIGH_RISK_TOOLS: set[str] = {
    "Shell",
    "EnableSkill",
    "DisableSkill",
    "InstallMCPServer",
    "UninstallMCPServer",
    "InstallConnector",
    "SetEnvVar",
    "DeleteEnvVar",
    "CreateAutoTask",
    "ControlAutoTask",
}

# ---------------------------------------------------------------------------
# Hardline 模式：不可绕过的纯破坏性命令
# 任何模式下（包括 full_auto/YOLO）都直接 BLOCK
#
# 只收录"没有正当使用场景、执行即造成不可逆系统破坏"的命令。
# 高危但有合法用途的操作——删普通子目录（rm -rf build）、装软件的 curl|bash、
# sudo/su 提权、带 $TOKEN 的 curl 调 API、nmap/nc 网络诊断等——不放这里；
# 它们会落到 shell_policy，按授权模式改为"需确认"（full_auto 放行），
# 既不误伤日常操作，又保留一道人工确认闸。
# ---------------------------------------------------------------------------
HARDLINE_SHELL_PATTERNS: list[re.Pattern] = [
    # 删除根目录 / 家目录：rm -rf / 、rm -rf /* 、rm -rf ~（不可逆、无正当理由）
    re.compile(r"\brm\s+(?:-r(?:f)?|-fr|-f\s*-r|--recursive)\s+/(?:\s|$|\*|~)", re.IGNORECASE),
    re.compile(r"\brm\s+(?:-r(?:f)?|-fr|-f\s*-r|--recursive)\s+~(?:\s|$)", re.IGNORECASE),
    # 格式化文件系统
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    # 直接写裸磁盘设备
    re.compile(r"\bdd\s+if=.*of=/dev/", re.IGNORECASE),
    # fork bomb
    re.compile(r":\s*\(\)\s*\{\s*.*\}\s*;\s*\b", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# 安全命令模式：smart/auto 下可考虑自动放行
# 注意：匹配后仍需检查命令替换（$() / ``），防止绕过
# ---------------------------------------------------------------------------
SAFE_SHELL_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*git\s+(status|log|diff|show|branch|remote|config\s+--get)\b", re.IGNORECASE),
    re.compile(r"^\s*ls\b", re.IGNORECASE),
    re.compile(r"^\s*cat\b", re.IGNORECASE),
    re.compile(r"^\s*find\b", re.IGNORECASE),
    re.compile(r"^\s*grep\b", re.IGNORECASE),
    re.compile(r"^\s*echo\b", re.IGNORECASE),
    re.compile(r"^\s*pwd\b", re.IGNORECASE),
    re.compile(r"^\s*which\b", re.IGNORECASE),
    re.compile(r"^\s*python\s+--version\b|\s*python\s+-V\b", re.IGNORECASE),
    re.compile(r"^\s*node\s+--version\b|\s*node\s+-v\b", re.IGNORECASE),
]

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
    "SetEnvVar",
    "DeleteEnvVar",
    "CreateAutoTask",
    "ControlAutoTask",
}

# ---------------------------------------------------------------------------
# Hardline 模式：不可绕过的破坏性命令
# 任何模式下（包括 full_auto/YOLO）都直接 BLOCK
# ---------------------------------------------------------------------------
HARDLINE_SHELL_PATTERNS: list[re.Pattern] = [
    # 系统目录写入/删除
    re.compile(r"\brm\s+.*-(?:[a-zA-Z]*[rf]|[rf][a-zA-Z]*)", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=.*of=/dev/", re.IGNORECASE),
    # 提权
    re.compile(r"\bsudo\s+", re.IGNORECASE),
    re.compile(r"\bsu\s+-", re.IGNORECASE),
    # 远程脚本执行
    re.compile(r"\b(curl|wget)\b.*\|\s*(bash|sh|zsh)\b", re.IGNORECASE),
    # 网络监听/端口扫描
    re.compile(r"\bnc\s+-[lL]\b", re.IGNORECASE),
    re.compile(r"\bnmap\b", re.IGNORECASE),
    # fork bomb
    re.compile(r":\s*\(\)\s*\{\s*.*\}\s*;\s*\b", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# 凭证外传：直接 BLOCK
# ---------------------------------------------------------------------------
CREDENTIAL_EXFIL_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bcurl\b.*\$(?:SECRET|TOKEN|PWD|PASSWORD|API_KEY)", re.IGNORECASE),
    re.compile(r"\bwget\b.*\$(?:SECRET|TOKEN|PWD|PASSWORD|API_KEY)", re.IGNORECASE),
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

"""授权策略链。

每个策略函数接收 CapabilityAuthorizationRequest，返回：
- CapabilityAuthorizationResult：该策略做出了决策
- None：该策略不处理，PASS 给下一个策略

策略链按固定优先级遍历，第一个非 None 的结果直接生效。
"""

from __future__ import annotations

from typing import Callable

from .constants import (
    CREDENTIAL_EXFIL_PATTERNS,
    HARDLINE_SHELL_PATTERNS,
    READONLY_TOOL_ALLOWLIST,
    SAFE_SHELL_PATTERNS,
)
from .types import (
    AuthorizationDecision,
    AuthorizationMode,
    CapabilityAuthorizationRequest,
    CapabilityAuthorizationResult,
    RiskLevel,
)

PolicyFn = Callable[[CapabilityAuthorizationRequest], CapabilityAuthorizationResult | None]


def _result(
    decision: AuthorizationDecision,
    reason: str = "",
    prompt: str = "",
    denial: str = "",
    pattern_key: str | None = None,
) -> CapabilityAuthorizationResult:
    """构造策略结果。"""
    return CapabilityAuthorizationResult(
        decision=decision,
        reason=reason,
        confirmation_prompt=prompt,
        denial_message=denial,
        pattern_key=pattern_key,
    )


def _extract_command(request: CapabilityAuthorizationRequest) -> str:
    """从请求中提取 Shell 命令字符串。"""
    command = request.arguments.get("command", "")
    return str(command) if isinstance(command, str) else ""


def _has_command_substitution(command: str) -> bool:
    """检测命令中是否包含命令替换语法（可能被绕过）。"""
    return "$(" in command or "`" in command


# ---------------------------------------------------------------------------
# 策略 1：只读白名单
# ---------------------------------------------------------------------------
def readonly_allowlist(
    request: CapabilityAuthorizationRequest,
) -> CapabilityAuthorizationResult | None:
    """只读工具和白名单内的操作任何模式都自动放行。"""
    if request.tool_name in READONLY_TOOL_ALLOWLIST:
        return _result(AuthorizationDecision.ALLOW, f"{request.tool_name} 属于只读白名单")
    if request.risk_level == RiskLevel.READONLY:
        return _result(AuthorizationDecision.ALLOW, "只读操作自动放行")
    return None


# ---------------------------------------------------------------------------
# 策略 2：Shell Hardline（不可绕过）
# ---------------------------------------------------------------------------
def hardline_shell(request: CapabilityAuthorizationRequest) -> CapabilityAuthorizationResult | None:
    """Shell 命令的硬拦截：破坏性/危险命令，任何模式下都 BLOCK。"""
    if request.tool_name != "Shell":
        return None
    command = _extract_command(request)
    for pattern in HARDLINE_SHELL_PATTERNS:
        if pattern.search(command):
            return _result(
                AuthorizationDecision.BLOCK,
                "检测到破坏性/危险 Shell 命令",
                denial="该命令涉及系统安全边界，已被拦截。如需执行，请使用受控的运行时环境或手动操作。",
                pattern_key="shell_hardline",
            )
    for pattern in CREDENTIAL_EXFIL_PATTERNS:
        if pattern.search(command):
            return _result(
                AuthorizationDecision.BLOCK,
                "检测到凭证外传风险",
                denial="该命令可能泄露敏感凭证，已被拦截。",
                pattern_key="shell_credential_exfil",
            )
    return None


# ---------------------------------------------------------------------------
# 策略 3：Shell 一般分析
# ---------------------------------------------------------------------------
def shell_policy(request: CapabilityAuthorizationRequest) -> CapabilityAuthorizationResult | None:
    """非 Hardline 的 Shell 命令按模式处理。"""
    if request.tool_name != "Shell":
        return None
    command = _extract_command(request)
    mode = request.authorization_mode

    # full_auto：非 hardline 全部放行
    if mode == AuthorizationMode.FULL_AUTO:
        return _result(
            AuthorizationDecision.ALLOW,
            "full_auto 模式自动放行非破坏性命令",
            pattern_key="shell_command",
        )

    # 检查是否匹配安全模式
    is_safe = False
    for pattern in SAFE_SHELL_PATTERNS:
        if pattern.search(command):
            is_safe = True
            break

    # 安全命令在 smart/auto 下放行，但包含命令替换时降级为询问
    if is_safe and not _has_command_substitution(command):
        if mode in (AuthorizationMode.SMART, AuthorizationMode.AUTO):
            return _result(
                AuthorizationDecision.ALLOW,
                "低风险 Shell 命令在 smart/auto 下自动放行",
                pattern_key="shell_safe",
            )

    # manual：非白名单都询问
    if mode == AuthorizationMode.MANUAL:
        return _result(
            AuthorizationDecision.ASK,
            "manual 模式下 Shell 命令需要确认",
            f"是否允许执行 Shell 命令：\n```\n{command[:200]}\n```",
            pattern_key="shell_command",
        )

    # smart/auto 下对未知命令询问
    return _result(
        AuthorizationDecision.ASK,
        "未分类的 Shell 命令需要确认",
        f"是否允许执行 Shell 命令：\n```\n{command[:200]}\n```",
        pattern_key="shell_command",
    )


# ---------------------------------------------------------------------------
# 策略 4：文件写入
# ---------------------------------------------------------------------------
def file_write_policy(
    request: CapabilityAuthorizationRequest,
) -> CapabilityAuthorizationResult | None:
    """WriteFile / StrReplaceFile / CreateFile 的写入授权。"""
    if request.tool_name not in ("WriteFile", "StrReplaceFile", "CreateFile"):
        return None
    path = request.arguments.get("path", "")
    if not isinstance(path, str):
        path = str(path)
    mode = request.authorization_mode

    # 全局写入
    if path.startswith("/global/") or "/global_workspace/" in path:
        if mode == AuthorizationMode.FULL_AUTO:
            return _result(
                AuthorizationDecision.ALLOW,
                "full_auto 模式下全局写入自动放行",
                pattern_key="global_write",
            )
        return _result(
            AuthorizationDecision.ASK,
            "全局工作区写入需要确认",
            f"是否允许写入全局工作区文件：{path}",
            pattern_key="global_write",
        )

    # workspace 写入
    if mode in (AuthorizationMode.FULL_AUTO, AuthorizationMode.AUTO):
        return _result(
            AuthorizationDecision.ALLOW,
            f"{mode.value} 模式下工作区写入自动放行",
            pattern_key="workspace_write",
        )
    if mode == AuthorizationMode.SMART:
        return _result(
            AuthorizationDecision.ALLOW,
            "smart 模式下工作区写入自动放行",
            pattern_key="workspace_write",
        )

    return _result(
        AuthorizationDecision.ASK,
        "manual 模式下文件写入需要确认",
        f"是否允许写入文件：{path}",
        pattern_key="workspace_write",
    )


# ---------------------------------------------------------------------------
# 策略 5：Skill 启用/禁用
# ---------------------------------------------------------------------------
def skill_activation_policy(
    request: CapabilityAuthorizationRequest,
) -> CapabilityAuthorizationResult | None:
    """EnableSkill / DisableSkill 的授权。"""
    if request.tool_name not in ("EnableSkill", "DisableSkill"):
        return None
    mode = request.authorization_mode

    # DisableSkill 比启用安全
    if request.tool_name == "DisableSkill":
        if mode in (AuthorizationMode.SMART, AuthorizationMode.AUTO, AuthorizationMode.FULL_AUTO):
            return _result(
                AuthorizationDecision.ALLOW,
                "Skill 禁用在 smart/auto/full_auto 下自动放行",
                pattern_key="skill_disable",
            )
        return _result(
            AuthorizationDecision.ASK,
            "manual 模式下 Skill 禁用需要确认",
            f"是否禁用 Skill '{request.arguments.get('name', '')}'？",
            pattern_key="skill_disable",
        )

    # EnableSkill
    scope = request.arguments.get("scope", "workspace")
    skill_name = request.arguments.get("name", "")
    sec = request.skill_security

    if scope == "global":
        if mode == AuthorizationMode.FULL_AUTO:
            return _result(
                AuthorizationDecision.ALLOW,
                "full_auto 模式下全局 Skill 启用自动放行",
                pattern_key="skill_enable_global",
            )
        return _result(
            AuthorizationDecision.ASK,
            "全局默认 Skill 启用需要确认",
            f"是否将 Skill '{skill_name}' 启用到全局默认？",
            pattern_key="skill_enable_global",
        )

    if mode in (AuthorizationMode.FULL_AUTO, AuthorizationMode.AUTO):
        return _result(
            AuthorizationDecision.ALLOW,
            f"{mode.value} 模式下 Skill 启用自动放行",
            pattern_key="skill_enable_workspace",
        )
    if mode == AuthorizationMode.MANUAL:
        return _result(
            AuthorizationDecision.ASK,
            "manual 模式下 Skill 启用需要确认",
            f"是否启用 Skill '{skill_name}'？",
            pattern_key="skill_enable_workspace",
        )

    # smart：基于安全元数据
    if not sec:
        return _result(
            AuthorizationDecision.ASK,
            "缺少 Skill 安全元数据，保守处理",
            f"是否在当前工作区启用 Skill '{skill_name}'？",
            pattern_key="skill_enable_workspace",
        )

    risk = sec.get("risk_level", "medium")
    has_scripts = sec.get("has_scripts", False)
    uses_shell = sec.get("uses_shell", False)
    installs_deps = sec.get("installs_dependencies", False)
    writes_global = sec.get("writes_global", False)
    adds_tools = sec.get("adds_tools", [])
    uses_network = sec.get("uses_network", False)

    if (
        risk == "low"
        and not has_scripts
        and not uses_shell
        and not installs_deps
        and not writes_global
        and not uses_network
        and not adds_tools
    ):
        return _result(
            AuthorizationDecision.ALLOW,
            "Skill 风险等级为 low 且无脚本/Shell/依赖/网络/新增工具",
            pattern_key="skill_enable_workspace",
        )

    if (
        risk == "medium"
        and not uses_shell
        and not installs_deps
        and not writes_global
        and not uses_network
    ):
        return _result(
            AuthorizationDecision.ALLOW,
            "Skill 风险等级为 medium 且无 Shell/依赖/global 写入/网络",
            pattern_key="skill_enable_workspace",
        )

    reasons = []
    if has_scripts:
        reasons.append("含脚本")
    if uses_shell:
        reasons.append("调用 Shell")
    if installs_deps:
        reasons.append("安装依赖")
    if writes_global:
        reasons.append("写全局工作区")
    if uses_network:
        reasons.append("使用网络")
    if adds_tools:
        reasons.append(f"新增工具 {adds_tools}")
    reason_str = "、".join(reasons) if reasons else f"风险等级 {risk}"

    return _result(
        AuthorizationDecision.ASK,
        f"Skill 启用需要确认：{reason_str}",
        f"是否在当前工作区启用 Skill '{skill_name}'？（{reason_str}）",
        pattern_key="skill_enable_workspace",
    )


# ---------------------------------------------------------------------------
# 策略 6：MCP 安装/卸载
# ---------------------------------------------------------------------------
def mcp_install_policy(
    request: CapabilityAuthorizationRequest,
) -> CapabilityAuthorizationResult | None:
    if request.tool_name not in ("InstallMCPServer", "UninstallMCPServer"):
        return None
    if request.authorization_mode == AuthorizationMode.FULL_AUTO:
        return _result(
            AuthorizationDecision.ALLOW,
            "full_auto 模式下 MCP 安装自动放行",
            pattern_key="mcp_install",
        )
    return _result(
        AuthorizationDecision.ASK,
        "MCP 服务器安装/卸载需要确认",
        "是否安装/卸载 MCP 服务器？该操作可能影响系统安全。",
        pattern_key="mcp_install",
    )


# ---------------------------------------------------------------------------
# 策略 7：环境变量
# ---------------------------------------------------------------------------
def env_var_policy(request: CapabilityAuthorizationRequest) -> CapabilityAuthorizationResult | None:
    if request.tool_name not in ("SetEnvVar", "DeleteEnvVar"):
        return None
    if request.authorization_mode in (
        AuthorizationMode.SMART,
        AuthorizationMode.AUTO,
        AuthorizationMode.FULL_AUTO,
    ):
        return _result(
            AuthorizationDecision.ALLOW,
            "环境变量变更在 smart/auto/full_auto 下自动放行",
            pattern_key="env_var",
        )
    return _result(
        AuthorizationDecision.ASK, "manual 模式下环境变量变更需要确认", pattern_key="env_var"
    )


# ---------------------------------------------------------------------------
# 策略 8：AutoTask
# ---------------------------------------------------------------------------
def auto_task_policy(
    request: CapabilityAuthorizationRequest,
) -> CapabilityAuthorizationResult | None:
    if request.tool_name not in ("CreateAutoTask", "ControlAutoTask"):
        return None
    if request.authorization_mode in (
        AuthorizationMode.SMART,
        AuthorizationMode.AUTO,
        AuthorizationMode.FULL_AUTO,
    ):
        return _result(
            AuthorizationDecision.ALLOW,
            "AutoTask 在 smart/auto/full_auto 下自动放行",
            pattern_key="auto_task",
        )
    return _result(
        AuthorizationDecision.ASK, "manual 模式下 AutoTask 操作需要确认", pattern_key="auto_task"
    )


# ---------------------------------------------------------------------------
# 策略 9：运行时环境
# ---------------------------------------------------------------------------
def runtime_env_policy(
    request: CapabilityAuthorizationRequest,
) -> CapabilityAuthorizationResult | None:
    if request.tool_name != "RuntimeEnvironment":
        return None
    action = request.arguments.get("action", "")
    if action in ("inspect", "list"):
        return _result(
            AuthorizationDecision.ALLOW,
            "运行时环境只读操作自动放行",
            pattern_key="runtime_env_read",
        )
    mode = request.authorization_mode
    if mode in (AuthorizationMode.AUTO, AuthorizationMode.FULL_AUTO):
        return _result(
            AuthorizationDecision.ALLOW,
            f"{mode.value} 模式下运行时环境变更自动放行",
            pattern_key="runtime_env_modify",
        )
    return _result(
        AuthorizationDecision.ASK, "运行时环境变更需要确认", pattern_key="runtime_env_modify"
    )


# ---------------------------------------------------------------------------
# 策略 10：子 Agent 创建
# ---------------------------------------------------------------------------
def subagent_policy(
    request: CapabilityAuthorizationRequest,
) -> CapabilityAuthorizationResult | None:
    if request.tool_name not in ("SpawnSubAgent", "CreateSubAgent"):
        return None
    if request.authorization_mode in (
        AuthorizationMode.SMART,
        AuthorizationMode.AUTO,
        AuthorizationMode.FULL_AUTO,
    ):
        return _result(
            AuthorizationDecision.ALLOW,
            "子 Agent 创建在 smart/auto/full_auto 下自动放行",
            pattern_key="subagent_create",
        )
    return _result(
        AuthorizationDecision.ASK,
        "manual 模式下子 Agent 创建需要确认",
        pattern_key="subagent_create",
    )


# ---------------------------------------------------------------------------
# 策略 11：通用风险兜底
# ---------------------------------------------------------------------------
def generic_risk_policy(
    request: CapabilityAuthorizationRequest,
) -> CapabilityAuthorizationResult | None:
    """按风险等级和授权模式做通用兜底决策。"""
    mode = request.authorization_mode
    risk = request.risk_level
    pk = f"tool_{request.tool_name}"

    if mode == AuthorizationMode.FULL_AUTO:
        if risk == RiskLevel.CRITICAL:
            return _result(
                AuthorizationDecision.BLOCK,
                "full_auto 也不允许极高风险操作",
                denial="该操作风险等级为 critical，已被系统硬拦截。",
                pattern_key="critical_tool",
            )
        return _result(
            AuthorizationDecision.ALLOW, "full_auto 模式下非 critical 操作自动放行", pattern_key=pk
        )

    if mode == AuthorizationMode.AUTO:
        if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return _result(
                AuthorizationDecision.DENY,
                "auto 模式下高风险操作自动拒绝",
                denial="该操作风险较高，当前授权模式（auto）已自动拒绝。如需执行，请切换到 smart 或手动授权。",
                pattern_key=f"high_risk_{pk}",
            )
        return _result(AuthorizationDecision.ALLOW, "auto 模式下中低风险自动放行", pattern_key=pk)

    if mode == AuthorizationMode.SMART:
        if risk == RiskLevel.CRITICAL:
            return _result(
                AuthorizationDecision.BLOCK,
                "smart 模式下 critical 操作硬拦截",
                denial="该操作风险等级为 critical，已被系统拦截。",
                pattern_key="critical_tool",
            )
        if risk == RiskLevel.HIGH:
            return _result(
                AuthorizationDecision.ASK,
                "smart 模式下高风险操作需要确认",
                pattern_key=f"high_risk_{pk}",
            )
        return _result(AuthorizationDecision.ALLOW, "smart 模式下低中风险自动放行", pattern_key=pk)

    # manual
    if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return _result(
            AuthorizationDecision.ASK,
            "manual 模式下高风险操作需要确认",
            pattern_key=f"high_risk_{pk}",
        )
    return _result(AuthorizationDecision.ASK, "manual 模式下所有副作用操作需要确认", pattern_key=pk)


# ---------------------------------------------------------------------------
# 策略 0：Plan Mode 硬拦截
# ---------------------------------------------------------------------------
# Plan Mode 是高于权限模式的独立状态：无论当前是 manual/smart/auto/full_auto，
# 只要处于 Plan Mode，就必须先完成计划审批，才能执行有副作用的操作。
PLAN_MODE_BLOCKED_TOOLS: set[str] = {
    "Task",
    "TaskTool",
    "AgentTool",
    "CreateSubagentTool",
    "SpawnSubagentTool",
    "DeleteSubagentTool",
    "UpdateSubagentTool",
    "ListSubagentsTool",
    "TaskStop",
    "CronCreate",
    "CronDelete",
    "SpawnMonitorTool",
    "ManageMonitorTool",
    "RuntimeEnvironment",
    "SetEnvVar",
    "DeleteEnvVar",
    "CreateAutoTask",
    "ControlAutoTask",
    "EnableSkill",
    "DisableSkill",
    "InstallMCPServer",
    "UninstallMCPServer",
    "MemoryTool",
}


def plan_mode_policy(
    request: CapabilityAuthorizationRequest,
) -> CapabilityAuthorizationResult | None:
    """Plan Mode 下只允许只读探索和写入当前计划文件。"""
    if not request.plan_mode_active:
        return None

    tool_name = request.tool_name

    # exit_plan_mode 必须能执行，否则无法退出 Plan Mode
    if tool_name == "exit_plan_mode":
        return None

    # 只读风险等级工具放行（由后续策略或本策略的只读判断处理）
    if request.risk_level == RiskLevel.READONLY:
        return None

    # 文件写入类工具：Plan Mode 下禁止。
    # 计划文件由 exit_plan_mode 工具自身写入，不经过 WriteFile/StrReplaceFile。
    if tool_name in ("WriteFile", "StrReplaceFile", "CreateFile"):
        return _result(
            AuthorizationDecision.DENY,
            "Plan Mode 下禁止文件写入",
            denial=(
                "当前处于 Plan Mode，文件写入已被禁止。"
                "请先调用 exit_plan_mode 提交计划并等待用户批准。"
            ),
            pattern_key="plan_mode_write_guard",
        )

    # 显式禁止跨 Plan 边界的副作用工具
    if tool_name in PLAN_MODE_BLOCKED_TOOLS:
        return _result(
            AuthorizationDecision.DENY,
            f"Plan Mode 下不允许使用 {tool_name}",
            denial=(
                f"{tool_name} 在 Plan Mode 下不可用，"
                "因为它可能产生超出计划范围的副作用。"
                "请先调用 exit_plan_mode 提交计划并等待用户批准。"
            ),
            pattern_key="plan_mode_blocked_tool",
        )

    # 其他工具交给后续策略处理
    return None


# ---------------------------------------------------------------------------
# 策略链（按优先级排列）
# ---------------------------------------------------------------------------
POLICY_CHAIN: list[PolicyFn] = [
    plan_mode_policy,
    readonly_allowlist,
    hardline_shell,
    shell_policy,
    file_write_policy,
    skill_activation_policy,
    mcp_install_policy,
    env_var_policy,
    auto_task_policy,
    runtime_env_policy,
    subagent_policy,
    generic_risk_policy,
]

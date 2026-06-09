"""能力授权决策服务。

使用策略链（Policy Chain）架构，按固定优先级遍历策略，
第一个做出决策的策略直接生效。
"""

from __future__ import annotations

from .policies import POLICY_CHAIN
from .types import (
    AuthorizationDecision,
    CapabilityAuthorizationRequest,
    CapabilityAuthorizationResult,
)


class CapabilityAuthorizationService:
    """统一能力授权决策服务。

    所有有副作用的能力调用（工具、Skill、MCP、运行环境、AutoTask、子 Agent、
    全局写入、外部系统）在真正执行前都应该经过本服务决策。
    """

    @classmethod
    def decide(
        cls,
        request: CapabilityAuthorizationRequest,
    ) -> CapabilityAuthorizationResult:
        """对一次能力调用做出授权决策。"""
        for policy in POLICY_CHAIN:
            result = policy(request)
            if result is not None:
                return result

        # 兜底（理论上不会走到这里，因为 generic_risk_policy 已兜底）
        return CapabilityAuthorizationResult(
            decision=AuthorizationDecision.ASK,
            reason="未匹配任何策略，默认需要确认",
        )

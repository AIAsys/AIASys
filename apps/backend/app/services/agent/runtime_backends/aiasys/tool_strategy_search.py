"""SearchToolStrategy — 基于 tool_search 的渐进式工具发现策略。

用于不支持 defer_loading 的模型 (Kimi/GPT/Gemini/...)。

只发送核心工具 + tool_search。其余 deferred 工具不发送，
模型通过 tool_search 按需发现后，下一轮自动激活。
激活工具超过硬上限时 LRU 淘汰。
"""

from __future__ import annotations

import logging
from typing import Any

from .tool_registry import ToolRegistry
from .tool_strategy import ToolStrategy

logger = logging.getLogger(__name__)

# 激活工具硬上限
ACTIVATED_TOOL_LIMIT = 128


class SearchToolStrategy(ToolStrategy):
    """工具搜索策略 — 用于不支持 defer_loading 的模型。

    核心工具 + tool_search 始终可用。
    其余工具不发送，模型调 tool_search 发现后自动激活。
    激活工具超过 ACTIVATED_TOOL_LIMIT 时 LRU 淘汰最久未用的。
    """

    def __init__(self) -> None:
        self._tool_search: Any = None
        self._registry: ToolRegistry | None = None
        self._activated: set[str] = set()  # 已激活的工具名
        self._last_activated_turn: dict[str, int] = {}  # LRU 追踪
        self._turn = 0

    def setup_registry(self, registry: ToolRegistry) -> None:
        """注册 tool_search 工具（带激活回调）。"""
        from .tools.tool_search_tool import ToolSearchTool

        self._registry = registry
        self._tool_search = ToolSearchTool.from_registry(
            registry, on_results=self._on_tools_discovered
        )
        try:
            registry.register(self._tool_search)
        except ValueError:
            logger.debug("tool_search 已注册，跳过")

    def _on_tools_discovered(self, tool_names: list[str]) -> None:
        """tool_search 结果回调：激活发现的工具。"""
        for name in tool_names:
            self._activated.add(name)
            self._last_activated_turn[name] = self._turn
        if tool_names:
            logger.debug("SearchTool: activated %d tools via tool_search", len(tool_names))

    def prepare_tools(self, registry: ToolRegistry) -> list[dict[str, Any]]:
        self._turn += 1
        non_deferred, deferred = registry.get_openai_schemas_split()
        return self._prepare_from_split(non_deferred, deferred)

    def prepare_tools_filtered(
        self,
        registry: ToolRegistry,
        allowed_names: set[str],
    ) -> list[dict[str, Any]]:
        self._turn += 1
        non_deferred, deferred = registry.get_openai_schemas_split_filtered(allowed_names)
        return self._prepare_from_split(non_deferred, deferred)

    def _prepare_from_split(
        self,
        non_deferred: list[dict[str, Any]],
        deferred: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:

        # 同步 tool_search 的可搜索列表
        if self._tool_search is not None:
            self._tool_search.update_schemas(deferred)

        total_deferred = len(deferred)
        if total_deferred == 0:
            return non_deferred

        # 构建 deferred 工具的 name→schema 映射
        deferred_map: dict[str, dict[str, Any]] = {}
        for entry in deferred:
            name = entry.get("function", {}).get("name", "")
            if name:
                deferred_map[name] = entry

        # 筛选已激活的 deferred 工具
        activated_schemas: list[dict[str, Any]] = []
        stale: list[str] = []
        for name in self._activated:
            schema = deferred_map.get(name)
            if schema is not None:
                self._last_activated_turn[name] = self._turn
                activated_schemas.append(schema)
            else:
                stale.append(name)
        for name in stale:
            self._activated.discard(name)
            self._last_activated_turn.pop(name, None)

        # LRU 淘汰
        overflow = len(activated_schemas) - ACTIVATED_TOOL_LIMIT
        if overflow > 0:
            sorted_names = sorted(
                self._activated,
                key=lambda n: self._last_activated_turn.get(n, 0),
            )
            for name in sorted_names[:overflow]:
                self._activated.discard(name)
                self._last_activated_turn.pop(name, None)
            # 重新过滤激活的 schemas
            activated_schemas = [
                s for s in activated_schemas if s.get("function", {}).get("name") in self._activated
            ]

        logger.debug(
            "SearchTool: turn=%d, non_deferred=%d, activated=%d/%d deferred",
            self._turn,
            len(non_deferred),
            len(activated_schemas),
            total_deferred,
        )
        return non_deferred + activated_schemas

    def get_system_prompt_additions(self) -> str:
        if self._registry is None:
            return ""
        _non_def, deferred = self._registry.get_openai_schemas_split()
        if not deferred:
            return ""

        # 生成分类预览
        categories = _build_category_summary(deferred)
        return (
            "\n\n## Available Tools (Progressive Discovery)\n"
            f"You have {len(deferred)} additional tools available through `tool_search`.\n\n"
            "**How to discover and use tools:**\n"
            "1. `tool_search(action='list_tools')` — browse all tools by category\n"
            "2. `tool_search(action='search_tools', query='what you need')` — find tools by description\n"
            "3. `tool_search(action='get_tool_description', tool_names=['ToolName'])` — get full parameters\n"
            "4. Once a tool is discovered, it becomes available for direct use in the next turn\n\n"
            "**Available categories:**\n"
            f"{categories}"
        )

    @property
    def strategy_name(self) -> str:
        return "search"


def _build_category_summary(deferred_schemas: list[dict[str, Any]]) -> str:
    """生成 deferred 工具分类摘要。"""
    categories: dict[str, list[str]] = {}
    for entry in deferred_schemas:
        fn = entry.get("function", {})
        name = fn.get("name", "")
        if name.startswith("mcp__"):
            parts = name.split("__", 2)
            prefix = f"mcp/{parts[1]}" if len(parts) >= 2 else "mcp"
        elif "_" in name:
            prefix = name.split("_")[0]
        else:
            prefix = "other"
        categories.setdefault(prefix, []).append(name)

    lines: list[str] = []
    for prefix in sorted(categories):
        tool_names = sorted(categories[prefix])
        if len(tool_names) <= 3:
            lines.append(f"- **{prefix}**/*: {', '.join(tool_names)}")
        else:
            lines.append(
                f"- **{prefix}**/* ({len(tool_names)} tools, e.g. {', '.join(tool_names[:3])}...)"
            )
    return "\n".join(lines)

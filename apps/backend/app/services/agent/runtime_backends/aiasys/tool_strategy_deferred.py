"""DeferredToolStrategy — Anthropic defer_loading + tool_search 策略。

仅当检测到 Anthropic 原生端点 + Claude 4.5+ 时使用。
将工具分为 non_deferred（始终可用）和 deferred（需 tool_search 发现）。
"""

from __future__ import annotations

import logging
from typing import Any

from .tool_registry import NON_DEFERRED_TOOL_NAMES, ToolRegistry
from .tool_strategy import ToolStrategy

logger = logging.getLogger(__name__)

TOOL_SEARCH_INSTRUCTIONS = """\
<tool_search_instructions>
You have access to a large set of tools, but only a core subset is available immediately.
The remaining tools are *deferred* — you MUST use the `tool_search` tool to load them
before calling them directly.

**Rules:**
- You MUST call `tool_search` to discover deferred tools BEFORE calling them
- Calling a deferred tool without loading it first will fail
- Describe what capability you need in natural language — the search uses semantic similarity
- Do NOT call `tool_search` again for a tool already returned by a previous search
- If a search returns no matching tools, the tool is not available — do not retry

**Example:**
- "search github issues" — finds GitHub-related tools
- "create a database table" — finds database tools
- "run a notebook cell" — finds notebook execution tools

**Available deferred tool categories (for search inspiration):**
{tool_categories}
</tool_search_instructions>"""


def _categorize_deferred_tools(deferred_schemas: list[dict[str, Any]]) -> list[str]:
    """从 deferred 工具列表中提取分类提示，帮助模型知道该搜什么。"""
    names = sorted(s.get("function", {}).get("name", "") for s in deferred_schemas)
    # 简单按前缀分类
    categories: dict[str, list[str]] = {}
    for name in names:
        prefix = name.split("_")[0] if "_" in name else name.split(":")[-1].split(".")[0]
        prefix = prefix or "other"
        categories.setdefault(prefix, []).append(name)

    lines: list[str] = []
    for prefix, tool_names in sorted(categories.items()):
        if len(tool_names) <= 1:
            lines.append(f"- {tool_names[0]}")
        else:
            lines.append(
                f"- {prefix}/* ({len(tool_names)} tools: {', '.join(tool_names[:3])}{'...' if len(tool_names) > 3 else ''})"
            )
    return lines


class DeferredToolStrategy(ToolStrategy):
    """Anthropic defer_loading 策略。

    将工具分为：
    - non_deferred: 核心工具（白名单），始终完整发送
    - deferred: 其余工具，标记 defer_loading: true，需 tool_search 发现
    """

    def __init__(self, client: Any) -> None:
        self._model = getattr(client, "model", "unknown")
        self._tool_search: Any = None
        self._registry: ToolRegistry | None = None

    def setup_registry(self, registry: ToolRegistry) -> None:
        """注册 tool_search 工具到 registry。"""
        from .tools.tool_search_tool import ToolSearchTool

        self._registry = registry
        self._tool_search = ToolSearchTool.from_registry(registry)
        try:
            registry.register(self._tool_search)
        except ValueError:
            logger.debug("tool_search 已注册，跳过")

    def get_system_prompt_additions(self) -> str:
        if self._registry is None:
            return ""
        return self.build_tool_search_instructions(self._registry)

    def prepare_tools(self, registry: ToolRegistry) -> list[dict[str, Any]]:
        non_deferred, deferred = registry.get_openai_schemas_split()
        return self._prepare_from_split(non_deferred, deferred)

    def prepare_tools_filtered(
        self,
        registry: ToolRegistry,
        allowed_names: set[str],
    ) -> list[dict[str, Any]]:
        non_deferred, deferred = registry.get_openai_schemas_split_filtered(allowed_names)
        return self._prepare_from_split(non_deferred, deferred)

    def _prepare_from_split(
        self,
        non_deferred: list[dict[str, Any]],
        deferred: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:

        # 同步 tool_search 工具的可搜索列表
        if self._tool_search is not None:
            self._tool_search.update_schemas(deferred)

        # 标记 deferred 工具
        for entry in deferred:
            entry["defer_loading"] = True

        # 将 tool_search 自身的 schema 加入 non_deferred（如果 registry 中没有）
        existing_names = {s.get("function", {}).get("name") for s in non_deferred}
        if "tool_search" not in existing_names:
            non_deferred.append(self._build_tool_search_schema(deferred))

        logger.debug(
            "DeferredToolStrategy: non_deferred=%d, deferred=%d, model=%s",
            len(non_deferred),
            len(deferred),
            self._model,
        )
        return non_deferred + deferred

    def build_tool_search_instructions(self, registry: ToolRegistry) -> str:
        """生成 tool_search 使用说明，根据实际工具列表填充分类。"""
        _non_deferred, deferred = registry.get_openai_schemas_split()
        if not deferred:
            return ""
        categories = _categorize_deferred_tools(deferred)
        return TOOL_SEARCH_INSTRUCTIONS.format(
            tool_categories="\n".join(categories),
        )

    @staticmethod
    def _build_tool_search_schema(
        deferred: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """构建 tool_search 工具的 OpenAI schema。

        tool_search 让模型通过自然语言描述搜索延迟加载的工具。
        """
        # 生成可搜索工具列表（name + description 摘要）
        tool_catalog = []
        for entry in deferred:
            fn = entry.get("function", {})
            name = fn.get("name", "")
            desc = fn.get("description", "")[:200]
            tool_catalog.append(f"{name}: {desc}")

        catalog_text = "\n".join(tool_catalog)
        return {
            "type": "function",
            "function": {
                "name": "tool_search",
                "description": (
                    "Search for available tools by describing what you need in natural language. "
                    "Use this BEFORE calling any tool not in the core set — deferred tools "
                    "must be discovered via tool_search first. "
                    "Returns matching tool schemas with their parameters."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language description of the capability you need. Be specific: 'search GitHub issues' not 'github'",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max number of tools to return (default: 5, max: 15)",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    @property
    def strategy_name(self) -> str:
        return "deferred"

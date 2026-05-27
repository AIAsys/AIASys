"""tool_search — 渐进式工具发现。

支持三种动作：
- list_tools: 列出所有可用 deferred 工具（仅名称+分类）
- search_tools: 自然语言搜索工具
- get_tool_description: 获取指定工具的完整参数 schema

策略可通过 on_results 回调获知被发现的工具，以便下一轮将其加入可用列表。
"""

from __future__ import annotations

import difflib
import logging
from collections.abc import Callable, Sequence
from typing import Any, ClassVar

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.agent.runtime_backends.aiasys.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


def _keyword_score(query: str, text: str) -> float:
    query_words = query.lower().split()
    text_lower = text.lower()
    hits = sum(1 for w in query_words if w in text_lower)
    return hits / len(query_words) if query_words else 0.0


def _search_tools(
    query: str,
    deferred_schemas: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """关键词 + 序列匹配搜索 deferred 工具。"""
    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in deferred_schemas:
        fn = entry.get("function", {})
        name = fn.get("name", "")
        desc = fn.get("description", "")
        search_text = f"{name} {desc}"

        kw_score = _keyword_score(query, search_text)
        sm = difflib.SequenceMatcher(None, query.lower(), name.lower())
        seq_score = sm.ratio()

        score = kw_score * 0.7 + seq_score * 0.3
        if score > 0.25:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _score, entry in scored[:limit]]


def _categorize_tool_name(name: str) -> str:
    """从工具名提取分类前缀。"""
    if name.startswith("mcp__"):
        parts = name.split("__", 2)
        if len(parts) >= 2:
            return f"mcp/{parts[1]}"
        return "mcp"
    if "_" in name:
        return name.split("_")[0]
    return "other"


def _build_catalog(
    deferred_schemas: list[dict[str, Any]],
    category_filter: str | None = None,
) -> list[dict[str, Any]]:
    """构建分类工具目录。"""
    categories: dict[str, list[dict[str, Any]]] = {}
    for entry in deferred_schemas:
        fn = entry.get("function", {})
        name = fn.get("name", "")
        cat = _categorize_tool_name(name)
        if category_filter and cat != category_filter:
            continue
        categories.setdefault(cat, []).append(entry)

    result: list[dict[str, Any]] = []
    for cat in sorted(categories):
        result.append({"category": cat, "count": len(categories[cat])})
    return result


class ToolSearchTool(AiasysTool):
    """渐进式工具发现工具。

    支持三种 action：
    - list_tools: 按分类列出所有 deferred 工具名
    - search_tools: 自然语言搜索（关键词+序列匹配）
    - get_tool_description: 获取指定工具的完整描述+参数
    """

    name: ClassVar[str] = "tool_search"
    description: ClassVar[str] = (
        "Discover available tools progressively. "
        "Use list_tools to see all tool categories, "
        "search_tools to find tools by natural language, "
        "and get_tool_description to see full parameter details before calling a tool."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list_tools", "search_tools", "get_tool_description"],
                "description": (
                    "What to do: "
                    "'list_tools' — browse all available tools by category; "
                    "'search_tools' — find tools matching a natural language description; "
                    "'get_tool_description' — get full parameter schema for specific tool(s)"
                ),
            },
            "query": {
                "type": "string",
                "description": "Natural language description of what you need. Required for search_tools.",
            },
            "tool_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "One or more tool names to describe. Required for get_tool_description.",
            },
            "category": {
                "type": "string",
                "description": "Optional category prefix to filter list_tools results.",
            },
        },
        "required": ["action"],
    }

    def __init__(
        self,
        deferred_schemas: list[dict[str, Any]],
        on_results: Callable[[list[str]], None] | None = None,
    ) -> None:
        self._deferred = list(deferred_schemas)
        self._on_results = on_results

    @classmethod
    def from_registry(
        cls,
        registry: ToolRegistry,
        on_results: Callable[[list[str]], None] | None = None,
    ) -> "ToolSearchTool":
        _non_deferred, deferred = registry.get_openai_schemas_split()
        return cls(deferred, on_results=on_results)

    def update_schemas(self, deferred_schemas: list[dict[str, Any]]) -> None:
        self._deferred = list(deferred_schemas)

    def _notify_results(self, tool_names: list[str]) -> None:
        if self._on_results:
            try:
                self._on_results(tool_names)
            except Exception:
                logger.debug("on_results 回调失败", exc_info=True)

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        action = str(kwargs.get("action", "")).strip()
        if not action:
            return ToolResult(
                content="Error: 'action' parameter is required. Choose: list_tools, search_tools, get_tool_description",
                is_error=True,
            )

        if action == "list_tools":
            return self._handle_list(kwargs)
        elif action == "search_tools":
            return self._handle_search(kwargs)
        elif action == "get_tool_description":
            return self._handle_get_description(kwargs)
        else:
            return ToolResult(
                content=f"Error: Unknown action '{action}'. Choose: list_tools, search_tools, get_tool_description",
                is_error=True,
            )

    def _handle_list(self, kwargs: dict[str, Any]) -> ToolResult:
        category_filter = str(kwargs.get("category", "")).strip() or None
        catalog = _build_catalog(self._deferred, category_filter=category_filter)

        if not catalog:
            return ToolResult(content="No deferred tools available.")

        lines = [f"Available tool categories ({len(self._deferred)} total tools):\n"]
        for item in catalog:
            cat = item["category"]
            count = item["count"]
            lines.append(f"- **{cat}**/* ({count} tools)")

        lines.append("")
        lines.append("Use `get_tool_description` to see details of a specific category's tools.")
        lines.append("Use `search_tools` with a natural language query to find relevant tools.")

        content = "\n".join(lines)
        self._notify_results([])
        return ToolResult(content=content)

    def _handle_search(self, kwargs: dict[str, Any]) -> ToolResult:
        query = str(kwargs.get("query", "")).strip()
        if not query:
            return ToolResult(
                content="Error: 'query' parameter is required for search_tools",
                is_error=True,
            )

        try:
            limit = min(max(int(kwargs.get("limit", 5)), 1), 15)
        except (ValueError, TypeError):
            limit = 5
        results = _search_tools(query, self._deferred, limit=limit)

        if not results:
            return ToolResult(
                content=(
                    f"No tools found matching '{query}'. "
                    "Try a broader query or use 'list_tools' to browse all available tools."
                ),
            )

        lines = [f"Found {len(results)} tool(s) matching '{query}':\n"]
        found_names: list[str] = []
        for entry in results:
            fn = entry.get("function", {})
            name = fn.get("name", "")
            desc = fn.get("description", "")
            params = fn.get("parameters", {})
            props = params.get("properties", {}) if isinstance(params, dict) else {}
            param_names = list(props.keys())[:8]
            found_names.append(name)

            lines.append(f"## {name}")
            lines.append(f"  {desc}")
            if param_names:
                lines.append(f"  Parameters: {', '.join(param_names)}")
            lines.append("")

        lines.append(
            "Use `get_tool_description` with the tool name(s) above to see full parameter details before calling."
        )

        self._notify_results(found_names)
        return ToolResult(content="\n".join(lines))

    def _handle_get_description(self, kwargs: dict[str, Any]) -> ToolResult:
        raw_names = kwargs.get("tool_names")
        if not isinstance(raw_names, list) or not raw_names:
            return ToolResult(
                content="Error: 'tool_names' parameter is required for get_tool_description (provide a list of tool names)",
                is_error=True,
            )

        requested = {str(n).strip() for n in raw_names if str(n).strip()}
        if not requested:
            return ToolResult(
                content="Error: 'tool_names' must contain at least one valid tool name",
                is_error=True,
            )

        # Build lookup
        deferred_map: dict[str, dict[str, Any]] = {}
        for entry in self._deferred:
            fn = entry.get("function", {})
            name = fn.get("name", "")
            deferred_map[name] = entry

        lines: list[str] = []
        found_names: list[str] = []
        for name in sorted(requested):
            entry = deferred_map.get(name)
            if entry is None:
                lines.append(f"## {name}")
                lines.append("  *Not found in available tools.*")
                lines.append("")
                continue

            fn = entry.get("function", {})
            desc = fn.get("description", "")
            params = fn.get("parameters", {})
            found_names.append(name)

            lines.append(f"## {name}")
            lines.append(f"  {desc}")
            lines.append("")
            lines.append("  **Parameters:**")
            lines.append("  ```json")
            lines.append(f"  {_format_params_compact(params)}")
            lines.append("  ```")
            lines.append("")

        if not found_names:
            return ToolResult(
                content=f"None of the requested tools were found. Use 'list_tools' or 'search_tools' to discover available tools.",
            )

        self._notify_results(found_names)
        return ToolResult(content="\n".join(lines))


def _format_params_compact(params: dict[str, Any] | None) -> str:
    """紧凑格式化参数 schema。"""
    import json

    if not isinstance(params, dict):
        return "{}"
    props = params.get("properties", {})
    required = params.get("required", [])
    if not isinstance(required, list):
        required = []

    out: dict[str, Any] = {}
    if not isinstance(props, dict):
        return json.dumps(params, indent=2, ensure_ascii=False)

    for pname, pinfo in props.items():
        if not isinstance(pinfo, dict):
            continue
        entry: dict[str, Any] = {}
        ptype = pinfo.get("type", "string")
        entry["type"] = ptype
        if "description" in pinfo:
            entry["description"] = str(pinfo["description"])[:120]
        if "enum" in pinfo:
            entry["enum"] = pinfo["enum"]
        if "default" in pinfo:
            entry["default"] = pinfo["default"]
        if pname in required:
            entry["required"] = True
        out[pname] = entry

    return json.dumps(out, indent=2, ensure_ascii=False)

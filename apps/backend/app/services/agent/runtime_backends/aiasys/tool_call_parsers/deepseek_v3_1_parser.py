import json
import uuid
from typing import Any, Dict, List

from . import ParseResult, ToolCallParser, register_parser


@register_parser("deepseek_v3_1")
class DeepSeekV31ToolCallParser(ToolCallParser):
    """Parser for DeepSeek V3.1 tool call format.

    Variant with <｜tool▁calls▁begin｜> ... <｜tool▁calls▁end｜> tags.
    """

    BEGIN = "<｜tool▁calls▁begin｜>"
    END = "<｜tool▁calls▁end｜>"

    def parse(self, text: str) -> ParseResult:
        if self.BEGIN not in text:
            return text, None

        begin_idx = text.find(self.BEGIN)
        end_idx = text.find(self.END, begin_idx)
        if end_idx == -1:
            end_idx = len(text)

        content = text[:begin_idx].strip()
        tool_section = text[begin_idx + len(self.BEGIN) : end_idx].strip()

        tool_calls: List[Dict[str, Any]] = []
        for line in tool_section.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                tc_data = json.loads(line)
                name = tc_data.get("name")
                if not name:
                    continue
                tool_calls.append(
                    {
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(
                                tc_data.get("arguments", {}), ensure_ascii=False
                            ),
                        },
                    }
                )
            except (json.JSONDecodeError, ValueError):
                continue

        if not tool_calls:
            return text, None

        return content if content else None, tool_calls

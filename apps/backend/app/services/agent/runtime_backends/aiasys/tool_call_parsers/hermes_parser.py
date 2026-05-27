import json
import re
import uuid
from typing import Any, Dict, List

from . import ParseResult, ToolCallParser, register_parser


@register_parser("hermes")
class HermesToolCallParser(ToolCallParser):
    """Parser for Hermes-format tool calls.

    Format: <tool_call>{"name": "func", "arguments": {...}}</tool_call>
    """

    PATTERN = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>|<tool_call>\s*(.*)", re.DOTALL)

    def parse(self, text: str) -> ParseResult:
        if "<tool_call>" not in text:
            return text, None

        try:
            matches = self.PATTERN.findall(text)
            if not matches:
                return text, None

            tool_calls: List[Dict[str, Any]] = []
            for match in matches:
                raw_json = match[0] if match[0] else match[1]
                if not raw_json.strip():
                    continue

                tc_data = json.loads(raw_json)
                if "name" not in tc_data:
                    continue
                tool_calls.append(
                    {
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": tc_data["name"],
                            "arguments": json.dumps(
                                tc_data.get("arguments", {}), ensure_ascii=False
                            ),
                        },
                    }
                )

            if not tool_calls:
                return text, None

            content = text[: text.find("<tool_call>")].strip()
            return content if content else None, tool_calls

        except Exception:
            return text, None

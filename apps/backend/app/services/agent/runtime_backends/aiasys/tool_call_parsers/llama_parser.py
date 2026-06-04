"""
Llama 3.x / 4 tool call parser.

Format: JSON objects with "name" and "arguments" (or "parameters") keys.
May be preceded by <|python_tag|> token. Supports multiple JSON objects.
"""

import json
import re
import uuid
from typing import Any, Dict, List

from . import ParseResult, ToolCallParser, register_parser


@register_parser("llama3_json")
@register_parser("llama4_json")
class LlamaToolCallParser(ToolCallParser):
    """Parser for Llama 3.x and 4 JSON-format tool calls."""

    BOT_TOKEN = "<|python_tag|>"
    JSON_START = re.compile(r"\{")

    def parse(self, text: str) -> ParseResult:
        if self.BOT_TOKEN not in text and "{" not in text:
            return text, None

        try:
            decoder = json.JSONDecoder()
            tool_calls: List[Dict[str, Any]] = []
            end_index = -1

            for match in self.JSON_START.finditer(text):
                start = match.start()
                if start <= end_index:
                    continue

                try:
                    obj, json_end = decoder.raw_decode(text[start:])
                    end_index = start + json_end

                    name = obj.get("name")
                    args = obj.get("arguments", obj.get("parameters"))

                    if not name or args is None:
                        continue

                    if isinstance(args, dict):
                        args = json.dumps(args, ensure_ascii=False)
                    elif not isinstance(args, str):
                        args = json.dumps(args, ensure_ascii=False)

                    tool_calls.append(
                        {
                            "id": f"call_{uuid.uuid4().hex[:8]}",
                            "type": "function",
                            "function": {"name": name, "arguments": args},
                        }
                    )
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

            if not tool_calls:
                return text, None

            first_tc_start = text.find("{")
            if self.BOT_TOKEN in text:
                first_tc_start = text.find(self.BOT_TOKEN)
            content = text[:first_tc_start].strip() if first_tc_start > 0 else None

            return content, tool_calls

        except Exception:
            return text, None

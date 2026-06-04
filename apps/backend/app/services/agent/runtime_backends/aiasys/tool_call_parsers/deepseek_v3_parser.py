"""
DeepSeek V3 tool call parser.

Format uses special unicode tokens:
    <｜tool▁calls▁begin｜>
    <｜tool▁call▁begin｜>type<｜tool▁sep｜>function_name
    ```json
    {"arg": "value"}
    ```
    <｜tool▁call▁end｜>
    <｜tool▁calls▁end｜>

Fixes Issue #989: Support for multiple simultaneous tool calls.
"""

import logging
import re
import uuid
from typing import Any, Dict, List

from . import ParseResult, ToolCallParser, register_parser

logger = logging.getLogger(__name__)


@register_parser("deepseek_v3")
class DeepSeekV3ToolCallParser(ToolCallParser):
    """Parser for DeepSeek V3 tool calls."""

    START_TOKEN = "<｜tool▁calls▁begin｜>"

    PATTERN = re.compile(
        r"<｜tool▁call▁begin｜>(?P<type>.*?)<｜tool▁sep｜>(?P<function_name>.*?)\s*```json\s*(?P<function_arguments>.*?)\s*```\s*<｜tool▁call▁end｜>",
        re.DOTALL,
    )

    def parse(self, text: str) -> ParseResult:
        if self.START_TOKEN not in text:
            return text, None

        try:
            matches = list(self.PATTERN.finditer(text))
            if not matches:
                return text, None

            tool_calls: List[Dict[str, Any]] = []
            for match in matches:
                func_name = match.group("function_name").strip()
                func_args = match.group("function_arguments").strip()
                tool_calls.append(
                    {
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": func_name,
                            "arguments": func_args,
                        },
                    }
                )

            if tool_calls:
                content_index = text.find(self.START_TOKEN)
                content = text[:content_index].strip()
                return content if content else None, tool_calls

            return text, None

        except Exception as e:
            logger.error("Error parsing DeepSeek V3 tool calls: %s", e)
            return text, None

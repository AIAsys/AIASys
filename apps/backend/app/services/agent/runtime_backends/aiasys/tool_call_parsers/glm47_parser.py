"""
GLM 4.7 tool call parser.

Same as GLM 4.5 but with slightly different regex patterns.
"""

import re

from . import register_parser
from .glm45_parser import Glm45ToolCallParser


@register_parser("glm47")
class Glm47ToolCallParser(Glm45ToolCallParser):
    """Parser for GLM 4.7 tool calls. Extends GLM 4.5 with updated regex."""

    def __init__(self):
        super().__init__()
        self.FUNC_DETAIL_REGEX = re.compile(
            r"<tool_call>(.*?)(<arg_key>.*?)?</tool_call>", re.DOTALL
        )
        self.FUNC_ARG_REGEX = re.compile(
            r"<arg_key>(.*?)</arg_key>(?:\n|\s)*<arg_value>(.*?)</arg_value>",
            re.DOTALL,
        )

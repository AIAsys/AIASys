"""
Qwen 2.5 tool call parser.

Uses the same <tool_call> format as Hermes.
"""

from . import register_parser
from .hermes_parser import HermesToolCallParser


@register_parser("qwen")
class QwenToolCallParser(HermesToolCallParser):
    """Parser for Qwen 2.5 tool calls. Same format as Hermes."""

    pass

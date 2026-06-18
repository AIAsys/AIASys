"""Memory pipeline 工具函数测试。"""

import pytest

from app.services.memory.pipeline import (
    _deep_truncate_strings,
    _safe_truncate_prompt_text,
)


class TestDeepTruncateStrings:
    def test_no_truncation_needed(self):
        value = {"key": "short"}
        assert _deep_truncate_strings(value) == {"key": "short"}

    def test_truncates_long_string(self):
        long_str = "a" * 5000
        result = _deep_truncate_strings(long_str, max_len=4000)
        assert result.endswith("\n...（内容已截断）")
        assert len(result) == 4000 + len("\n...（内容已截断）")

    def test_truncates_nested_dict(self):
        value = {"outer": {"inner": "x" * 5000}}
        result = _deep_truncate_strings(value, max_len=100)
        assert result["outer"]["inner"].endswith("\n...（内容已截断）")

    def test_truncates_list_items(self):
        value = ["x" * 5000, "short"]
        result = _deep_truncate_strings(value, max_len=100)
        assert result[0].endswith("\n...（内容已截断）")
        assert result[1] == "short"

    def test_preserves_non_string_values(self):
        value = {"num": 42, "flag": True, "none": None}
        assert _deep_truncate_strings(value) == {"num": 42, "flag": True, "none": None}


class TestSafeTruncatePromptText:
    def test_no_truncation_needed(self):
        text = "short text"
        assert _safe_truncate_prompt_text(text, 100) == "short text"

    def test_truncates_at_newline_boundary(self):
        text = "line1\nline2\nline3\nline4\nline5\nline6"
        # max_chars 足够容纳 "line1\nline2" + 后缀，测试换行符边界截断
        result = _safe_truncate_prompt_text(text, 25)
        assert result.startswith("line1\nline2")
        assert len(result) <= 25
        assert result.endswith("...（以上内容已截断）")

    def test_truncates_without_newline_fallback(self):
        text = "a" * 1000
        result = _safe_truncate_prompt_text(text, 100)
        # 总长度（含后缀）必须不超过 max_chars
        assert len(result) <= 100
        assert result.endswith("...（以上内容已截断）")

    def test_truncates_long_json(self):
        text = '{\n  "key1": "value1",\n  "key2": "value2"\n}'
        # max_chars 不足以容纳完整后缀，测试退化到省略号
        result = _safe_truncate_prompt_text(text, 10)
        assert len(result) <= 10
        assert result.endswith("...")

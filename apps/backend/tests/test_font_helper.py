from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parent.parent / "agent_runtime_helpers"
if str(HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(HELPER_DIR))

from font_helper import setup_cn_font, PREFERRED_FONT_FAMILIES  # noqa: E402


def test_setup_cn_font_matches_system_font() -> None:
    result = setup_cn_font(quiet=True)

    assert result["ok"] is True, f"期望匹配到系统字体，结果: {result}"
    assert result["font_name"] in PREFERRED_FONT_FAMILIES, (
        f"字体名 {result['font_name']!r} 不在预期列表 {PREFERRED_FONT_FAMILIES} 中"
    )

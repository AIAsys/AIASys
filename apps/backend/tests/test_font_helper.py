from __future__ import annotations

import sys
from pathlib import Path


HELPER_DIR = Path(__file__).resolve().parent.parent / "agent_runtime_helpers"
if str(HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(HELPER_DIR))

from font_helper import setup_cn_font  # noqa: E402


def test_setup_cn_font_can_use_bundled_font_without_extra_paths(tmp_path: Path) -> None:
    result = setup_cn_font(workspace=tmp_path, quiet=True)

    assert result["ok"] is True
    assert result["font_name"] in {"Noto Sans CJK SC", "Noto Sans SC"}

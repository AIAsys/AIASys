"""Node.js 运行时工具函数单元测试。"""

import pytest

from app.services.node_runtime import _normalize_node_version, _parse_fnm_list_versions


@pytest.mark.parametrize(
    "stdout,expected",
    [
        ("* v22.15.0 default\n* v20.15.1\n", ["22.15.0", "20.15.1"]),
        ("v18.20.4\nv20.15.0\n", ["18.20.4", "20.15.0"]),
        ("* v22.15.0\n", ["22.15.0"]),
        ("", []),
        ("no versions here", []),
        ("v22.15.0 lts\nv23.0.0 latest\n", ["22.15.0", "23.0.0"]),
    ],
)
def test_parse_fnm_list_versions(stdout: str, expected: list[str]) -> None:
    assert _parse_fnm_list_versions(stdout) == expected


@pytest.mark.parametrize(
    "version,expected",
    [
        ("20", "20"),
        ("v20", "20"),
        ("20.11", "20.11"),
        ("v20.11.0", "20.11.0"),
        ("lts", "lts/*"),
        ("lts/*", "lts/*"),
        ("lts-iron", "lts-iron"),
    ],
)
def test_normalize_node_version(version: str, expected: str) -> None:
    """裸 lts 必须归一化为 lts/*，否则 bundled fnm 会报不可安装。"""
    assert _normalize_node_version(version) == expected


@pytest.mark.parametrize("version", ["", "   ", None])
def test_normalize_node_version_empty(version: str | None) -> None:
    with pytest.raises(ValueError):
        _normalize_node_version(version)

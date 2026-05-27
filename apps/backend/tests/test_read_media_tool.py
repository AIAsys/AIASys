from __future__ import annotations

import base64

import pytest

from app.agents.tools.read_media_tool import Params, ReadMediaFile
from app.services.history import current_workspace


@pytest.mark.asyncio
async def test_read_media_tool_instantiates_without_vendor_runtime_modules() -> None:
    tool = ReadMediaFile({"image_in"})

    assert tool.name == "ReadMediaFile"
    assert "Read media content from a file." in tool.description


@pytest.mark.asyncio
async def test_read_media_tool_fallback_detects_text_files(tmp_path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("hello from text file", encoding="utf-8")
    tool = ReadMediaFile({"image_in"})

    token = current_workspace.set(tmp_path)
    try:
        result = await tool.invoke(**Params(path="notes.txt").model_dump())
    finally:
        current_workspace.reset(token)

    assert result.is_error is True
    assert "text file" in result.message


@pytest.mark.asyncio
async def test_read_media_tool_fallback_reads_png_file(tmp_path) -> None:
    png_path = tmp_path / "pixel.png"
    png_path.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7d0AAAAASUVORK5CYII="
        )
    )
    tool = ReadMediaFile({"image_in"})

    token = current_workspace.set(tmp_path)
    try:
        result = await tool.invoke(**Params(path="pixel.png").model_dump())
    finally:
        current_workspace.reset(token)

    assert result.is_error is False
    assert "[image:/workspace/pixel.png]" in result.output
    assert "data:image/png;base64," in result.output

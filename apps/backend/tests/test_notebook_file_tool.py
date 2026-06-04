from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.core.tool_result import ToolResult

from app.agents.tools.notebook_file_tool import (
    EditNotebookParams,
    EditNotebookFile,
    NotebookOperation,
    ReadNotebook,
)
from app.services.history import current_session_root, current_workspace


def _set_workspace_context(workspace: Path, session_root: Path | None = None):
    tokens = {"workspace": current_workspace.set(workspace)}
    if session_root is not None:
        tokens["session_root"] = current_session_root.set(session_root)
    return tokens


def _reset_workspace_context(tokens):
    if "session_root" in tokens:
        current_session_root.reset(tokens["session_root"])
    current_workspace.reset(tokens["workspace"])


@pytest.mark.asyncio
async def test_read_missing_notebook_returns_exists_false(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    token = _set_workspace_context(workspace)

    try:
        result = await ReadNotebook().invoke(
            notebook_path="notebooks/demo.ipynb",
        )
    finally:
        _reset_workspace_context(token)

    assert not result.is_error
    payload = json.loads(result.output)
    assert payload["status"] == "missing"
    assert payload["exists"] is False


@pytest.mark.asyncio
async def test_edit_notebook_file_read_delegates_to_read_tool(tmp_path: Path):
    workspace = tmp_path / "workspace"
    notebook_path = workspace / "notebooks" / "summary.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-md",
                        "cell_type": "markdown",
                        "source": "# Summary",
                        "metadata": {},
                    },
                    {
                        "id": "cell-code",
                        "cell_type": "code",
                        "source": "print('ok')",
                        "metadata": {},
                        "execution_count": 1,
                        "outputs": [
                            {
                                "output_type": "stream",
                                "name": "stdout",
                                "text": "ok\n",
                            }
                        ],
                    },
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    token = _set_workspace_context(workspace)
    try:
        result = await EditNotebookFile().invoke(
            operation="read",
            notebook_path="notebooks/summary.ipynb",
            start_index=1,
            max_cells=1,
        )
    finally:
        _reset_workspace_context(token)

    assert not result.is_error
    payload = json.loads(result.output)
    assert payload["operation"] == "read"
    assert payload["cell_count"] == 2
    assert payload["returned_cell_count"] == 1
    assert payload["cells"][0]["cell_id"] == "cell-code"


@pytest.mark.asyncio
async def test_upsert_cell_creates_notebook_in_logical_workspace_root(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    token = _set_workspace_context(workspace)

    try:
        result = await EditNotebookFile().invoke(
            operation="upsert_cell",
            notebook_path="notebooks/demo.ipynb",
            cell={
                "cell_type": "markdown",
                "source": "# Demo Notebook",
                "cell_id": "cell-intro",
            },
        )
    finally:
        _reset_workspace_context(token)

    assert not result.is_error
    payload = json.loads(result.output)
    assert payload["cell_count"] == 1
    notebook_path = workspace / "notebooks" / "demo.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    assert notebook["metadata"]["kernelspec"]["name"] == "python3"
    assert notebook["cells"][0]["id"] == "cell-intro"
    assert notebook["cells"][0]["source"] == "# Demo Notebook"


@pytest.mark.asyncio
async def test_upsert_and_clear_outputs_preserve_existing_cells(tmp_path: Path):
    workspace = tmp_path / "workspace"
    notebook_path = workspace / "notebooks" / "analysis.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-code",
                        "cell_type": "code",
                        "source": "print(1)",
                        "metadata": {},
                        "outputs": [
                            {
                                "output_type": "stream",
                                "name": "stdout",
                                "text": "1\n",
                            }
                        ],
                        "execution_count": 1,
                    },
                    {
                        "id": "cell-md",
                        "cell_type": "markdown",
                        "source": "old",
                        "metadata": {},
                    },
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    token = _set_workspace_context(workspace)
    try:
        update_result = await EditNotebookFile().invoke(
            operation="upsert_cell",
            notebook_path="notebooks/analysis.ipynb",
            cell_index=1,
            cell={
                "cell_type": "markdown",
                "source": "updated markdown",
                "cell_id": "cell-md",
            },
        )
        clear_result = await EditNotebookFile().invoke(
            operation="clear_cell_outputs",
            notebook_path="notebooks/analysis.ipynb",
            cell_id="cell-code",
        )
    finally:
        _reset_workspace_context(token)

    assert not update_result.is_error
    assert not clear_result.is_error
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    assert notebook["cells"][0]["outputs"] == []
    assert notebook["cells"][0]["execution_count"] is None
    assert notebook["cells"][1]["source"] == "updated markdown"


@pytest.mark.asyncio
async def test_rejects_session_internal_notebook_path(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    token = _set_workspace_context(workspace)

    try:
        result = await ReadNotebook().invoke(
            notebook_path=".aiasys/session/demo.ipynb",
        )
    finally:
        _reset_workspace_context(token)

    assert result.is_error
    assert ".aiasys" in result.message


@pytest.mark.asyncio
async def test_read_notebook_returns_paginated_safe_output_summaries(tmp_path: Path):
    workspace = tmp_path / "workspace"
    notebook_path = workspace / "notebooks" / "large.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-md",
                        "cell_type": "markdown",
                        "source": "# Intro",
                        "metadata": {},
                    },
                    {
                        "id": "cell-code-1",
                        "cell_type": "code",
                        "source": "print('x' * 200)",
                        "metadata": {},
                        "execution_count": 2,
                        "outputs": [
                            {
                                "output_type": "stream",
                                "name": "stdout",
                                "text": "x" * 240,
                            }
                        ],
                    },
                    {
                        "id": "cell-code-2",
                        "cell_type": "code",
                        "source": "display(image)",
                        "metadata": {},
                        "execution_count": 3,
                        "outputs": [
                            {
                                "output_type": "display_data",
                                "data": {
                                    "image/png": "aGVsbG8=" * 100,
                                    "text/plain": "<Figure size 640x480>",
                                },
                            }
                        ],
                    },
                ],
                "metadata": {"kernelspec": {"name": "python3"}},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    token = _set_workspace_context(workspace)
    try:
        result = await ReadNotebook().invoke(
            notebook_path="notebooks/large.ipynb",
            start_index=1,
            max_cells=1,
        )
    finally:
        _reset_workspace_context(token)

    assert not result.is_error
    payload = json.loads(result.output)
    assert payload["cell_count"] == 3
    assert payload["returned_cell_count"] == 1
    assert payload["start_index"] == 1
    assert payload["next_start_index"] == 2
    assert payload["cells"][0]["cell_id"] == "cell-code-1"
    assert payload["cells"][0]["output_summaries"][0]["output_type"] == "stream"
    assert len(payload["cells"][0]["output_summaries"][0]["text_preview"]) < 200
    assert "aGVsbG8=" not in result.output


@pytest.mark.asyncio
async def test_read_full_notebook_sanitizes_binary_outputs(tmp_path: Path):
    workspace = tmp_path / "workspace"
    notebook_path = workspace / "notebooks" / "binary.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    raw_base64 = "aGVsbG8=" * 100
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-plot",
                        "cell_type": "code",
                        "source": "display(fig)",
                        "metadata": {},
                        "execution_count": 1,
                        "outputs": [
                            {
                                "output_type": "display_data",
                                "data": {
                                    "image/png": raw_base64,
                                    "text/html": f"<img src=\"data:image/png;base64,{raw_base64}\">",
                                },
                            }
                        ],
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    token = _set_workspace_context(workspace)
    try:
        result = await ReadNotebook().invoke(
            notebook_path="notebooks/binary.ipynb",
            include_full_notebook=True,
        )
    finally:
        _reset_workspace_context(token)

    assert not result.is_error
    payload = json.loads(result.output)
    assert payload["notebook_sanitized"] is True
    assert "aGVsbG8=" not in result.output
    image_payload = payload["notebook"]["cells"][0]["outputs"][0]["data"]["image/png"]
    assert image_payload["omitted"] is True
    assert image_payload["mime_type"] == "image/png"
    assert payload["cells"][0]["output_summaries"][0]["has_binary_payload"] is True


@pytest.mark.asyncio
async def test_write_notebook_defaults_to_session_private_copy_when_session_root_exists(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    session_root = tmp_path / "session"
    workspace_notebook_path = workspace / "notebooks" / "analysis.ipynb"
    workspace_notebook_path.parent.mkdir(parents=True, exist_ok=True)
    session_root.mkdir(parents=True, exist_ok=True)
    workspace_notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-md",
                        "cell_type": "markdown",
                        "source": "# Shared Notebook",
                        "metadata": {},
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    token = _set_workspace_context(workspace)
    try:
        read_result = await ReadNotebook().invoke(
            notebook_path="notebooks/analysis.ipynb",
        )
        write_result = await EditNotebookFile().invoke(
            operation="upsert_cell",
            notebook_path="notebooks/analysis.ipynb",
            cell={
                "cell_type": "markdown",
                "source": "branch private",
                "cell_id": "cell-branch",
            },
        )
    finally:
        _reset_workspace_context(token)

    assert not read_result.is_error
    read_payload = json.loads(read_result.output)
    assert read_payload["resolved_from"] == "workspace"

    assert not write_result.is_error
    write_payload = json.loads(write_result.output)
    assert write_payload["written_to"] == "workspace"

    workspace_notebook = json.loads(workspace_notebook_path.read_text(encoding="utf-8"))
    assert len(workspace_notebook["cells"]) == 2
    assert workspace_notebook["cells"][1]["source"] == "branch private"



@pytest.mark.asyncio
async def test_patch_cell_single_find_replace(tmp_path: Path):
    workspace = tmp_path / "workspace"
    notebook_path = workspace / "notebooks" / "patch.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-1",
                        "cell_type": "code",
                        "source": "import pandas as pd\nimport numpy as np\n",
                        "metadata": {},
                        "outputs": [{"output_type": "stream", "name": "stdout", "text": "ok\n"}],
                        "execution_count": 1,
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    token = _set_workspace_context(workspace)
    try:
        result = await EditNotebookFile().invoke(
            operation="patch_cell",
            notebook_path="notebooks/patch.ipynb",
            cell_id="cell-1",
            patches=[{"find": "import pandas as pd", "replace": "import polars as pl"}],
        )
    finally:
        _reset_workspace_context(token)

    assert not result.is_error
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    assert notebook["cells"][0]["source"] == "import polars as pl\nimport numpy as np\n"


@pytest.mark.asyncio
async def test_patch_cell_multiple_patches(tmp_path: Path):
    workspace = tmp_path / "workspace"
    notebook_path = workspace / "notebooks" / "patch.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-1",
                        "cell_type": "code",
                        "source": "x = 1\ny = 2\nz = 3\n",
                        "metadata": {},
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    token = _set_workspace_context(workspace)
    try:
        result = await EditNotebookFile().invoke(
            operation="patch_cell",
            notebook_path="notebooks/patch.ipynb",
            cell_index=0,
            patches=[
                {"find": "x = 1", "replace": "x = 10"},
                {"find": "y = 2", "replace": "y = 20"},
            ],
        )
    finally:
        _reset_workspace_context(token)

    assert not result.is_error
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    assert notebook["cells"][0]["source"] == "x = 10\ny = 20\nz = 3\n"


@pytest.mark.asyncio
async def test_patch_cell_missing_find_returns_error(tmp_path: Path):
    workspace = tmp_path / "workspace"
    notebook_path = workspace / "notebooks" / "patch.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-1",
                        "cell_type": "code",
                        "source": "print('hello')",
                        "metadata": {},
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    token = _set_workspace_context(workspace)
    try:
        result = await EditNotebookFile().invoke(
            operation="patch_cell",
            notebook_path="notebooks/patch.ipynb",
            cell_id="cell-1",
            patches=[{"find": "nonexistent", "replace": "foo"}],
        )
    finally:
        _reset_workspace_context(token)

    assert result.is_error
    assert "find 内容未找到" in result.message


@pytest.mark.asyncio
async def test_patch_cell_duplicate_find_replaces_first_only(tmp_path: Path):
    workspace = tmp_path / "workspace"
    notebook_path = workspace / "notebooks" / "patch.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-1",
                        "cell_type": "code",
                        "source": "a = 1\na = 2\na = 3\n",
                        "metadata": {},
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    token = _set_workspace_context(workspace)
    try:
        result = await EditNotebookFile().invoke(
            operation="patch_cell",
            notebook_path="notebooks/patch.ipynb",
            cell_id="cell-1",
            patches=[{"find": "a = 2", "replace": "a = 99"}],
        )
    finally:
        _reset_workspace_context(token)

    assert not result.is_error
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    assert notebook["cells"][0]["source"] == "a = 1\na = 99\na = 3\n"


@pytest.mark.asyncio
async def test_patch_cell_on_list_source(tmp_path: Path):
    workspace = tmp_path / "workspace"
    notebook_path = workspace / "notebooks" / "patch.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-1",
                        "cell_type": "code",
                        "source": ["def foo():\n", "    return 1\n"],
                        "metadata": {},
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    token = _set_workspace_context(workspace)
    try:
        result = await EditNotebookFile().invoke(
            operation="patch_cell",
            notebook_path="notebooks/patch.ipynb",
            cell_id="cell-1",
            patches=[{"find": "    return 1", "replace": "    return 42"}],
        )
    finally:
        _reset_workspace_context(token)

    assert not result.is_error
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    assert notebook["cells"][0]["source"] == "def foo():\n    return 42\n"

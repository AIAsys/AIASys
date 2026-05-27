from __future__ import annotations

import json
from pathlib import Path

import pytest
# ToolError/ToolOk removed, use result.is_error

from app.agents.tools.notebook_session_tool import (
    CreateSessionNotebookParams,
    CreateSessionNotebook,
    ListSessionNotebooksParams,
    ListSessionNotebooks,
    ReadNotebookOutputsParams,
    ReadNotebookOutputs,
)
from app.services.history import current_session_root, current_workspace


def _set_context(workspace: Path, session_root: Path | None = None):
    tokens = {"workspace": current_workspace.set(workspace)}
    if session_root is not None:
        tokens["session_root"] = current_session_root.set(session_root)
    return tokens


def _reset_context(tokens: dict[str, object]) -> None:
    if "session_root" in tokens:
        current_session_root.reset(tokens["session_root"])
    current_workspace.reset(tokens["workspace"])


@pytest.mark.asyncio
async def test_list_session_notebooks_reads_workspace_directory(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    (workspace / "research" / "notebooks").mkdir(parents=True, exist_ok=True)
    (workspace / "research" / "notebooks" / "shared.ipynb").write_text("{}", encoding="utf-8")
    (workspace / "research" / "notebooks" / "scratch.ipynb").write_text("{}", encoding="utf-8")
    (workspace / "research" / "notebooks" / "branch.ipynb").write_text("{}", encoding="utf-8")

    tokens = _set_context(workspace)
    try:
        result = await ListSessionNotebooks().invoke(**ListSessionNotebooksParams(directory="research/notebooks").model_dump())
    finally:
        _reset_context(tokens)

    assert not result.is_error
    payload = json.loads(result.output)
    assert payload["scope"] == "workspace"
    assert payload["count"] == 3
    assert {item["path"] for item in payload["notebooks"]} == {
        "research/notebooks/branch.ipynb",
        "research/notebooks/scratch.ipynb",
        "research/notebooks/shared.ipynb",
    }


@pytest.mark.asyncio
async def test_list_session_notebooks_defaults_to_notebooks_directory(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "notebooks").mkdir(parents=True, exist_ok=True)
    (workspace / "research" / "notebooks").mkdir(parents=True, exist_ok=True)
    (workspace / "notebooks" / "current.ipynb").write_text("{}", encoding="utf-8")
    (workspace / "research" / "notebooks" / "legacy.ipynb").write_text(
        "{}",
        encoding="utf-8",
    )

    tokens = _set_context(workspace)
    try:
        result = await ListSessionNotebooks().invoke(**ListSessionNotebooksParams().model_dump())
    finally:
        _reset_context(tokens)

    assert not result.is_error
    payload = json.loads(result.output)
    assert payload["directory"] == "notebooks"
    assert payload["count"] == 1
    assert payload["notebooks"][0]["path"] == "notebooks/current.ipynb"


@pytest.mark.asyncio
async def test_create_session_notebook_writes_private_notebook_and_seeds_cells(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    session_root = tmp_path / "session"
    workspace.mkdir(parents=True, exist_ok=True)
    session_root.mkdir(parents=True, exist_ok=True)

    tokens = _set_context(workspace, session_root)
    try:
        result = await CreateSessionNotebook().invoke(**CreateSessionNotebookParams(
            notebook_path="research/notebooks/_scratch/demo.ipynb",
            title="Scratch Demo",
            cells=[
                {
                    "cell_type": "code",
                    "source": "print('hello')",
                    "cell_id": "cell-code",
                }
            ],
        ).model_dump())
    finally:
        _reset_context(tokens)

    assert not result.is_error
    payload = json.loads(result.output)
    assert payload["scope"] == "workspace"
    assert payload["cell_count"] == 1

    workspace_notebook = workspace / "research" / "notebooks" / "_scratch" / "demo.ipynb"
    assert workspace_notebook.exists()

    notebook = json.loads(workspace_notebook.read_text(encoding="utf-8"))
    assert notebook["cells"][0]["id"] == "cell-code"
    assert notebook["cells"][0]["source"] == "print('hello')"


@pytest.mark.asyncio
async def test_read_notebook_outputs_prefers_session_copy_and_filters_output_cells(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    session_root = tmp_path / "session"
    workspace.mkdir(parents=True, exist_ok=True)
    session_root.mkdir(parents=True, exist_ok=True)

    workspace_notebook = workspace / "research" / "notebooks" / "analysis.ipynb"
    workspace_notebook.parent.mkdir(parents=True, exist_ok=True)
    workspace_notebook.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "id": "cell-md",
                        "cell_type": "markdown",
                        "source": "# Demo",
                        "metadata": {},
                    },
                    {
                        "id": "cell-out",
                        "cell_type": "code",
                        "source": "print('workspace')",
                        "metadata": {},
                        "outputs": [
                            {
                                "output_type": "stream",
                                "name": "stdout",
                                "text": "workspace output\n",
                            }
                        ],
                        "execution_count": 2,
                    },
                    {
                        "id": "cell-figure",
                        "cell_type": "code",
                        "source": "display(fig)",
                        "metadata": {},
                        "outputs": [
                            {
                                "output_type": "display_data",
                                "data": {
                                    "image/png": "aGVsbG8=" * 20,
                                    "text/plain": "<Figure size 640x480>",
                                },
                            }
                        ],
                        "execution_count": 3,
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

    tokens = _set_context(workspace)
    try:
        result = await ReadNotebookOutputs().invoke(**ReadNotebookOutputsParams(
                notebook_path="research/notebooks/analysis.ipynb",
                max_cells=10,
            ).model_dump())
    finally:
        _reset_context(tokens)

    assert not result.is_error
    payload = json.loads(result.output)
    assert payload["resolved_from"] == "workspace"
    assert payload["matching_cell_count"] == 2
    assert payload["returned_cell_count"] == 2
    assert payload["cells"][0]["cell_id"] == "cell-out"
    assert payload["cells"][0]["output_summaries"][0]["text_preview"] == "workspace output"
    assert payload["cells"][1]["cell_id"] == "cell-figure"
    assert payload["cells"][1]["output_summaries"][0]["mime_types"] == [
        "image/png",
        "text/plain",
    ]
    assert "aGVsbG8=" not in result.output


@pytest.mark.asyncio
async def test_create_session_notebook_creates_in_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    tokens = _set_context(workspace)
    try:
        result = await CreateSessionNotebook().invoke(**CreateSessionNotebookParams(
                notebook_path="research/notebooks/demo.ipynb",
                title="Workspace Notebook",
            ).model_dump())
    finally:
        _reset_context(tokens)

    assert not result.is_error
    notebook_path = workspace / "research" / "notebooks" / "demo.ipynb"
    assert notebook_path.exists()
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    assert notebook["cells"][0]["source"] == "# Workspace Notebook"

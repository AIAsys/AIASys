from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.tools.notebook_tool import ManageNotebook, NotebookAction
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
async def test_manage_notebook_patch_delegates_to_edit_tool(tmp_path: Path):
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
                        "source": "x = 1\n",
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
        result = await ManageNotebook().invoke(
            action=NotebookAction.PATCH,
            notebook_path="notebooks/patch.ipynb",
            cell_id="cell-1",
            patches=[{"find": "x = 1", "replace": "x = 42"}],
        )
    finally:
        _reset_workspace_context(token)

    assert not result.is_error
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    assert notebook["cells"][0]["source"] == "x = 42\n"

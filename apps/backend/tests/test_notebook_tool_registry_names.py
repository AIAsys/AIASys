from __future__ import annotations

import importlib

from app.agents.tools.notebook_file_tool import EditNotebookFile
from app.agents.tools.notebook_tool import ManageNotebook
from app.services.agent.runtime_backends.aiasys.tool_registry import ToolRegistry
from app.services.agent.system_presets import (
    DATA_ANALYSIS_BASELINE,
)


def _instantiate_tool_from_path(tool_path: str):
    module_name, symbol_name = tool_path.rsplit(":", 1)
    tool_cls = getattr(importlib.import_module(module_name), symbol_name)
    return tool_cls()


def test_notebook_tool_runtime_names_match_prompts():
    registry = ToolRegistry()
    registry.register(ManageNotebook())
    registry.register(EditNotebookFile())

    schema_names = {
        item["function"]["name"]
        for item in registry.get_openai_schema()
    }

    assert "ManageNotebook" in schema_names
    assert "EditNotebookFile" in schema_names
    assert "manage_notebook" not in schema_names
    assert "EditNotebook" not in schema_names
    assert registry.get_tool("ManageNotebook") is not None
    assert registry.get_tool("EditNotebookFile") is not None


def test_notebook_tool_runtime_names_match_system_preset_loaded_schemas():
    registry = ToolRegistry()
    for tool_path in DATA_ANALYSIS_BASELINE.tools:
        if "notebook" not in tool_path:
            continue
        registry.register(_instantiate_tool_from_path(tool_path))

    schema_names = {
        item["function"]["name"]
        for item in registry.get_openai_schema()
    }

    assert "ListSessionNotebooks" in schema_names
    assert "ManageNotebook" in schema_names
    assert "manage_notebook" not in schema_names
    assert "EditNotebook" not in schema_names

from __future__ import annotations

from app.services import capability_registry as capability_registry_module
from app.services.capability_registry import CapabilityRegistryService
from app.services.runtime_tooling import (
    NATIVE_TASK_TOOL_PATH,
    READ_MEDIA_TOOL_PATH,
    RuntimeToolAvailability,
    probe_runtime_tool,
)
from app.services.agent.system_presets import (
    AUTO_TASK_TOOL_PATHS,
    CANVAS_TOOL_PATHS,
    DATA_TABLE_TOOL_PATHS,
    KNOWLEDGE_BASE_TOOL_PATHS,
    KNOWLEDGE_GRAPH_TOOL_PATHS,
    RUNTIME_ENVIRONMENT_TOOL_PATH,
    SESSION_TASK_PLAN_TOOL_PATHS,
)


def _build_probe(available_tools: set[str]):
    def fake_probe(tool_name: str) -> RuntimeToolAvailability:
        return RuntimeToolAvailability(
            tool_name=tool_name,
            available=tool_name in available_tools,
            reason="available" if tool_name in available_tools else "module_import_error",
        )

    return fake_probe


def test_knowledge_graph_tool_paths_are_runtime_importable() -> None:
    unavailable = [
        availability
        for tool_name in KNOWLEDGE_GRAPH_TOOL_PATHS
        if not (availability := probe_runtime_tool(tool_name)).available
    ]

    assert unavailable == []


def test_knowledge_base_tool_paths_are_runtime_importable() -> None:
    unavailable = [
        availability
        for tool_name in KNOWLEDGE_BASE_TOOL_PATHS
        if not (availability := probe_runtime_tool(tool_name)).available
    ]

    assert unavailable == []


def test_data_table_tool_paths_are_runtime_importable() -> None:
    unavailable = [
        availability
        for tool_name in DATA_TABLE_TOOL_PATHS
        if not (availability := probe_runtime_tool(tool_name)).available
    ]

    assert unavailable == []


def test_canvas_tool_paths_are_runtime_importable() -> None:
    unavailable = [
        availability
        for tool_name in CANVAS_TOOL_PATHS
        if not (availability := probe_runtime_tool(tool_name)).available
    ]

    assert unavailable == []


def test_capability_registry_includes_mode_presets(monkeypatch) -> None:
    monkeypatch.setattr(
        capability_registry_module,
        "probe_runtime_tool",
        _build_probe(
            {
                NATIVE_TASK_TOOL_PATH,
                READ_MEDIA_TOOL_PATH,
                RUNTIME_ENVIRONMENT_TOOL_PATH,
                "app.agents.tools.notebook_session_tool:ListSessionNotebooks",
                "app.agents.tools.notebook_tool:ManageNotebook",
                "app.agents.tools.notebook_file_tool:ReadNotebook",
                "app.agents.tools.notebook_file_tool:EditNotebookFile",
                "app.agents.tools.ask_user.tool:AskUser",
                *SESSION_TASK_PLAN_TOOL_PATHS,
                *AUTO_TASK_TOOL_PATHS,
                *KNOWLEDGE_BASE_TOOL_PATHS,
                *KNOWLEDGE_GRAPH_TOOL_PATHS,
                *DATA_TABLE_TOOL_PATHS,
                *CANVAS_TOOL_PATHS,
            }
        ),
    )

    service = CapabilityRegistryService()
    registry = service.get_registry(user_id="local_default", analysis_sandbox_mode="local")

    analysis_preset = next(item for item in registry.mode_presets if item.mode == "analysis")

    assert registry.analysis_sandbox_mode == "local"
    assert analysis_preset.source_config_path == "preset://local/data_analysis"
    assert "runtime.list_session_notebooks" in analysis_preset.capability_ids
    assert "runtime.manage_notebook" in analysis_preset.capability_ids
    assert "runtime.local_ipython_box" not in analysis_preset.capability_ids
    assert "native.multiagent_task" in analysis_preset.capability_ids
    assert "native.session_task_create" in analysis_preset.capability_ids
    assert "native.enter_plan_mode" in analysis_preset.capability_ids
    assert "native.exit_plan_mode" in analysis_preset.capability_ids
    assert "native.auto_task_signal" in analysis_preset.capability_ids
    assert "native.create_auto_task" in analysis_preset.capability_ids
    assert "native.list_auto_tasks" in analysis_preset.capability_ids
    assert "native.update_auto_task" in analysis_preset.capability_ids
    assert "native.control_auto_task" in analysis_preset.capability_ids
    assert "runtime.manage_workspace_runtime_environment" in analysis_preset.capability_ids
    assert "native.create_knowledge_base" in analysis_preset.capability_ids
    assert "native.update_knowledge_base" in analysis_preset.capability_ids
    assert "native.upload_knowledge_base_documents" in analysis_preset.capability_ids
    assert "native.list_knowledge_base_documents" in analysis_preset.capability_ids
    assert "native.delete_knowledge_base_documents" in analysis_preset.capability_ids
    assert "native.delete_knowledge_base" in analysis_preset.capability_ids
    assert "native.graphrag_entity_search" in analysis_preset.capability_ids
    assert "native.graphrag_entity_detail" in analysis_preset.capability_ids
    assert "native.list_knowledge_graphs" in analysis_preset.capability_ids
    assert "native.create_knowledge_graph" in analysis_preset.capability_ids
    assert "native.delete_knowledge_graph" in analysis_preset.capability_ids
    assert "native.create_graph_entity" in analysis_preset.capability_ids
    assert "native.update_graph_entity" in analysis_preset.capability_ids
    assert "native.delete_graph_entity" in analysis_preset.capability_ids
    assert "native.create_graph_relation" in analysis_preset.capability_ids
    assert "native.graphrag_entity_relations" in analysis_preset.capability_ids
    assert "native.graphrag_community_report" in analysis_preset.capability_ids
    assert "native.graphrag_document_upload" in analysis_preset.capability_ids
    assert "native.create_data_table" in analysis_preset.capability_ids
    assert "native.read_data_table_schema" in analysis_preset.capability_ids
    assert "native.query_data_table" in analysis_preset.capability_ids
    assert "native.insert_data_table_records" in analysis_preset.capability_ids
    assert "native.update_data_table_record" in analysis_preset.capability_ids
    assert "native.delete_data_table_record" in analysis_preset.capability_ids
    assert "native.add_data_table_column" in analysis_preset.capability_ids
    assert "native.update_data_table_column" in analysis_preset.capability_ids
    assert "native.remove_data_table_column" in analysis_preset.capability_ids
    assert "native.read_canvas" in analysis_preset.capability_ids
    assert "native.write_canvas" in analysis_preset.capability_ids
    assert "native.batch_canvas_operations" in analysis_preset.capability_ids

    manage_notebook = next(
        item for item in registry.capabilities if item.capability_id == "runtime.manage_notebook"
    )
    assert manage_notebook.kind.value == "runtime_helper"
    assert manage_notebook.default_modes == ["analysis"]
    assert manage_notebook.evidence_level.value == "runtime_verified"
    task_capability = next(
        item for item in registry.capabilities if item.capability_id == "native.multiagent_task"
    )
    assert task_capability.status.value == "active"
    assert task_capability.config_schema["runtime_available"] is True
    assert task_capability.config_schema["tool_name"] == NATIVE_TASK_TOOL_PATH
    assert task_capability.config_schema["source"] == "system_preset"
    assert "runtime.read_file" not in analysis_preset.capability_ids
    runtime_env_capability = next(
        item
        for item in registry.capabilities
        if item.capability_id == "runtime.manage_workspace_runtime_environment"
    )
    assert runtime_env_capability.config_schema["tool_name"] == RUNTIME_ENVIRONMENT_TOOL_PATH
    assert runtime_env_capability.evidence_level.value == "runtime_verified"


def test_capability_registry_switches_analysis_runtime_helper_with_sandbox_mode(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        capability_registry_module,
        "probe_runtime_tool",
        _build_probe(
            {
                NATIVE_TASK_TOOL_PATH,
                READ_MEDIA_TOOL_PATH,
                RUNTIME_ENVIRONMENT_TOOL_PATH,
                "app.agents.tools.notebook_session_tool:ListSessionNotebooks",
                "app.agents.tools.notebook_tool:ManageNotebook",
                "app.agents.tools.notebook_file_tool:ReadNotebook",
                "app.agents.tools.notebook_file_tool:EditNotebookFile",
                "app.agents.tools.ask_user.tool:AskUser",
                *SESSION_TASK_PLAN_TOOL_PATHS,
                *AUTO_TASK_TOOL_PATHS,
                *KNOWLEDGE_BASE_TOOL_PATHS,
                *KNOWLEDGE_GRAPH_TOOL_PATHS,
                *DATA_TABLE_TOOL_PATHS,
                *CANVAS_TOOL_PATHS,
            }
        ),
    )
    service = CapabilityRegistryService()

    local_registry = service.get_registry(user_id="local_default", analysis_sandbox_mode="local")
    docker_registry = service.get_registry(user_id="local_default", analysis_sandbox_mode="docker")

    local_analysis = next(item for item in local_registry.mode_presets if item.mode == "analysis")
    docker_analysis = next(item for item in docker_registry.mode_presets if item.mode == "analysis")

    assert "runtime.manage_notebook" in local_analysis.capability_ids
    assert "runtime.ipython_box" not in local_analysis.capability_ids
    assert docker_registry.analysis_sandbox_mode == "local"
    assert "runtime.manage_notebook" in docker_analysis.capability_ids
    assert "runtime.ipython_box" not in docker_analysis.capability_ids

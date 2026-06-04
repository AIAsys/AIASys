from __future__ import annotations

import pytest

from app.api.routes import system as system_route
from app.models.user import UserInfo
from app.services import capability_registry as capability_registry_module
from app.services.capability_registry import CapabilityRegistryService
from app.services.agent.system_presets import (
    AUTO_TASK_TOOL_PATHS,
    CANVAS_TOOL_PATHS,
    DATA_TABLE_TOOL_PATHS,
    KNOWLEDGE_BASE_TOOL_PATHS,
    KNOWLEDGE_GRAPH_TOOL_PATHS,
    RUNTIME_ENVIRONMENT_TOOL_PATH,
    SESSION_TASK_PLAN_TOOL_PATHS,
)
from app.services.runtime_tooling import (
    NATIVE_TASK_TOOL_PATH,
    READ_MEDIA_TOOL_PATH,
    RuntimeToolAvailability,
)


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_probe(available_tools: set[str]):
    def fake_probe(tool_name: str) -> RuntimeToolAvailability:
        return RuntimeToolAvailability(
            tool_name=tool_name,
            available=tool_name in available_tools,
            reason="available" if tool_name in available_tools else "module_import_error",
        )

    return fake_probe


@pytest.mark.asyncio
async def test_system_capability_registry_route_exposes_runtime_disabled_tools(
    monkeypatch: pytest.MonkeyPatch,
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
    monkeypatch.setattr(system_route, "get_capability_registry_service", lambda: service)

    registry = await system_route.get_capability_registry(
        analysis_sandbox_mode="local",
        current_user=_build_user(),
    )

    analysis_preset = next(item for item in registry.mode_presets if item.mode == "analysis")
    task_capability = next(
        item for item in registry.capabilities if item.capability_id == "native.multiagent_task"
    )

    assert analysis_preset.source_config_path == "preset://local/data_analysis"
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
    assert task_capability.status.value == "active"
    assert task_capability.config_schema["runtime_available"] is True
    assert task_capability.config_schema["tool_name"] == NATIVE_TASK_TOOL_PATH
    assert task_capability.config_schema["source"] == "system_preset"
    assert "runtime.read_file" not in analysis_preset.capability_ids


@pytest.mark.asyncio
async def test_system_integrations_market_route_returns_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CapabilityRegistryService()
    monkeypatch.setattr(system_route, "get_capability_registry_service", lambda: service)

    market = await system_route.get_integrations_market(current_user=_build_user())

    assert isinstance(market.items, list)
    assert isinstance(market.recommended_by_mode, dict)


@pytest.mark.asyncio
async def test_system_tool_categories_return_functional_capability_mappings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CapabilityRegistryService()
    monkeypatch.setattr(system_route, "get_capability_registry_service", lambda: service)

    response = await system_route.get_tool_categories(current_user=_build_user())

    categories = {item.category_id: item for item in response.categories}
    assert response.total == len(categories)
    assert {
        "workspace-files",
        "environment",
        "knowledge-base",
        "knowledge-graph",
        "data-tables",
        "canvas",
        "notebook",
        "databases",
        "automation",
    }.issubset(categories)
    assert "runtime.read_file" in categories["workspace-files"].capability_ids
    assert "runtime.list_env_vars" in categories["environment"].capability_ids
    assert "runtime.manage_workspace_runtime_environment" in categories[
        "environment"
    ].capability_ids
    assert "native.knowledge_query" in categories["knowledge-base"].capability_ids
    assert "native.create_knowledge_base" in categories["knowledge-base"].capability_ids
    assert "native.update_knowledge_base" in categories["knowledge-base"].capability_ids
    assert "native.upload_knowledge_base_documents" in categories[
        "knowledge-base"
    ].capability_ids
    assert "native.list_knowledge_base_documents" in categories[
        "knowledge-base"
    ].capability_ids
    assert "native.delete_knowledge_base_documents" in categories[
        "knowledge-base"
    ].capability_ids
    assert "native.delete_knowledge_base" in categories["knowledge-base"].capability_ids
    assert "native.graphrag_entity_search" in categories[
        "knowledge-graph"
    ].capability_ids
    assert "native.create_knowledge_graph" in categories[
        "knowledge-graph"
    ].capability_ids
    assert "native.delete_knowledge_graph" in categories[
        "knowledge-graph"
    ].capability_ids
    assert "native.create_graph_entity" in categories[
        "knowledge-graph"
    ].capability_ids
    assert "native.update_graph_entity" in categories[
        "knowledge-graph"
    ].capability_ids
    assert "native.delete_graph_entity" in categories[
        "knowledge-graph"
    ].capability_ids
    assert "native.create_graph_relation" in categories[
        "knowledge-graph"
    ].capability_ids
    assert "native.graphrag_entity_relations" in categories[
        "knowledge-graph"
    ].capability_ids
    assert "native.graphrag_community_report" in categories[
        "knowledge-graph"
    ].capability_ids
    assert "native.graphrag_document_upload" in categories[
        "knowledge-graph"
    ].capability_ids
    assert "native.create_data_table" in categories["data-tables"].capability_ids
    assert "native.read_data_table_schema" in categories["data-tables"].capability_ids
    assert "native.query_data_table" in categories["data-tables"].capability_ids
    assert "native.insert_data_table_records" in categories["data-tables"].capability_ids
    assert "native.update_data_table_record" in categories["data-tables"].capability_ids
    assert "native.delete_data_table_record" in categories["data-tables"].capability_ids
    assert "native.add_data_table_column" in categories["data-tables"].capability_ids
    assert "native.update_data_table_column" in categories["data-tables"].capability_ids
    assert "native.remove_data_table_column" in categories["data-tables"].capability_ids
    assert "native.read_canvas" in categories["canvas"].capability_ids
    assert "native.write_canvas" in categories["canvas"].capability_ids
    assert "native.batch_canvas_operations" in categories["canvas"].capability_ids
    assert "native.auto_task_signal" in categories["automation"].capability_ids
    assert "native.create_auto_task" in categories["automation"].capability_ids
    assert "native.list_auto_tasks" in categories["automation"].capability_ids
    assert "native.update_auto_task" in categories["automation"].capability_ids
    assert "native.control_auto_task" in categories["automation"].capability_ids
    assert "runtime.manage_notebook" in categories["notebook"].capability_ids
    assert "app.agents.tools.notebook_tool:ManageNotebook" in categories[
        "notebook"
    ].tool_names

from __future__ import annotations

import pytest

from app.services.agent_config.models import AgentMode
from app.services.agent_config.service import AgentConfigService


SEARCH_WEB_TOOL = "app.agents.tools.read_media_tool:ReadMediaFile"
FETCH_URL_TOOL = "app.agents.tools.notebook_session_tool:ListSessionNotebooks"


@pytest.mark.asyncio
async def test_session_override_takes_precedence_over_user_default(
    tmp_path,
) -> None:
    service = AgentConfigService(workspace_root=tmp_path)

    assert await service.save_prompt_override(
        AgentMode.ANALYSIS,
        user_id="user-1",
        content="USER DEFAULT PROMPT",
    )
    assert await service.save_tools_config(
        AgentMode.ANALYSIS,
        user_id="user-1",
        disabled_tools=[SEARCH_WEB_TOOL],
    )

    merged_user = await service.get_merged_config(
        mode=AgentMode.ANALYSIS,
        user_id="user-1",
    )
    assert merged_user.prompt_source == "user_default"
    assert SEARCH_WEB_TOOL in merged_user.disabled_tools

    assert await service.save_prompt_override(
        AgentMode.ANALYSIS,
        user_id="user-1",
        session_id="session-1",
        content="SESSION OVERRIDE PROMPT",
    )
    assert await service.save_tools_config(
        AgentMode.ANALYSIS,
        user_id="user-1",
        session_id="session-1",
        disabled_tools=[FETCH_URL_TOOL],
    )

    merged_session = await service.get_merged_config(
        mode=AgentMode.ANALYSIS,
        user_id="user-1",
        session_id="session-1",
    )
    assert merged_session.prompt_source == "session_override"
    assert "USER DEFAULT PROMPT" in merged_session.system_prompt
    assert "SESSION OVERRIDE PROMPT" in merged_session.system_prompt
    assert SEARCH_WEB_TOOL not in merged_session.disabled_tools
    assert FETCH_URL_TOOL in merged_session.disabled_tools


@pytest.mark.asyncio
async def test_session_editor_config_falls_back_to_user_default_until_local_override(
    tmp_path,
) -> None:
    service = AgentConfigService(workspace_root=tmp_path)

    assert await service.save_prompt_override(
        AgentMode.ANALYSIS,
        user_id="user-2",
        content="ANALYSIS USER DEFAULT",
    )

    editor_before = await service.get_session_editor_config(
        mode=AgentMode.ANALYSIS,
        user_id="user-2",
        session_id="session-2",
    )
    assert editor_before["source"] == "user_default"
    assert editor_before["has_local_override"] is False
    assert "ANALYSIS USER DEFAULT" in str(editor_before["prompt_content"])

    assert await service.save_prompt_override(
        AgentMode.ANALYSIS,
        user_id="user-2",
        session_id="session-2",
        content="ANALYSIS SESSION PROMPT",
    )

    editor_after = await service.get_session_editor_config(
        mode=AgentMode.ANALYSIS,
        user_id="user-2",
        session_id="session-2",
    )
    assert editor_after["source"] == "session_override"
    assert editor_after["has_local_override"] is True
    assert editor_after["prompt_content"] == "ANALYSIS SESSION PROMPT"

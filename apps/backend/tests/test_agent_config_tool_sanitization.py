from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.api.routes import agent_config as agent_config_route
from app.models.user import UserInfo
from app.services.agent_config.models import AgentMode
from app.services.agent_config.service import AgentConfigService
from app.services.agent_config import service as service_module
from app.services.runtime_tooling import NATIVE_TASK_TOOL_PATH, RuntimeToolAvailability

TODO_LIST_TOOL_PATH = "app.agents.tools.task_plan_tools:SetTodoList"


def test_filter_supported_tools_canonicalizes_and_filters(monkeypatch) -> None:
    def fake_probe(tool_name: str) -> RuntimeToolAvailability:
        return RuntimeToolAvailability(
            tool_name=tool_name,
            available=tool_name != "app.agents.tools.unknown:Missing",
            reason="available"
            if tool_name != "app.agents.tools.unknown:Missing"
            else "module_import_error",
        )

    monkeypatch.setattr(service_module, "probe_runtime_tool", fake_probe)

    filtered = service_module._filter_supported_tools(
        [
            "app.services.agent.runtime_backends.aiasys.tools.task_tool:AgentTool",
            "app.services.agent.runtime_backends.aiasys.tools.task_tool:TaskTool",
            TODO_LIST_TOOL_PATH,
            "app.agents.tools.unknown:Missing",
        ]
    )

    assert filtered == [
        NATIVE_TASK_TOOL_PATH,
        TODO_LIST_TOOL_PATH,
    ]


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _write_legacy_tools_config(tmp_path: Path) -> None:
    config_root = tmp_path / "local_default" / "global_workspace" / ".aiasys" / "agent_config"
    mode_dir = config_root / AgentMode.ANALYSIS.value
    mode_dir.mkdir(parents=True, exist_ok=True)

    (config_root / "user_config.yaml").write_text(
        yaml.dump(
            {
                "version": "1.0",
                "modes": {
                    AgentMode.ANALYSIS.value: {
                        "enabled": True,
                        "tools_path": f"{AgentMode.ANALYSIS.value}/tools.yaml",
                    }
                },
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (mode_dir / "tools.yaml").write_text(
        yaml.dump(
            {
                "disabled_tools": [NATIVE_TASK_TOOL_PATH],
                "extra_tools": [
                    NATIVE_TASK_TOOL_PATH,
                    "app.agents.tools.web:SearchWeb",
                ],
                "tool_overrides": {
                    NATIVE_TASK_TOOL_PATH: {
                        "name": NATIVE_TASK_TOOL_PATH,
                        "timeout": 12,
                    }
                },
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

"""Execution Resource Group 单元与集成测试。

覆盖 WorkspaceRuntimeBinding 新旧字段兼容、工作区创建时多运行时初始化、
模板 runtime_resources 解析。
"""

from __future__ import annotations

import pytest

from app.core.templates import _parse_runtime_resources
from app.models.workspace import ExecutionResourceGroup, WorkspaceRuntimeBinding
from app.services.workspace_registry import (
    _merge_workspace_runtime_binding,
    _normalize_workspace_runtime_binding,
)


def test_workspace_runtime_binding_legacy_env_id_syncs_to_resources() -> None:
    binding = WorkspaceRuntimeBinding(env_id="workspace-default")
    assert binding.resources.python_env_id == "workspace-default"
    assert binding.env_id == "workspace-default"


def test_workspace_runtime_binding_resources_syncs_to_legacy_env_id() -> None:
    binding = WorkspaceRuntimeBinding(
        resources=ExecutionResourceGroup(python_env_id="my-python")
    )
    assert binding.env_id == "my-python"


def test_workspace_runtime_binding_docker_validation() -> None:
    with pytest.raises(ValueError):
        WorkspaceRuntimeBinding(
            resources=ExecutionResourceGroup(
                python_env_id="py",
                docker_resource_id="docker-1",
            )
        )


def test_normalize_workspace_runtime_binding_with_resources() -> None:
    binding = _normalize_workspace_runtime_binding({
        "resources": {
            "python_env_id": "workspace-default",
            "node_env_id": "node-default",
        },
        "env_vars": {"FOO": "bar"},
    })
    assert binding.resources.python_env_id == "workspace-default"
    assert binding.resources.node_env_id == "node-default"
    assert binding.env_id == "workspace-default"
    assert binding.sandbox_mode == "local"


def test_normalize_workspace_runtime_binding_legacy_only() -> None:
    binding = _normalize_workspace_runtime_binding({
        "env_id": "legacy-python",
        "sandbox_mode": "local",
    })
    assert binding.resources.python_env_id == "legacy-python"
    assert binding.env_id == "legacy-python"


def test_merge_workspace_runtime_binding_updates_resources() -> None:
    base = _normalize_workspace_runtime_binding({
        "resources": {"python_env_id": "py1"},
    })
    merged = _merge_workspace_runtime_binding(
        base,
        {"resources": {"node_env_id": "node1"}},
    )
    assert merged.resources.python_env_id == "py1"
    assert merged.resources.node_env_id == "node1"


def test_parse_runtime_resources_from_contract() -> None:
    resources = _parse_runtime_resources({
        "resources": {
            "python_env_id": "workspace-default",
            "node_env_id": "node-default",
        }
    })
    assert resources.python_env_id == "workspace-default"
    assert resources.node_env_id == "node-default"


def test_parse_runtime_resources_legacy_env_id() -> None:
    resources = _parse_runtime_resources({"env_id": "legacy-python"})
    assert resources.python_env_id == "legacy-python"



def test_create_workspace_docker_clears_local_envs() -> None:
    binding = _normalize_workspace_runtime_binding({
        "resources": {
            "python_env_id": "workspace-default",
            "docker_resource_id": "docker-1",
        }
    })
    assert binding.sandbox_mode == "docker"
    assert binding.resources.python_env_id is None
    assert binding.resources.docker_resource_id == "docker-1"

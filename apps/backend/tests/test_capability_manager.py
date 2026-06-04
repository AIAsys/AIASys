from __future__ import annotations

from pathlib import Path

import pytest
import tomli_w

from app.capabilities import source_registry as source_registry_module
from app.capabilities.manager import CapabilityManager
from app.capabilities.models import CapabilityKind, WorkspaceCapability
from app.skills import SkillManager
from app.skills import manager as skill_manager_module


def _configure_capability_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    builtin_dir = tmp_path / "capability_sources" / "builtin"
    store_dir = tmp_path / "capability_sources" / "store"
    skill_builtin_dir = tmp_path / "skills" / "builtin"
    skill_store_dir = tmp_path / "skills" / "store"
    monkeypatch.setattr(source_registry_module, "_BUILTIN_SOURCES_DIR", builtin_dir)
    monkeypatch.setattr(source_registry_module, "_STORE_SOURCES_DIR", store_dir)
    monkeypatch.setattr(source_registry_module, "_SKILL_BUILTIN_DIR", skill_builtin_dir)
    monkeypatch.setattr(source_registry_module, "_SKILL_STORE_DIR", skill_store_dir)
    return builtin_dir


def _configure_skill_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    builtin_dir = tmp_path / "skills" / "builtin"
    store_dir = tmp_path / "skills" / "store"
    monkeypatch.setattr(SkillManager, "SKILLS_BUILTIN_DIR", builtin_dir)
    monkeypatch.setattr(SkillManager, "SKILLS_STORE_DIR", store_dir)
    monkeypatch.setattr(skill_manager_module, "_skill_manager", None)
    return builtin_dir


def _write_manifest(source_dir: Path, capability_id: str) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "manifest.toml").write_text(
        tomli_w.dumps(
            {
                "capability_id": capability_id,
                "display_name": capability_id,
            },
        ),
        encoding="utf-8",
    )


def _write_skill_source(source_dir: Path, skill_name: str) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "SKILL.md").write_text(
        f"+++\nname = \"{skill_name}\"\ndescription = \"Demo\"\n+++\n\n# Demo\n",
        encoding="utf-8",
    )


def test_deactivate_skill_removes_declaration_when_skill_is_uninstalled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cap_builtin_dir = _configure_capability_sources(tmp_path, monkeypatch)
    skill_builtin_dir = _configure_skill_sources(tmp_path, monkeypatch)
    _write_manifest(cap_builtin_dir / "skill" / "demo-skill", "demo-skill")
    _write_manifest(skill_builtin_dir / "demo-skill", "demo-skill")
    _write_skill_source(skill_builtin_dir / "demo-skill", "demo-skill")

    workspace_path = tmp_path / "workspaces" / "local_default" / "workspace-a"
    manager = CapabilityManager()

    installed = manager.install("demo-skill", workspace_path)
    assert installed.success is True
    assert (workspace_path / ".aiasys" / "skills" / "demo-skill").exists()
    assert "demo-skill" in manager._read_declarations(workspace_path)

    deactivated = manager.deactivate("demo-skill", workspace_path)

    assert deactivated.success is True
    assert not (workspace_path / ".aiasys" / "skills" / "demo-skill").exists()
    assert "demo-skill" not in manager._read_declarations(workspace_path)


def test_deactivate_stale_subagent_declaration_cleans_without_policy_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cap_builtin_dir = _configure_capability_sources(tmp_path, monkeypatch)
    _write_manifest(cap_builtin_dir / "subagent" / "coder", "coder")

    workspace_path = tmp_path / "workspaces" / "local_default" / "workspace-a"
    manager = CapabilityManager()
    manager._write_declaration(
        workspace_path,
        WorkspaceCapability(
            capability_id="coder",
            kind=CapabilityKind.SUBAGENT,
            enabled=True,
            source="builtin",
        ),
    )

    deactivated = manager.deactivate("coder", workspace_path)

    assert deactivated.success is True
    assert "coder" not in manager._read_declarations(workspace_path)
    assert not (
        workspace_path / ".aiasys" / "agent_config" / "collaboration_roles.json"
    ).exists()

from __future__ import annotations

import json
from pathlib import Path

import tomli_w
import yaml

from app.capabilities.providers.skill_provider import SkillProvider


def _write_source(
    source_dir: Path,
    *,
    config_example_json: dict[str, str] | None = None,
    config_example_yaml: str | None = None,
) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "manifest.toml").write_text(
        tomli_w.dumps(
            {
                "capability_id": "demo-skill",
                "display_name": "Demo Skill",
            }
        ),
        encoding="utf-8",
    )
    (source_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Demo\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    if config_example_json is not None:
        (source_dir / "config.example.json").write_text(
            json.dumps(config_example_json),
            encoding="utf-8",
        )
    if config_example_yaml is not None:
        (source_dir / "config.example.yaml").write_text(
            config_example_yaml,
            encoding="utf-8",
        )


def test_skill_provider_writes_config_inside_installed_skill_dir(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source" / "demo-skill"
    workspace_path = tmp_path / "workspace"
    _write_source(source_dir)

    provider = SkillProvider()
    result = provider.install(
        "demo-skill",
        workspace_path,
        source_dir,
        config={"api_key": "demo"},
    )

    assert result.success is True
    config_path = workspace_path / ".aiasys" / "skills" / "demo-skill" / "config.json"
    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "api_key": "demo",
    }
    assert not (workspace_path / ".agents" / "skills" / "demo-skill").exists()


def test_skill_provider_copies_config_example_inside_installed_skill_dir(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source" / "demo-skill"
    workspace_path = tmp_path / "workspace"
    _write_source(source_dir, config_example_json={"api_key": "demo"})

    provider = SkillProvider()
    result = provider.install("demo-skill", workspace_path, source_dir)

    assert result.success is True
    config_path = workspace_path / ".aiasys" / "skills" / "demo-skill" / "config.json"
    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "api_key": "demo",
    }
    assert not (workspace_path / ".agents" / "skills" / "demo-skill").exists()


def test_skill_provider_uninstall_removes_skill_dir_with_config(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source" / "demo-skill"
    workspace_path = tmp_path / "workspace"
    _write_source(source_dir)

    provider = SkillProvider()
    installed = provider.install(
        "demo-skill",
        workspace_path,
        source_dir,
        config={"api_key": "demo"},
    )
    assert installed.success is True

    removed = provider.uninstall("demo-skill", workspace_path)

    assert removed.success is True
    assert not (workspace_path / ".aiasys" / "skills" / "demo-skill").exists()
    assert not (workspace_path / ".agents" / "skills" / "demo-skill").exists()


def test_skill_provider_uses_json_config_example_when_present(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source" / "demo-skill"
    workspace_path = tmp_path / "workspace"
    _write_source(source_dir, config_example_json={"api_key": "demo"})

    provider = SkillProvider()
    result = provider.install("demo-skill", workspace_path, source_dir)

    assert result.success is True
    config_path = workspace_path / ".aiasys" / "skills" / "demo-skill" / "config.json"
    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "api_key": "demo",
    }


def test_skill_provider_uses_yaml_config_example_when_present(tmp_path: Path) -> None:
    source_dir = tmp_path / "source" / "demo-skill"
    workspace_path = tmp_path / "workspace"
    _write_source(source_dir, config_example_yaml="api_key: demo\n")

    provider = SkillProvider()
    result = provider.install("demo-skill", workspace_path, source_dir)

    assert result.success is True
    config_path = workspace_path / ".aiasys" / "skills" / "demo-skill" / "config.yaml"
    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == {
        "api_key": "demo",
    }

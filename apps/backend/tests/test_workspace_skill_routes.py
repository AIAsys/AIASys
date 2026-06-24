from __future__ import annotations

import inspect
import io
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.api.routes import skills as skills_route
from app.core.config import RUNTIME_ROOT
from app.models.user import UserInfo
from app.skills.manager import SkillManager


def test_skill_manager_store_dir_points_to_runtime_root() -> None:
    # 桌面打包模式下 AIASYS_RUNTIME_ROOT 指向用户可写目录，store 必须可写
    expected_dir = RUNTIME_ROOT / "skills" / "store"
    assert SkillManager.SKILLS_STORE_DIR == expected_dir
    assert SkillManager.SKILLS_STORE_DIR.exists()


def test_aiasys_usage_skill_is_system_builtin() -> None:
    manager = SkillManager()

    skills = {skill.name: skill for skill in manager.list_store_skills()}

    assert "aiasys-platform-skill" in skills
    skill = skills["aiasys-platform-skill"]
    assert "平台使用指南" in skill.display_name or "AIASys" in skill.display_name
    assert "RuntimeEnvironment" in skill.description or "UV" in skill.description
    assert skill.entry_relative_path == "SKILL.md"


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _write_skill_package(base_dir: Path, name: str, description: str) -> Path:
    package_dir = base_dir / name
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "+++",
                f'name = "{name}"',
                f'description = "{description}"',
                "+++",
                "",
                f"# {name}",
                "",
                "Skill body",
            ]
        ),
        encoding="utf-8",
    )
    return package_dir


def test_skill_manager_config_example_stays_in_runtime_skill_dir(tmp_path: Path) -> None:
    store_dir = tmp_path / "skills-store"
    package_dir = _write_skill_package(store_dir, "demo-skill", "演示技能")
    (package_dir / SkillManager.CONFIG_EXAMPLE_NAME).write_text(
        '{"api_key": "demo"}',
        encoding="utf-8",
    )
    workspace_path = tmp_path / "workspaces" / "local_default" / "task-alpha"

    manager = SkillManager()
    manager.SKILLS_STORE_DIR = store_dir
    manager.SKILLS_BUILTIN_DIR = tmp_path / "skills-builtin"

    enabled = manager.enable_skill("demo-skill", workspace_path)

    assert enabled.success is True
    assert (workspace_path / ".aiasys" / "skills" / "demo-skill" / "config.json").exists()
    assert not (workspace_path / ".agents" / "skills" / "demo-skill").exists()


def _build_zip_bytes(root_name: str, description: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            f"{root_name}/SKILL.md",
            "\n".join(
                [
                    "+++",
                    f'name = "{root_name}"',
                    f'description = "{description}"',
                    "+++",
                    "",
                    f"# {root_name}",
                    "",
                    "Imported skill body",
                ]
            ),
        )
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_skill_routes_support_enable_and_entry_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_dir = tmp_path / "skills-store"
    _write_skill_package(store_dir, "demo-skill", "演示技能")

    monkeypatch.setattr(skills_route, "WORKSPACE_DIR", tmp_path)
    manager = SkillManager()
    monkeypatch.setattr(manager, "SKILLS_STORE_DIR", store_dir)
    monkeypatch.setattr(manager, "SKILLS_BUILTIN_DIR", tmp_path / "skills-builtin")
    monkeypatch.setattr(skills_route, "get_skill_manager", lambda: manager)

    # 全局仓库应有 1 个 skill
    store_list = await skills_route.list_store_skills(current_user=_build_user())
    assert store_list.total == 1
    assert store_list.skills[0].name == "demo-skill"

    # 工作区尚未启用
    workspace_skills = await skills_route.list_workspace_skills(
        "task-alpha",
        current_user=_build_user(),
    )
    assert workspace_skills.total == 0

    # 启用 skill
    enabled = await skills_route.enable_skill_for_workspace(
        "task-alpha",
        skills_route.EnableSkillRequest(skill_name="demo-skill"),
        current_user=_build_user(),
    )
    assert enabled.success is True

    # 工作区应已启用
    workspace_skills = await skills_route.list_workspace_skills(
        "task-alpha",
        current_user=_build_user(),
    )
    assert workspace_skills.total == 1
    assert workspace_skills.skills[0].name == "demo-skill"
    assert workspace_skills.skills[0].source == "workspace"

    # 读取 entry
    entry = await skills_route.get_workspace_skill_entry(
        "task-alpha",
        "demo-skill",
        current_user=_build_user(),
    )
    assert entry.entry_relative_path == "SKILL.md"
    assert "演示技能" in entry.content

    # 禁用 skill
    disabled = await skills_route.disable_skill_for_workspace(
        "task-alpha",
        skills_route.DisableSkillRequest(skill_name="demo-skill"),
        current_user=_build_user(),
    )
    assert disabled.success is True

    workspace_skills_after_disable = await skills_route.list_workspace_skills(
        "task-alpha",
        current_user=_build_user(),
    )
    assert workspace_skills_after_disable.total == 0


@pytest.mark.asyncio
async def test_skill_routes_support_zip_import_to_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_dir = tmp_path / "skills-store"
    store_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(skills_route, "WORKSPACE_DIR", tmp_path)
    manager = SkillManager()
    monkeypatch.setattr(manager, "SKILLS_STORE_DIR", store_dir)
    monkeypatch.setattr(manager, "SKILLS_BUILTIN_DIR", tmp_path / "skills-builtin")
    monkeypatch.setattr(skills_route, "get_skill_manager", lambda: manager)

    upload = UploadFile(
        file=io.BytesIO(_build_zip_bytes("zip-demo", "zip 导入技能")),
        filename="zip-demo.zip",
    )

    # 导入到全局仓库
    imported = await skills_route.import_skill_to_store(
        file=upload,
        force=False,
        current_user=_build_user(),
    )
    assert imported.success is True
    assert imported.skill_name == "zip-demo"

    # 全局仓库应有 1 个
    store_list = await skills_route.list_store_skills(current_user=_build_user())
    assert store_list.total == 1
    assert store_list.skills[0].name == "zip-demo"

    # 在工作区启用
    enabled = await skills_route.enable_skill_for_workspace(
        "task-zip",
        skills_route.EnableSkillRequest(skill_name="zip-demo"),
        current_user=_build_user(),
    )
    assert enabled.success is True

    workspace_skills = await skills_route.list_workspace_skills(
        "task-zip",
        current_user=_build_user(),
    )
    assert workspace_skills.total == 1
    assert workspace_skills.skills[0].name == "zip-demo"

    entry = await skills_route.get_workspace_skill_entry(
        "task-zip",
        "zip-demo",
        current_user=_build_user(),
    )
    assert entry.description == "zip 导入技能"
    assert "Imported skill body" in entry.content


@pytest.mark.asyncio
async def test_enable_skill_rejects_missing_store_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_dir = tmp_path / "skills-store"
    store_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(skills_route, "WORKSPACE_DIR", tmp_path)
    manager = SkillManager()
    monkeypatch.setattr(manager, "SKILLS_STORE_DIR", store_dir)
    monkeypatch.setattr(manager, "SKILLS_BUILTIN_DIR", tmp_path / "skills-builtin")
    monkeypatch.setattr(skills_route, "get_skill_manager", lambda: manager)

    with pytest.raises(HTTPException) as exc_info:
        await skills_route.enable_skill_for_workspace(
            "task-missing",
            skills_route.EnableSkillRequest(skill_name="missing-skill"),
            current_user=_build_user(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Skill 仓库中不存在 Skill 'missing-skill'"


@pytest.mark.asyncio
async def test_enable_skill_requires_force_to_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_dir = tmp_path / "skills-store"
    _write_skill_package(store_dir, "demo-skill", "初始 store 描述")

    monkeypatch.setattr(skills_route, "WORKSPACE_DIR", tmp_path)
    manager = SkillManager()
    monkeypatch.setattr(manager, "SKILLS_STORE_DIR", store_dir)
    monkeypatch.setattr(manager, "SKILLS_BUILTIN_DIR", tmp_path / "skills-builtin")
    monkeypatch.setattr(skills_route, "get_skill_manager", lambda: manager)

    first_enable = await skills_route.enable_skill_for_workspace(
        "task-force",
        skills_route.EnableSkillRequest(skill_name="demo-skill"),
        current_user=_build_user(),
    )
    assert first_enable.success is True

    # 更新 store 中的描述
    _write_skill_package(store_dir, "demo-skill", "覆盖后的 store 描述")

    with pytest.raises(HTTPException) as exc_info:
        await skills_route.enable_skill_for_workspace(
            "task-force",
            skills_route.EnableSkillRequest(skill_name="demo-skill"),
            current_user=_build_user(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "工作区中已启用 Skill 'demo-skill'"

    forced_enable = await skills_route.enable_skill_for_workspace(
        "task-force",
        skills_route.EnableSkillRequest(skill_name="demo-skill", force=True),
        current_user=_build_user(),
    )
    assert forced_enable.success is True

    entry = await skills_route.get_workspace_skill_entry(
        "task-force",
        "demo-skill",
        current_user=_build_user(),
    )
    assert "覆盖后的 store 描述" in entry.content


@pytest.mark.asyncio
async def test_skill_routes_support_store_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_dir = tmp_path / "skills-store"
    _write_skill_package(store_dir, "to-delete", "将被删除的技能")

    monkeypatch.setattr(skills_route, "WORKSPACE_DIR", tmp_path)
    manager = SkillManager()
    monkeypatch.setattr(manager, "SKILLS_STORE_DIR", store_dir)
    monkeypatch.setattr(manager, "SKILLS_BUILTIN_DIR", tmp_path / "skills-builtin")
    monkeypatch.setattr(skills_route, "get_skill_manager", lambda: manager)

    store_list_before = await skills_route.list_store_skills(current_user=_build_user())
    assert store_list_before.total == 1

    deleted = await skills_route.delete_store_skill(
        "to-delete",
        current_user=_build_user(),
    )
    assert deleted.success is True

    store_list_after = await skills_route.list_store_skills(current_user=_build_user())
    assert store_list_after.total == 0

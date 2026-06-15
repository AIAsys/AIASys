from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.agents.tools.skill_tools import SearchStoreSkills
from app.skills.models import SkillInfo


class _FakeSkillManager:
    def list_store_skills(self) -> list[SkillInfo]:
        return [
            SkillInfo(
                name="demo-skill",
                display_name="Demo Skill",
                description="演示用 Skill",
                source="builtin",
                path=Path("/tmp/demo-skill"),
                entry_path=Path("/tmp/demo-skill/SKILL.md"),
                entry_relative_path="SKILL.md",
            )
        ]


@pytest.mark.asyncio
async def test_search_store_skills_returns_candidate_without_forcing_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.skills.manager as skill_manager_module

    monkeypatch.setattr(
        skill_manager_module,
        "get_skill_manager",
        lambda: _FakeSkillManager(),
    )

    result = await SearchStoreSkills().invoke(query="demo")

    assert result.is_error is False
    assert "Skill 仓库中找到 1 个 Skill" in result.content
    # 当前 SearchStoreSkills 文案已改为强制化：找到候选后立即启用，不再让 Agent 自行判断
    assert "立即调用 EnableSkill" in result.content
    assert "请根据当前任务判断是否需要启用 Skill" not in result.content
    assert "已获授权" not in result.content


def test_builtin_skill_references_from_prompts_and_presets_are_loadable() -> None:
    from app.services.agent.system_presets import DATA_ANALYSIS_BASELINE, DATA_ANALYST_BASELINE
    from app.skills.manager import get_skill_manager

    backend_root = Path(__file__).resolve().parents[1]
    prompt_paths = [
        backend_root / "app/agents/local_sandbox_agent_config/general_host_prompt.md",
        backend_root / "app/agents/local_sandbox_agent_config/subagent_data_analyst_prompt.md",
    ]
    referenced_names: set[str] = set()
    for prompt_path in prompt_paths:
        prompt_text = prompt_path.read_text(encoding="utf-8")
        referenced_names.update(
            re.findall(r"LoadSkill\(name=[\"']([^\"']+)[\"']\)", prompt_text)
        )
    referenced_names.update(DATA_ANALYSIS_BASELINE.skills)
    referenced_names.update(DATA_ANALYST_BASELINE.skills)

    manager = get_skill_manager()
    store_names = {skill.name for skill in manager.list_store_skills()}
    missing = sorted(name for name in referenced_names if name not in store_names)

    assert missing == []
    for skill_name in sorted(referenced_names):
        loaded = manager.get_skill_file_content(
            skill_name=skill_name,
            workspace_path=backend_root,
        )
        assert loaded is not None, skill_name

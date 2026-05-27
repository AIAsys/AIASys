from __future__ import annotations

from typing import Any

import pytest

from app.services.skill_external_market_service import (
    AIASysBuiltinSkillAdapter,
    ExternalSkillMarketService,
    SkillHubExternalSkillAdapter,
    SkillsMPExternalSkillAdapter,
    _parse_github_tree_url,
    _skillsmp_slug_from_github_url,
)


def _api_item(
    slug: str,
    *,
    name: str | None = None,
    description: str | None = None,
    description_zh: str | None = None,
    category: str | None = None,
    version: str | None = None,
    downloads: int | None = None,
    installs: int | None = None,
    stars: int | None = None,
    score: float | None = None,
    owner_name: str | None = None,
    source: str | None = None,
    icon_url: str | None = None,
    labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "slug": slug,
        "name": name or slug,
        "description": description or f"{slug} description",
        "category": category,
        "downloads": downloads,
        "stars": stars,
        "score": score,
    }
    if description_zh is not None:
        payload["description_zh"] = description_zh
    if version is not None:
        payload["version"] = version
    if installs is not None:
        payload["installs"] = installs
    if owner_name is not None:
        payload["ownerName"] = owner_name
    if source is not None:
        payload["source"] = source
    if icon_url is not None:
        payload["iconUrl"] = icon_url
    if labels is not None:
        payload["labels"] = labels
    return payload


def _api_response(skills: list[dict[str, Any]], total: int | None = None) -> dict[str, Any]:
    return {
        "skills": skills,
        "total": total if total is not None else len(skills),
    }


@pytest.mark.asyncio
async def test_skillhub_list_items_returns_items_from_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SkillHubExternalSkillAdapter()

    async def fake_fetch_api_page(**kwargs: Any) -> dict[str, Any]:
        return _api_response([
            _api_item("github", name="GitHub", description="index github", score=99),
            _api_item("browser-use", name="Browser Use", description="browser", score=88),
            _api_item("local-tool", name="Local Tool", description="local", score=77),
        ])

    monkeypatch.setattr(adapter, "_fetch_api_page", fake_fetch_api_page)

    response = await adapter.list_items(
        search=None,
        category=None,
        sort_by="recommended",
        page_number=1,
        page_size=24,
    )

    assert response.total_count == 3
    assert len(response.items) == 3
    assert [item.slug for item in response.items] == ["github", "browser-use", "local-tool"]


@pytest.mark.asyncio
async def test_skillhub_list_items_passes_search_keyword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SkillHubExternalSkillAdapter()

    captured_keyword: str | None = None

    async def fake_fetch_api_page(*, keyword: str | None = None, **kwargs: Any) -> dict[str, Any]:
        nonlocal captured_keyword
        captured_keyword = keyword
        return _api_response([
            _api_item("python-helper", name="Python Helper", score=95),
        ])

    monkeypatch.setattr(adapter, "_fetch_api_page", fake_fetch_api_page)

    await adapter.list_items(
        search="python",
        category=None,
        sort_by="downloads",
        page_number=1,
        page_size=24,
    )

    assert captured_keyword == "python"


@pytest.mark.asyncio
async def test_skillhub_list_items_filters_by_category_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SkillHubExternalSkillAdapter()

    async def fake_fetch_api_page(**kwargs: Any) -> dict[str, Any]:
        return _api_response([
            _api_item("skill-a", name="Skill A", category="ai", score=90),
            _api_item("skill-b", name="Skill B", category="tools", score=80),
            _api_item("skill-c", name="Skill C", category="ai", score=70),
        ])

    monkeypatch.setattr(adapter, "_fetch_api_page", fake_fetch_api_page)

    response = await adapter.list_items(
        search=None,
        category="ai",
        sort_by="recommended",
        page_number=1,
        page_size=24,
    )

    assert response.total_count == 3
    assert [item.slug for item in response.items] == ["skill-a", "skill-c"]


@pytest.mark.asyncio
async def test_skillhub_list_items_handles_api_error_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SkillHubExternalSkillAdapter()

    async def fake_fetch_api_page(**kwargs: Any) -> dict[str, Any]:
        raise ValueError("API not available")

    monkeypatch.setattr(adapter, "_fetch_api_page", fake_fetch_api_page)

    response = await adapter.list_items(
        search=None,
        category=None,
        sort_by="recommended",
        page_number=1,
        page_size=24,
    )

    assert response.total_count == 0
    assert response.items == []


@pytest.mark.asyncio
async def test_skillhub_list_items_paginates_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SkillHubExternalSkillAdapter()

    captured_page: int | None = None
    captured_page_size: int | None = None

    async def fake_fetch_api_page(*, page_number: int = 1, page_size: int = 24, **kwargs: Any) -> dict[str, Any]:
        nonlocal captured_page, captured_page_size
        captured_page = page_number
        captured_page_size = page_size
        return _api_response([_api_item("skill-001", score=99)])

    monkeypatch.setattr(adapter, "_fetch_api_page", fake_fetch_api_page)

    await adapter.list_items(
        search=None,
        category=None,
        sort_by="recommended",
        page_number=3,
        page_size=24,
    )

    assert captured_page == 3
    assert captured_page_size == 24


@pytest.mark.asyncio
async def test_skillhub_list_items_passes_sort_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SkillHubExternalSkillAdapter()

    captured_sort_by: str | None = None

    async def fake_fetch_api_page(*, sort_by: str = "recommended", **kwargs: Any) -> dict[str, Any]:
        nonlocal captured_sort_by
        captured_sort_by = sort_by
        return _api_response([_api_item("top-skill", score=100)])

    monkeypatch.setattr(adapter, "_fetch_api_page", fake_fetch_api_page)

    await adapter.list_items(
        search=None,
        category=None,
        sort_by="stars",
        page_number=1,
        page_size=24,
    )

    assert captured_sort_by == "stars"


@pytest.mark.asyncio
async def test_skillhub_list_items_builds_items_with_new_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SkillHubExternalSkillAdapter()

    async def fake_fetch_api_page(**kwargs: Any) -> dict[str, Any]:
        return _api_response([
            _api_item(
                "cool-skill",
                name="Cool Skill",
                description="A very cool skill",
                description_zh="很酷的技能",
                category="ai",
                version="1.2.0",
                downloads=1000,
                installs=500,
                stars=200,
                score=95.5,
                owner_name="devuser",
                source="clawhub",
                icon_url="https://example.com/icon.png",
                labels={"requires_api_key": "false"},
            ),
        ])

    monkeypatch.setattr(adapter, "_fetch_api_page", fake_fetch_api_page)

    response = await adapter.list_items(
        search=None,
        category=None,
        sort_by="recommended",
        page_number=1,
        page_size=24,
    )

    item = response.items[0]
    assert item.slug == "cool-skill"
    assert item.display_name == "Cool Skill"
    assert item.description == "A very cool skill"
    assert item.description_zh == "很酷的技能"
    assert item.version == "1.2.0"
    assert item.downloads == 1000
    assert item.installs == 500
    assert item.stars == 200
    assert item.score == 95.5
    assert item.owner_name == "devuser"
    assert item.source == "clawhub"
    assert item.icon_url == "https://example.com/icon.png"
    assert item.labels == {"requires_api_key": "false"}
    assert item.categories == ["ai"]
    assert item.homepage_url == "https://skillhub.cn/skills/cool-skill"


def test_external_skill_market_service_has_three_sources() -> None:
    service = ExternalSkillMarketService()

    sources = service.list_sources()
    assert len(sources) == 3
    source_ids = {s.source_id for s in sources}
    assert source_ids == {"aiasys", "skillhub", "skillsmp"}

    skillhub_source = next(s for s in sources if s.source_id == "skillhub")
    assert skillhub_source.install_available is True
    assert skillhub_source.install_unavailable_reason is None

    skillsmp_source = next(s for s in sources if s.source_id == "skillsmp")
    assert skillsmp_source.display_name == "SkillsMP"
    assert skillsmp_source.install_available is True


@pytest.mark.asyncio
async def test_aiasys_builtin_market_lists_runtime_environment_skill() -> None:
    adapter = AIASysBuiltinSkillAdapter()

    response = await adapter.list_items(
        search="运行环境",
        category=None,
        sort_by="recommended",
        page_number=1,
        page_size=24,
    )

    items = {item.slug: item for item in response.items}
    assert "aiasys-platform-skill" in items
    item = items["aiasys-platform-skill"]
    assert "平台使用指南" in item.display_name or "AIASys" in item.display_name
    assert "运行环境" in (item.description or "")

    detail = await adapter.get_item_detail("aiasys-platform-skill")
    assert detail.entry_relative_path == "SKILL.md"
    assert "平台使用指南" in detail.item.display_name or "AIASys" in detail.item.display_name
    assert detail.readme_excerpt is not None
    assert "AIASys Platform Guide" in detail.readme_excerpt



def _skillsmp_api_item(
    *,
    id: str = "item-1",
    name: str = "Test Skill",
    description: str = "A test skill",
    github_url: str = "https://github.com/owner/repo/tree/main/skills/test-skill",
    stars: int = 10,
    author: str = "testauthor",
    skill_url: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": id,
        "name": name,
        "description": description,
        "githubUrl": github_url,
        "stars": stars,
        "author": author,
    }
    if skill_url is not None:
        payload["skillUrl"] = skill_url
    return payload


def _skillsmp_api_response(
    skills: list[dict[str, Any]],
    total: int | None = None,
) -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "skills": skills,
            "pagination": {
                "total": total if total is not None else len(skills),
            },
        },
    }


@pytest.mark.asyncio
async def test_skillsmp_list_items_returns_items_from_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SkillsMPExternalSkillAdapter()

    async def fake_fetch_api_page(**kwargs: Any) -> dict[str, Any]:
        return _skillsmp_api_response([
            _skillsmp_api_item(
                id="s1",
                name="Skill One",
                github_url="https://github.com/owner/repo/tree/main/skills/skill-one",
                stars=100,
            ),
            _skillsmp_api_item(
                id="s2",
                name="Skill Two",
                github_url="https://github.com/owner/repo/tree/main/skills/skill-two",
                stars=50,
            ),
        ], total=2)["data"]

    monkeypatch.setattr(adapter, "_fetch_api_page", fake_fetch_api_page)

    response = await adapter.list_items(
        search=None,
        category=None,
        sort_by="recommended",
        page_number=1,
        page_size=24,
    )

    assert response.total_count == 2
    assert len(response.items) == 2
    assert response.items[0].display_name == "Skill One"
    assert response.items[0].stars == 100
    assert response.items[0].source_id == "skillsmp"
    assert response.items[0].source == "github"
    assert response.items[1].display_name == "Skill Two"


@pytest.mark.asyncio
async def test_skillsmp_list_items_passes_search_keyword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SkillsMPExternalSkillAdapter()

    captured_keyword: str | None = None

    async def fake_fetch_api_page(*, keyword: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal captured_keyword
        captured_keyword = keyword
        return _skillsmp_api_response([])

    monkeypatch.setattr(adapter, "_fetch_api_page", fake_fetch_api_page)

    await adapter.list_items(
        search="python",
        category=None,
        sort_by="recommended",
        page_number=1,
        page_size=24,
    )

    assert captured_keyword == "python"


@pytest.mark.asyncio
async def test_skillsmp_list_items_uses_default_query_when_search_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SkillsMPExternalSkillAdapter()

    captured_keyword: str | None = None

    async def fake_fetch_api_page(*, keyword: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal captured_keyword
        captured_keyword = keyword
        return _skillsmp_api_response([])

    monkeypatch.setattr(adapter, "_fetch_api_page", fake_fetch_api_page)

    await adapter.list_items(
        search=None,
        category=None,
        sort_by="recommended",
        page_number=1,
        page_size=24,
    )

    assert captured_keyword is not None and captured_keyword != ""


@pytest.mark.asyncio
async def test_skillsmp_list_items_handles_api_error_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SkillsMPExternalSkillAdapter()

    async def fake_fetch_api_page(**kwargs: Any) -> dict[str, Any]:
        raise ValueError("API not available")

    monkeypatch.setattr(adapter, "_fetch_api_page", fake_fetch_api_page)

    response = await adapter.list_items(
        search=None,
        category=None,
        sort_by="recommended",
        page_number=1,
        page_size=24,
    )

    assert response.total_count == 0
    assert response.items == []


@pytest.mark.asyncio
async def test_skillsmp_get_item_detail_fetches_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SkillsMPExternalSkillAdapter()

    async def fake_fetch_skill_markdown(github_url: str) -> tuple[str | None, str | None]:
        return ("# Test Skill\n\nThis is a test skill.", "SKILL.md")

    monkeypatch.setattr(adapter, "_fetch_skill_markdown", fake_fetch_skill_markdown)

    github_url = "https://github.com/owner/repo/tree/main/skills/test-skill"
    detail = await adapter.get_item_detail(github_url)

    assert detail.item.slug == _skillsmp_slug_from_github_url(github_url)
    assert detail.readme_excerpt == "# Test Skill\n\nThis is a test skill."
    assert detail.entry_relative_path == "SKILL.md"
    assert detail.can_install is True


@pytest.mark.asyncio
async def test_skillsmp_get_item_detail_without_cache_builds_minimal_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SkillsMPExternalSkillAdapter()

    async def fake_fetch_skill_markdown(github_url: str) -> tuple[str | None, str | None]:
        return (None, None)

    monkeypatch.setattr(adapter, "_fetch_skill_markdown", fake_fetch_skill_markdown)

    github_url = "https://github.com/owner/repo/tree/main/skills/test-skill"
    detail = await adapter.get_item_detail(github_url)

    assert detail.item.item_id == github_url
    assert detail.readme_excerpt is None
    assert detail.entry_relative_path is None


@pytest.mark.asyncio
async def test_skillsmp_build_item_skips_missing_github_url() -> None:
    adapter = SkillsMPExternalSkillAdapter()

    item = adapter._build_item({"id": "x", "name": "No URL"})
    assert item is None


@pytest.mark.asyncio
async def test_skillsmp_build_item_skips_invalid_github_url() -> None:
    adapter = SkillsMPExternalSkillAdapter()

    item = adapter._build_item({
        "id": "x",
        "name": "Bad URL",
        "githubUrl": "not-a-url",
    })
    assert item is None


def test_skillsmp_parse_github_tree_url_valid() -> None:
    owner, repo, ref, path = _parse_github_tree_url(
        "https://github.com/owner/repo/tree/main/skills/my-skill"
    )
    assert owner == "owner"
    assert repo == "repo"
    assert ref == "main"
    assert path == "skills/my-skill"


def test_skillsmp_parse_github_tree_url_with_encoded_chars() -> None:
    owner, repo, ref, path = _parse_github_tree_url(
        "https://github.com/owner/repo/tree/v1.0.0/skills/my%20skill"
    )
    assert owner == "owner"
    assert repo == "repo"
    assert ref == "v1.0.0"
    assert path == "skills/my skill"


def test_skillsmp_parse_github_tree_url_invalid_scheme() -> None:
    with pytest.raises(ValueError, match="GitHub tree URL"):
        _parse_github_tree_url("http://github.com/owner/repo/tree/main/skills/skill")


def test_skillsmp_parse_github_tree_url_missing_tree() -> None:
    with pytest.raises(ValueError, match="格式不受支持"):
        _parse_github_tree_url("https://github.com/owner/repo/blob/main/skills/skill")


def test_skillsmp_parse_github_tree_url_too_short() -> None:
    with pytest.raises(ValueError, match="格式不受支持"):
        _parse_github_tree_url("https://github.com/owner/repo/tree/main")


def test_skillsmp_slug_from_github_url() -> None:
    github_url = "https://github.com/owner/repo/tree/main/skills/my-skill"
    slug = _skillsmp_slug_from_github_url(github_url)
    assert slug.startswith("skillsmp-")
    assert "owner" in slug
    assert "repo" in slug
    assert "my-skill" in slug


@pytest.mark.asyncio
async def test_skillsmp_install_item_downloads_and_installs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    adapter = SkillsMPExternalSkillAdapter()

    async def fake_download_github_skill_dir(github_url: str, target_dir: Path) -> Path:
        pkg_dir = target_dir / "package"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        skill_md = pkg_dir / "SKILL.md"
        skill_md.write_text("# Test\n")
        return pkg_dir

    installed_calls: list[dict[str, Any]] = []

    def fake_install(
        skill_name: str,
        *,
        source_dir: Path,
        workspace_path: Path,
        force: bool,
    ) -> None:
        installed_calls.append({
            "skill_name": skill_name,
            "source_dir": str(source_dir),
            "workspace_path": str(workspace_path),
            "force": force,
        })

    monkeypatch.setattr(adapter, "_download_github_skill_dir", fake_download_github_skill_dir)
    monkeypatch.setattr(
        "app.services.skill_external_market_service._install_directory_to_store_and_workspace",
        fake_install,
    )

    github_url = "https://github.com/owner/repo/tree/main/skills/my-skill"
    result = await adapter.install_item(
        github_url,
        workspace_path=tmp_path,
        force=False,
    )

    assert result == _skillsmp_slug_from_github_url(github_url)
    assert len(installed_calls) == 1
    assert installed_calls[0]["skill_name"] == _skillsmp_slug_from_github_url(github_url)
    assert installed_calls[0]["workspace_path"] == str(tmp_path)
    assert installed_calls[0]["force"] is False

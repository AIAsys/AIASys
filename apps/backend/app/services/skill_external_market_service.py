"""
外部 Skill 市场服务

目标不是把 SkillHub 之类的第三方平台抬成产品中心，而是把外部目录源收敛成
AIASys 自己的"外部 Skill 市场"供给层。
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import tempfile
import zipfile
from collections import OrderedDict
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import quote, unquote, urlparse

import httpx

from app.models.external_skill_market import (
    ExternalSkillMarketDetailResponse,
    ExternalSkillMarketItem,
    ExternalSkillMarketListResponse,
    ExternalSkillMarketSource,
)
from app.skills.manager import get_skill_manager

logger = logging.getLogger(__name__)


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_text_list(value: Any) -> list[str]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        return []
    result: list[str] = []
    for item in value:
        text = _string_or_none(item)
        if text:
            result.append(text)
    return result


def _truncate_text(value: str | None, limit: int = 1600) -> str | None:
    text = _string_or_none(value)
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _normalize_search_tokens(value: str | None) -> list[str]:
    text = _string_or_none(value)
    if not text:
        return []
    return [token for token in re.split(r"\s+", text.lower()) if token]


def _validate_skill_slug(value: str) -> str:
    slug = _string_or_none(value)
    if not slug:
        raise ValueError("无效的 Skill 标识")
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", slug):
        raise ValueError("Skill 标识包含非法字符")
    return slug


def _find_entry_file(package_dir: Path) -> Path | None:
    candidates = sorted(
        (path for path in package_dir.rglob("SKILL.md") if path.is_file()),
        key=lambda path: (len(path.relative_to(package_dir).parts), path.as_posix()),
    )
    return candidates[0] if candidates else None


def _collect_file_list(package_dir: Path, *, limit: int = 16) -> list[str]:
    files = sorted(
        (
            path.relative_to(package_dir).as_posix()
            for path in package_dir.rglob("*")
            if path.is_file()
        )
    )
    return files[:limit]


_SKILLHUB_API_BASE = os.environ.get(
    "AIASYS_SKILLHUB_API_URL",
    "https://api.skillhub.cn/api/skills",
).strip()
_SKILLHUB_DOWNLOAD_TEMPLATE = os.environ.get(
    "AIASYS_SKILLHUB_DOWNLOAD_URL",
    "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/skills/{slug}.zip",
).strip()
_SKILLHUB_PAGE_TEMPLATE = "https://skillhub.cn/skills/{slug}"

_SKILLSMP_API_BASE = os.environ.get(
    "AIASYS_SKILLSMP_API_URL",
    "https://skillsmp.com/api/v1/skills/search",
).strip()
_SKILLSMP_DEFAULT_QUERY = (
    os.environ.get(
        "AIASYS_SKILLSMP_DEFAULT_QUERY",
        "skill",
    ).strip()
    or "skill"
)
_SKILLSMP_PAGE_TEMPLATE = "https://skillsmp.com/skills/{item_id}"


def _external_http_headers(*, accept: str = "application/json") -> dict[str, str]:
    user_agent = os.environ.get("AIASYS_EXTERNAL_MARKET_USER_AGENT", "").strip()
    return {
        "Accept": accept,
        "User-Agent": user_agent or "AIASys/0.1 external-skill-market",
    }


def _skillsmp_headers() -> dict[str, str]:
    headers = _external_http_headers()
    api_key = os.environ.get("AIASYS_SKILLSMP_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _slug_with_hash(prefix: str, value: str, *, limit: int = 150) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-.").lower()
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    if len(normalized) > limit:
        normalized = normalized[:limit].rstrip("-.")
    return _validate_skill_slug(f"{prefix}-{normalized}-{digest}")


def _parse_github_tree_url(github_url: str) -> tuple[str, str, str, str]:
    parsed = urlparse(github_url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError("SkillsMP 条目缺少可安装的 GitHub tree URL")

    parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 5 or parts[2] != "tree":
        raise ValueError("SkillsMP GitHub URL 格式不受支持")

    owner, repo, ref = parts[0], parts[1], parts[3]
    skill_path = "/".join(parts[4:]).strip("/")
    if (
        not re.fullmatch(r"[a-zA-Z0-9._-]+", owner)
        or not re.fullmatch(r"[a-zA-Z0-9._-]+", repo)
        or not ref
        or ".." in parts
        or not skill_path
    ):
        raise ValueError("SkillsMP GitHub URL 包含非法路径")
    return owner, repo, ref, skill_path


def _skillsmp_slug_from_github_url(github_url: str) -> str:
    owner, repo, _ref, skill_path = _parse_github_tree_url(github_url)
    return _slug_with_hash(
        "skillsmp",
        "-".join([owner, repo, *skill_path.split("/")]),
    )


def _install_directory_to_store_and_workspace(
    *,
    skill_name: str,
    source_dir: Path,
    workspace_path: Path,
    force: bool,
) -> None:
    manager = get_skill_manager()
    target_dir = manager.SKILLS_STORE_DIR / skill_name
    if force or not target_dir.exists():
        install_result = manager.install_skill_directory(
            skill_name=skill_name,
            source_dir=source_dir,
            workspace_path=workspace_path,
            force=force,
        )
        if not install_result.success:
            raise ValueError(install_result.message)

    enable_result = manager.enable_skill(
        skill_name,
        workspace_path,
        force=force,
    )
    if not enable_result.success:
        raise ValueError(enable_result.message)


class ExternalSkillMarketAdapter:
    """外部 Skill 市场适配器基类。"""

    source: ExternalSkillMarketSource

    def refresh_source_state(self) -> None:
        """按请求刷新当前源状态。"""

        return None

    async def list_items(
        self,
        *,
        search: str | None,
        category: str | None,
        sort_by: str,
        page_number: int,
        page_size: int,
    ) -> ExternalSkillMarketListResponse:
        raise NotImplementedError

    async def get_item_detail(self, item_id: str) -> ExternalSkillMarketDetailResponse:
        raise NotImplementedError

    async def install_item(
        self,
        item_id: str,
        *,
        workspace_path: Path,
        force: bool,
    ) -> str:
        raise NotImplementedError


class SkillHubExternalSkillAdapter(ExternalSkillMarketAdapter):
    """SkillHub 外部 Skill 目录适配器。

    通过 api.skillhub.cn 公开 API 获取 Skill 列表/搜索/排序，
    安装时直接从 COS 下载 .zip 解压，不再依赖 skillhub CLI。
    """

    _SORT_MAP: dict[str, dict[str, str]] = {
        "recommended": {"sortBy": "score", "order": "desc"},
        "downloads": {"sortBy": "downloads", "order": "desc"},
        "stars": {"sortBy": "stars", "order": "desc"},
    }

    def __init__(self) -> None:
        self.source = self._build_source()

    def _build_source(self) -> ExternalSkillMarketSource:
        return ExternalSkillMarketSource(
            source_id="skillhub",
            display_name="SkillHub",
            description=(
                "通过 SkillHub 公开 API 为 AIASys 提供外部 Skill 供给，"
                "安装直接下载 Skill 包到当前工作区。"
            ),
            supports_public_catalog=True,
            supports_workspace_install=True,
            install_available=True,
            install_unavailable_reason=None,
        )

    def refresh_source_state(self) -> None:
        pass

    def _parse_sort(self, sort_by: str) -> dict[str, str]:
        return self._SORT_MAP.get(sort_by, self._SORT_MAP["recommended"])

    async def _fetch_api_page(
        self,
        *,
        page_number: int = 1,
        page_size: int = 24,
        sort_by: str = "recommended",
        keyword: str | None = None,
    ) -> dict[str, Any]:
        sort_spec = self._parse_sort(sort_by)
        params: dict[str, Any] = {
            "page": page_number,
            "pageSize": page_size,
            "sortBy": sort_spec["sortBy"],
            "order": sort_spec["order"],
        }
        if keyword:
            params["keyword"] = keyword

        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                response = await client.get(
                    _SKILLHUB_API_BASE,
                    params=params,
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("SkillHub API 请求失败: %s -> %s", _SKILLHUB_API_BASE, exc)
            raise ValueError("SkillHub API 暂时不可访问") from exc

        payload = response.json()
        if not isinstance(payload, dict) or payload.get("code") != 0:
            raise ValueError("SkillHub API 返回格式异常")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("SkillHub API 缺少 data 字段")
        return data

    async def _search_single(self, slug: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """按 slug 精确搜索单个 Skill。"""
        try:
            data = await self._fetch_api_page(
                page_number=1,
                page_size=limit,
                sort_by="recommended",
                keyword=slug,
            )
            skills = data.get("skills")
            if not isinstance(skills, list):
                return []
            return [
                item
                for item in skills
                if isinstance(item, dict) and str(item.get("slug") or "").strip() == slug
            ]
        except ValueError:
            return []

    def _build_item(self, raw: dict[str, Any]) -> ExternalSkillMarketItem:
        slug = _validate_skill_slug(str(raw.get("slug") or ""))
        display_name = _string_or_none(raw.get("name")) or slug
        category = _string_or_none(raw.get("category"))
        categories = [category] if category else []
        labels = raw.get("labels")
        if isinstance(labels, dict):
            labels = dict(labels)
        else:
            labels = None
        return ExternalSkillMarketItem(
            source_id=self.source.source_id,
            item_id=slug,
            slug=slug,
            display_name=display_name,
            description=_string_or_none(raw.get("description")),
            summary=_string_or_none(raw.get("summary")),
            description_zh=_string_or_none(raw.get("description_zh")),
            version=_string_or_none(raw.get("version")),
            homepage_url=_SKILLHUB_PAGE_TEMPLATE.format(slug=slug),
            categories=categories,
            labels=labels,
            owner_name=_string_or_none(raw.get("ownerName")),
            source=_string_or_none(raw.get("source")),
            icon_url=_string_or_none(raw.get("iconUrl")),
            downloads=raw.get("downloads") if isinstance(raw.get("downloads"), int) else None,
            installs=raw.get("installs") if isinstance(raw.get("installs"), int) else None,
            stars=raw.get("stars") if isinstance(raw.get("stars"), int) else None,
            score=raw.get("score") if isinstance(raw.get("score"), (int, float)) else None,
            rank=None,
        )

    def _matches_category(self, item: ExternalSkillMarketItem, category: str | None) -> bool:
        if not category:
            return True
        return category in item.categories

    async def _download_and_extract(self, slug: str, target_dir: Path) -> Path:
        """下载 Skill .zip 并解压到目标目录，返回 SKILL.md 所在的实际目录。"""
        download_url = _SKILLHUB_DOWNLOAD_TEMPLATE.format(slug=slug)
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(download_url)
                response.raise_for_status()
                zip_bytes = response.read()
        except httpx.HTTPStatusError as exc:
            raise ValueError(f"Skill 包下载失败: {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ValueError(f"Skill 包下载网络异常: {exc}") from exc

        staging = target_dir / f".staging_{slug}"
        staging.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
                zf.extractall(str(staging))
        except zipfile.BadZipFile as exc:
            raise ValueError(f"Skill 包损坏或格式错误: {exc}") from exc

        # .zip 内容可能直接散落在根目录或以 slug 为子目录名
        slug_dir = staging / slug
        if slug_dir.is_dir():
            slug_dir.rename(target_dir / slug)
        else:
            # 文件散落在根目录，创建 slug 目录并移入
            dest = target_dir / slug
            dest.mkdir(parents=True, exist_ok=True)
            for child in staging.iterdir():
                child.rename(dest / child.name)
        staging.rmdir()
        return target_dir / slug

    async def _inspect_package(
        self,
        slug: str,
    ) -> tuple[str | None, str | None, list[str]]:
        """下载 Skill 包并提取 SKILL.md 内容、入口路径、文件列表。"""
        with tempfile.TemporaryDirectory(prefix="aiasys-skillhub-detail-") as temp_dir:
            install_root = Path(temp_dir) / "skills"
            install_root.mkdir(parents=True, exist_ok=True)
            package_dir = await self._download_and_extract(slug, install_root)
            entry_path = _find_entry_file(package_dir)
            if entry_path is None:
                return None, None, _collect_file_list(package_dir)
            try:
                content = entry_path.read_text(encoding="utf-8")
            except Exception:
                content = None
            return (
                _truncate_text(content),
                entry_path.relative_to(package_dir).as_posix(),
                _collect_file_list(package_dir),
            )

    async def list_items(
        self,
        *,
        search: str | None,
        category: str | None,
        sort_by: str,
        page_number: int,
        page_size: int,
    ) -> ExternalSkillMarketListResponse:
        safe_page_number = max(page_number, 1)
        safe_page_size = max(min(page_size, 60), 1)

        keyword = _string_or_none(search)
        try:
            data = await self._fetch_api_page(
                page_number=safe_page_number,
                page_size=safe_page_size,
                sort_by=sort_by,
                keyword=keyword,
            )
        except ValueError as exc:
            logger.warning("SkillHub API 列表请求失败: %s", exc)
            return ExternalSkillMarketListResponse(
                source=self.source,
                items=[],
                available_categories=[],
                total_count=0,
                page_number=safe_page_number,
                page_size=safe_page_size,
            )

        raw_skills = data.get("skills")
        if not isinstance(raw_skills, list):
            raw_skills = []
        total = data.get("total")
        if not isinstance(total, int):
            total = 0

        items = [
            self._build_item(item)
            for item in raw_skills
            if isinstance(item, dict) and _string_or_none(item.get("slug"))
        ]

        # API 不支持按 category 过滤，在本地做
        normalized_category = _string_or_none(category)
        if normalized_category:
            items = [item for item in items if self._matches_category(item, normalized_category)]

        available_categories = sorted(
            {cat for item in items for cat in item.categories},
            key=lambda value: value.lower(),
        )

        # API 已排序，这里保持原顺序
        return ExternalSkillMarketListResponse(
            source=self.source,
            items=items,
            available_categories=available_categories,
            total_count=total,
            page_number=safe_page_number,
            page_size=safe_page_size,
        )

    async def get_item_detail(self, item_id: str) -> ExternalSkillMarketDetailResponse:
        slug = _validate_skill_slug(item_id)

        # 先通过 API 搜索找到 skill 元数据
        search_results = await self._search_single(slug, limit=5)
        item: ExternalSkillMarketItem
        if search_results:
            item = self._build_item(search_results[0])
        else:
            # 回退：创建一个最小 item（至少能展示下载/安装）
            item = ExternalSkillMarketItem(
                source_id=self.source.source_id,
                item_id=slug,
                slug=slug,
                display_name=slug,
                homepage_url=_SKILLHUB_PAGE_TEMPLATE.format(slug=slug),
            )

        readme_excerpt, entry_relative_path, included_files = await self._inspect_package(slug)
        return ExternalSkillMarketDetailResponse(
            source=self.source,
            item=item,
            readme_excerpt=readme_excerpt,
            entry_relative_path=entry_relative_path,
            included_files=included_files,
            can_install=self.source.install_available,
            install_disabled_reason=self.source.install_unavailable_reason,
        )

    async def install_item(
        self,
        item_id: str,
        *,
        workspace_path: Path,
        force: bool,
    ) -> str:
        slug = _validate_skill_slug(item_id)
        with tempfile.TemporaryDirectory(prefix="aiasys-skillhub-install-") as temp_dir:
            staging_root = Path(temp_dir) / "skills"
            staging_root.mkdir(parents=True, exist_ok=True)
            package_dir = await self._download_and_extract(slug, staging_root)
            _install_directory_to_store_and_workspace(
                skill_name=slug,
                source_dir=package_dir,
                workspace_path=workspace_path,
                force=force,
            )
        return slug


class SkillsMPExternalSkillAdapter(ExternalSkillMarketAdapter):
    """SkillsMP 外部 Skill 目录适配器。

    SkillsMP 只提供搜索 API，搜索结果里包含 GitHub tree URL。详情和安装通过
    GitHub URL 读取对应的 Skill 目录。
    """

    _SORT_MAP: dict[str, str] = {
        "recommended": "stars",
        "downloads": "stars",
        "stars": "stars",
        "recent": "recent",
    }
    _ITEM_CACHE_MAX_SIZE = 200

    def __init__(self) -> None:
        self.source = self._build_source()
        self._item_cache: OrderedDict[str, ExternalSkillMarketItem] = OrderedDict()

    def _build_source(self) -> ExternalSkillMarketSource:
        return ExternalSkillMarketSource(
            source_id="skillsmp",
            display_name="SkillsMP",
            description=(
                "通过 SkillsMP 搜索公开 GitHub 仓库中的 SKILL.md，"
                "安装时从 GitHub 拉取对应 Skill 目录。"
            ),
            supports_public_catalog=True,
            supports_workspace_install=True,
            install_available=True,
            install_unavailable_reason=None,
        )

    def _parse_sort(self, sort_by: str) -> str:
        return self._SORT_MAP.get(sort_by, self._SORT_MAP["recommended"])

    async def _fetch_api_page(
        self,
        *,
        page_number: int,
        page_size: int,
        sort_by: str,
        keyword: str,
        category: str | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "q": keyword,
            "page": page_number,
            "limit": page_size,
            "sortBy": self._parse_sort(sort_by),
        }
        if category:
            params["category"] = category

        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                response = await client.get(
                    _SKILLSMP_API_BASE,
                    params=params,
                    headers=_skillsmp_headers(),
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.warning("SkillsMP API 请求失败: %s -> %s", _SKILLSMP_API_BASE, status)
            raise ValueError(f"SkillsMP API 暂时不可访问: {status}") from exc
        except httpx.HTTPError as exc:
            logger.warning("SkillsMP API 请求失败: %s -> %s", _SKILLSMP_API_BASE, exc)
            raise ValueError("SkillsMP API 暂时不可访问") from exc

        payload = response.json()
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise ValueError("SkillsMP API 返回格式异常")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("SkillsMP API 缺少 data 字段")
        return data

    def _build_item(self, raw: dict[str, Any]) -> ExternalSkillMarketItem | None:
        github_url = _string_or_none(raw.get("githubUrl"))
        if not github_url:
            return None
        try:
            slug = _skillsmp_slug_from_github_url(github_url)
        except ValueError:
            return None

        item_id = github_url
        raw_id = _string_or_none(raw.get("id")) or slug
        skill_url = _string_or_none(raw.get("skillUrl")) or _SKILLSMP_PAGE_TEMPLATE.format(
            item_id=raw_id,
        )
        updated_at = _coerce_int(raw.get("updatedAt"))
        labels: dict[str, str] = {
            "skillsmp_id": raw_id,
            "github_url": github_url,
        }
        if updated_at is not None:
            labels["updated_at"] = str(updated_at)

        item = ExternalSkillMarketItem(
            source_id=self.source.source_id,
            item_id=item_id,
            slug=slug,
            display_name=_string_or_none(raw.get("name")) or slug,
            description=_string_or_none(raw.get("description")),
            summary=_string_or_none(raw.get("description")),
            version=None,
            homepage_url=skill_url,
            categories=[],
            labels=labels,
            owner_name=_string_or_none(raw.get("author")),
            source="github",
            icon_url=None,
            downloads=None,
            installs=None,
            stars=_coerce_int(raw.get("stars")),
            score=None,
            rank=None,
        )
        self._item_cache[item_id] = item
        if len(self._item_cache) > self._ITEM_CACHE_MAX_SIZE:
            self._item_cache.popitem(last=False)
        return item

    def _minimal_item_from_github_url(self, github_url: str) -> ExternalSkillMarketItem:
        owner, _repo, _ref, skill_path = _parse_github_tree_url(github_url)
        slug = _skillsmp_slug_from_github_url(github_url)
        display_name = Path(skill_path).name or slug
        return ExternalSkillMarketItem(
            source_id=self.source.source_id,
            item_id=github_url,
            slug=slug,
            display_name=display_name,
            homepage_url=github_url,
            categories=[],
            labels={"github_url": github_url},
            owner_name=owner,
            source="github",
        )

    async def list_items(
        self,
        *,
        search: str | None,
        category: str | None,
        sort_by: str,
        page_number: int,
        page_size: int,
    ) -> ExternalSkillMarketListResponse:
        safe_page_number = max(page_number, 1)
        safe_page_size = max(min(page_size, 50), 1)
        keyword = _string_or_none(search) or _SKILLSMP_DEFAULT_QUERY
        normalized_category = _string_or_none(category)

        try:
            data = await self._fetch_api_page(
                page_number=safe_page_number,
                page_size=safe_page_size,
                sort_by=sort_by,
                keyword=keyword,
                category=normalized_category,
            )
        except ValueError as exc:
            logger.warning("SkillsMP API 列表请求失败: %s", exc)
            return ExternalSkillMarketListResponse(
                source=self.source,
                items=[],
                available_categories=[],
                total_count=0,
                page_number=safe_page_number,
                page_size=safe_page_size,
            )

        raw_skills = data.get("skills")
        if not isinstance(raw_skills, list):
            raw_skills = []
        pagination = data.get("pagination")
        total = None
        if isinstance(pagination, dict):
            total = _coerce_int(pagination.get("total"))
        if total is None:
            total = len(raw_skills)

        items = [
            item
            for raw in raw_skills
            if isinstance(raw, dict)
            for item in [self._build_item(raw)]
            if item is not None
        ]

        return ExternalSkillMarketListResponse(
            source=self.source,
            items=items,
            available_categories=[normalized_category] if normalized_category else [],
            total_count=total,
            page_number=safe_page_number,
            page_size=safe_page_size,
        )

    async def _fetch_skill_markdown(self, github_url: str) -> tuple[str | None, str | None]:
        owner, repo, ref, skill_path = _parse_github_tree_url(github_url)
        encoded_ref = quote(ref, safe="")
        encoded_path = quote(skill_path.strip("/"), safe="/")
        candidates = [
            (
                "SKILL.md",
                f"https://raw.githubusercontent.com/{owner}/{repo}/{encoded_ref}/{encoded_path}/SKILL.md",
            ),
            (
                "skill.md",
                f"https://raw.githubusercontent.com/{owner}/{repo}/{encoded_ref}/{encoded_path}/skill.md",
            ),
        ]

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            for entry_name, raw_url in candidates:
                try:
                    response = await client.get(
                        raw_url,
                        headers=_external_http_headers(accept="text/plain"),
                    )
                except httpx.HTTPError:
                    continue
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                return _truncate_text(response.text), entry_name
        return None, None

    async def get_item_detail(self, item_id: str) -> ExternalSkillMarketDetailResponse:
        github_url = _string_or_none(item_id)
        if not github_url:
            raise ValueError("SkillsMP 条目缺少 GitHub URL")

        item = self._item_cache.get(github_url)
        if item is not None:
            self._item_cache.move_to_end(github_url)
        else:
            item = self._minimal_item_from_github_url(github_url)

        readme_excerpt, entry_relative_path = await self._fetch_skill_markdown(github_url)
        included_files = [entry_relative_path] if entry_relative_path else []
        labels = item.labels or {}
        github_url_from_labels = _string_or_none(labels.get("github_url"))
        if github_url_from_labels:
            included_files.append(github_url_from_labels)

        return ExternalSkillMarketDetailResponse(
            source=self.source,
            item=item,
            readme_excerpt=readme_excerpt,
            entry_relative_path=entry_relative_path,
            included_files=included_files,
            can_install=self.source.install_available,
            install_disabled_reason=self.source.install_unavailable_reason,
        )

    async def _download_github_skill_dir(self, github_url: str, target_dir: Path) -> Path:
        owner, repo, ref, skill_path = _parse_github_tree_url(github_url)
        encoded_ref = quote(ref, safe="/")
        archive_urls = [
            f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{encoded_ref}",
            f"https://codeload.github.com/{owner}/{repo}/zip/refs/tags/{encoded_ref}",
            f"https://codeload.github.com/{owner}/{repo}/zip/{encoded_ref}",
        ]

        zip_bytes: bytes | None = None
        async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
            for archive_url in archive_urls:
                try:
                    response = await client.get(
                        archive_url,
                        headers=_external_http_headers(accept="application/zip"),
                    )
                except httpx.HTTPError:
                    continue
                if response.status_code == 404:
                    continue
                try:
                    response.raise_for_status()
                except httpx.HTTPError:
                    continue
                zip_bytes = response.read()
                break

        if zip_bytes is None:
            raise ValueError("无法下载 SkillsMP 对应的 GitHub 仓库压缩包")

        package_dir = target_dir / "package"
        package_dir.mkdir(parents=True, exist_ok=True)
        wanted_path = PurePosixPath(skill_path.strip("/"))
        found = False

        try:
            with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
                for member in archive.infolist():
                    member_path = PurePosixPath(member.filename)
                    parts = member_path.parts
                    if len(parts) < 2:
                        continue
                    relative = PurePosixPath(*parts[1:])
                    try:
                        output_relative = relative.relative_to(wanted_path)
                    except ValueError:
                        continue
                    if not output_relative.parts:
                        continue
                    if any(part in {"", ".."} for part in output_relative.parts):
                        raise ValueError("GitHub 压缩包中包含非法路径")

                    found = True
                    target_path = package_dir.joinpath(*output_relative.parts)
                    if member.is_dir():
                        target_path.mkdir(parents=True, exist_ok=True)
                        continue
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as src, target_path.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
        except zipfile.BadZipFile as exc:
            raise ValueError(f"GitHub 压缩包损坏或格式错误: {exc}") from exc

        if not found:
            raise ValueError("GitHub 压缩包中未找到 SkillsMP 指向的 Skill 目录")
        if _find_entry_file(package_dir) is None:
            raise ValueError("SkillsMP 对应目录中未找到 SKILL.md")
        return package_dir

    async def install_item(
        self,
        item_id: str,
        *,
        workspace_path: Path,
        force: bool,
    ) -> str:
        github_url = _string_or_none(item_id)
        if not github_url:
            raise ValueError("SkillsMP 条目缺少 GitHub URL")
        slug = _skillsmp_slug_from_github_url(github_url)

        with tempfile.TemporaryDirectory(prefix="aiasys-skillsmp-install-") as temp_dir:
            package_dir = await self._download_github_skill_dir(github_url, Path(temp_dir))
            _install_directory_to_store_and_workspace(
                skill_name=slug,
                source_dir=package_dir,
                workspace_path=workspace_path,
                force=force,
            )
        return slug


class AIASysBuiltinSkillAdapter(ExternalSkillMarketAdapter):
    """AIASys 内置 Skill 适配器 — 从本地 skills/builtin/ 目录提供系统预装 Skill。"""

    def __init__(self) -> None:
        from app.skills.manager import SkillManager

        self._builtin_dir = SkillManager.SKILLS_BUILTIN_DIR
        self.source = self._build_source()

    def _build_source(self) -> ExternalSkillMarketSource:
        return ExternalSkillMarketSource(
            source_id="aiasys",
            display_name="AIASys",
            description=(
                "AIASys 系统内置 Skill 合集，包含 PDF 翻译、Canvas 编辑等开箱即用的能力。"
                "启用后复制到工作区 .aiasys/skills/ 目录。"
            ),
            supports_public_catalog=True,
            supports_workspace_install=True,
            install_available=True,
            install_unavailable_reason=None,
        )

    def refresh_source_state(self) -> None:
        self._builtin_dir.mkdir(parents=True, exist_ok=True)

    async def list_items(
        self,
        *,
        search: str | None,
        category: str | None,
        sort_by: str,
        page_number: int,
        page_size: int,
    ) -> ExternalSkillMarketListResponse:
        from app.skills.skill_discovery import _list_skill_packages

        self.refresh_source_state()
        packages = _list_skill_packages(self._builtin_dir, source="aiasys")

        items: list[ExternalSkillMarketItem] = []
        for pkg in packages:
            item = ExternalSkillMarketItem(
                source_id=self.source.source_id,
                item_id=pkg.name,
                slug=pkg.name,
                display_name=pkg.display_name,
                description=pkg.description,
                summary=pkg.description,
                version=None,
                homepage_url=None,
                categories=[],
                downloads=None,
                stars=None,
                score=None,
                rank=None,
            )
            items.append(item)

        search_tokens = _normalize_search_tokens(search)
        if search_tokens:
            items = [
                item
                for item in items
                if all(
                    token in f"{item.display_name} {item.slug} {item.description or ''}".lower()
                    for token in search_tokens
                )
            ]

        if category:
            items = [item for item in items if category in item.categories]

        total = len(items)
        safe_page = max(page_number, 1)
        safe_size = max(min(page_size, 60), 1)
        start = (safe_page - 1) * safe_size
        paged = items[start : start + safe_size]

        return ExternalSkillMarketListResponse(
            source=self.source,
            items=paged,
            available_categories=[],
            total_count=total,
            page_number=safe_page,
            page_size=safe_size,
        )

    async def get_item_detail(self, item_id: str) -> ExternalSkillMarketDetailResponse:
        from app.skills.skill_discovery import _is_safe_name, _parse_skill_info

        if not _is_safe_name(item_id):
            raise ValueError(f"无效的 Skill 名称: {item_id}")

        pkg_dir = self._builtin_dir / item_id
        if not pkg_dir.exists() or not pkg_dir.is_dir():
            raise ValueError(f"Skill 不存在: {item_id}")

        info = _parse_skill_info(pkg_dir, source="aiasys")
        if info is None:
            raise ValueError(f"Skill 缺少 SKILL.md: {item_id}")

        readme_excerpt: str | None = None
        try:
            content = info.entry_path.read_text(encoding="utf-8")
            readme_excerpt = _truncate_text(content, limit=1600)
        except Exception:
            pass

        included_files: list[str] = []
        try:
            for f in sorted(pkg_dir.rglob("*")):
                if f.is_file():
                    included_files.append(f.relative_to(pkg_dir).as_posix())
        except Exception:
            pass

        item = ExternalSkillMarketItem(
            source_id=self.source.source_id,
            item_id=info.name,
            slug=info.name,
            display_name=info.display_name,
            description=info.description,
            summary=info.description,
            version=None,
            homepage_url=None,
            categories=[],
        )

        return ExternalSkillMarketDetailResponse(
            source=self.source,
            item=item,
            readme_excerpt=readme_excerpt,
            entry_relative_path=info.entry_relative_path,
            included_files=included_files,
            can_install=True,
            install_disabled_reason=None,
        )

    async def install_item(
        self,
        item_id: str,
        *,
        workspace_path: Path,
        force: bool,
    ) -> str:
        from app.skills.manager import get_skill_manager
        from app.skills.skill_discovery import _is_safe_name

        if not _is_safe_name(item_id):
            raise ValueError(f"无效的 Skill 名称: {item_id}")

        pkg_dir = self._builtin_dir / item_id
        if not pkg_dir.exists() or not pkg_dir.is_dir():
            raise ValueError(f"Skill 不存在: {item_id}")

        manager = get_skill_manager()
        result = manager.enable_skill(item_id, workspace_path, force=force)
        if not result.success:
            raise ValueError(result.message)
        return item_id


class ExternalSkillMarketService:
    """外部 Skill 市场聚合服务。"""

    def __init__(self) -> None:
        aiasys_adapter = AIASysBuiltinSkillAdapter()
        skillhub_adapter = SkillHubExternalSkillAdapter()
        skillsmp_adapter = SkillsMPExternalSkillAdapter()
        self._adapters: dict[str, ExternalSkillMarketAdapter] = {
            aiasys_adapter.source.source_id: aiasys_adapter,
            skillhub_adapter.source.source_id: skillhub_adapter,
            skillsmp_adapter.source.source_id: skillsmp_adapter,
        }

    def list_sources(self) -> list[ExternalSkillMarketSource]:
        sources: list[ExternalSkillMarketSource] = []
        for adapter in self._adapters.values():
            adapter.refresh_source_state()
            sources.append(adapter.source)
        return sources

    def get_adapter(self, source_id: str) -> ExternalSkillMarketAdapter:
        adapter = self._adapters.get(source_id)
        if adapter is None:
            raise ValueError(f"不支持的外部 Skill 市场源: {source_id}")
        return adapter

    async def list_items(
        self,
        source_id: str,
        *,
        search: str | None,
        category: str | None,
        sort_by: str,
        page_number: int,
        page_size: int,
    ) -> ExternalSkillMarketListResponse:
        adapter = self.get_adapter(source_id)
        return await adapter.list_items(
            search=search,
            category=category,
            sort_by=sort_by,
            page_number=page_number,
            page_size=page_size,
        )

    async def get_item_detail(
        self,
        source_id: str,
        *,
        item_id: str,
    ) -> ExternalSkillMarketDetailResponse:
        adapter = self.get_adapter(source_id)
        return await adapter.get_item_detail(item_id=item_id)

    async def install_item(
        self,
        source_id: str,
        *,
        item_id: str,
        workspace_path: Path,
        force: bool,
    ) -> str:
        adapter = self.get_adapter(source_id)
        return await adapter.install_item(
            item_id=item_id,
            workspace_path=workspace_path,
            force=force,
        )


_external_skill_market_service: ExternalSkillMarketService | None = None


def get_external_skill_market_service() -> ExternalSkillMarketService:
    global _external_skill_market_service
    if _external_skill_market_service is None:
        _external_skill_market_service = ExternalSkillMarketService()
    return _external_skill_market_service

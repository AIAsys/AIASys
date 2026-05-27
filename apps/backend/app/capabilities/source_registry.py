"""能力源仓库注册表。

扫描 builtin/ 和 store/ 目录，发现所有可用的能力源。
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

from app.capabilities.models import CapabilityKind, CapabilityManifest

logger = logging.getLogger(__name__)

# 能力源根目录
_BUILTIN_SOURCES_DIR = Path(__file__).parent.parent.parent / "capability_sources" / "builtin"
_STORE_SOURCES_DIR = Path(__file__).parent.parent.parent / "capability_sources" / "store"

# skill 类型直接从 skills/ 目录扫描（消除与 capability_sources/ 的双轨）
_SKILL_BUILTIN_DIR = Path(__file__).parent.parent.parent / "skills" / "builtin"
_SKILL_STORE_DIR = Path(__file__).parent.parent.parent / "skills" / "store"

_KIND_SUBDIRS: dict[CapabilityKind, str] = {
    CapabilityKind.SKILL_PACK: "skill",
    CapabilityKind.MCP_SERVER: "mcp",
    CapabilityKind.SUBAGENT: "subagent",
}


class CapabilitySourceRegistry:
    """扫描并缓存能力源仓库中的 manifest。"""

    def __init__(self) -> None:
        self._cache: dict[str, CapabilityManifest] = {}

    # ---- 扫描 ----

    def scan_all(self) -> list[CapabilityManifest]:
        """扫描所有源目录，返回可用能力列表。"""
        results: list[CapabilityManifest] = []
        for source in ("builtin", "store"):
            results.extend(self._scan_source(source))
        return results

    def _scan_source(self, source: str) -> list[CapabilityManifest]:
        results: list[CapabilityManifest] = []
        for kind, subdir_name in _KIND_SUBDIRS.items():
            if kind == CapabilityKind.SKILL_PACK:
                # skill 类型从 skills/ 目录扫描，消除双轨
                base_dir = _SKILL_BUILTIN_DIR if source == "builtin" else _SKILL_STORE_DIR
            else:
                base_dir = (
                    _BUILTIN_SOURCES_DIR if source == "builtin" else _STORE_SOURCES_DIR
                ) / subdir_name
            if not base_dir.exists():
                continue
            try:
                for entry in base_dir.iterdir():
                    if not entry.is_dir() or entry.name.startswith("."):
                        continue
                    manifest = self._read_manifest(entry, kind, source)
                    if manifest is not None:
                        results.append(manifest)
            except PermissionError:
                logger.warning("无权限扫描能力目录: %s", base_dir)
        return results

    def _read_manifest(
        self,
        cap_dir: Path,
        kind: CapabilityKind,
        source: str,
    ) -> CapabilityManifest | None:
        if kind == CapabilityKind.SKILL_PACK:
            return self._read_skill_manifest(cap_dir, source)

        manifest_path = cap_dir / "manifest.toml"
        if not manifest_path.exists():
            return None
        try:
            raw: dict[str, Any] = tomllib.loads(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.warning("manifest 读取失败 %s: %s", manifest_path, exc)
            return None

        cap_id = str(raw.get("capability_id", cap_dir.name)).strip()
        if not cap_id:
            return None

        return CapabilityManifest(
            capability_id=cap_id,
            kind=kind,
            display_name=str(raw.get("display_name", cap_id)).strip(),
            description=str(raw.get("description", "")).strip(),
            version=str(raw.get("version", "1.0.0")).strip(),
            author=str(raw.get("author", "")).strip(),
            dependencies=[
                str(d).strip() for d in (raw.get("dependencies") or []) if str(d).strip()
            ],
            config_schema=raw.get("config_schema") or {},
            tool_names=[str(t).strip() for t in (raw.get("tools") or []) if str(t).strip()],
            min_platform_version=str(raw.get("min_platform_version", "0.1.0")).strip(),
            source_dir=str(cap_dir),
        )

    def _read_skill_manifest(
        self,
        cap_dir: Path,
        source: str,
    ) -> CapabilityManifest | None:
        """从 SKILL.md 的 TOML front matter 解析 skill manifest。"""
        skill_md = cap_dir / "SKILL.md"
        if not skill_md.exists():
            return None
        try:
            text = skill_md.read_text(encoding="utf-8")
            if not text.startswith("+++"):
                return None
            end = text.find("+++", 3)
            if end == -1:
                return None
            front_matter = tomllib.loads(text[3:end].strip()) or {}
        except Exception as exc:
            logger.warning("SKILL.md front matter 解析失败 %s: %s", skill_md, exc)
            return None

        cap_id = cap_dir.name
        display_name = str(front_matter.get("name", cap_id)).strip()
        description = str(front_matter.get("description", "")).strip()

        return CapabilityManifest(
            capability_id=cap_id,
            kind=CapabilityKind.SKILL_PACK,
            display_name=display_name or cap_id,
            description=description,
            version="1.0.0",
            author="",
            dependencies=[],
            config_schema={},
            tool_names=[],
            min_platform_version="0.1.0",
            source_dir=str(cap_dir),
        )

    # ---- 查询 ----

    def get_manifest(self, cap_id: str) -> CapabilityManifest | None:
        """按 ID 获取能力 manifest（store 优先于 builtin，允许 store 覆盖同名 builtin）。"""
        # store 优先（允许覆盖 builtin）
        manifest = self._find_in_source(cap_id, "store")
        if manifest is None:
            manifest = self._find_in_source(cap_id, "builtin")

        if manifest is not None:
            self._cache[cap_id] = manifest
        return manifest

    def _find_in_source(self, cap_id: str, source: str) -> CapabilityManifest | None:
        base_dir = _BUILTIN_SOURCES_DIR if source == "builtin" else _STORE_SOURCES_DIR
        for kind, subdir_name in _KIND_SUBDIRS.items():
            cap_dir = base_dir / subdir_name / cap_id
            if cap_dir.exists() and cap_dir.is_dir():
                manifest = self._read_manifest(cap_dir, kind, source)
                if manifest is not None:
                    return manifest
        return None

    def _infer_source(self, source_dir: Path) -> str:
        """从目录路径推断能力来源（builtin 或 store）。"""
        try:
            source_dir.resolve().relative_to(_BUILTIN_SOURCES_DIR.resolve())
            return "builtin"
        except ValueError:
            return "store"

    def clear_cache(self) -> None:
        self._cache.clear()

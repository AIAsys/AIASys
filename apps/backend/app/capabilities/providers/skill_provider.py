"""Skill 类型能力 Provider。

安装/卸载动作：目录复制到/删除工作区 .aiasys/skills/。
"""

from __future__ import annotations

import json
import logging
import shutil
import tomllib
from pathlib import Path
from typing import Any

from app.capabilities.models import (
    CapabilityKind,
    CapabilityManifest,
    CapabilityStatus,
    HealthStatus,
    InstallResult,
)
from app.capabilities.providers.base import CapabilityProvider, CapabilityProviderContext
from app.skills import get_skill_manager
from app.skills.models import SkillMetaInfo
from app.skills.skill_fingerprint import META_FILE_NAME, compute_directory_fingerprint

logger = logging.getLogger(__name__)


class SkillProvider(CapabilityProvider):
    """Skill 能力 Provider。

    install    = 从能力源目录 copytree 到 .aiasys/skills/{cap_id}/
    uninstall  = 委托 SkillManager.disable_skill
    activate   = 标记声明为 enabled（目录已存在即可）
    deactivate = 仅标记声明为 disabled，保留安装目录（软关闭）
    verify     = 检查 SKILL.md 和入口文件是否存在
    """

    def resolve_manifest(self, source_dir: Path) -> CapabilityManifest | None:
        manifest_path = source_dir / "manifest.toml"
        if not manifest_path.exists():
            return None
        try:
            raw: dict[str, Any] = tomllib.loads(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.warning("Skill manifest 解析失败 %s: %s", manifest_path, exc)
            return None

        cap_id = str(raw.get("capability_id", source_dir.name)).strip()
        if not cap_id:
            return None

        return CapabilityManifest(
            capability_id=cap_id,
            kind=CapabilityKind.SKILL_PACK,
            display_name=str(raw.get("display_name", cap_id)).strip(),
            description=str(raw.get("description", "")).strip(),
            version=str(raw.get("version", "1.0.0")).strip(),
            author=str(raw.get("author", "")).strip(),
            dependencies=[
                str(d).strip() for d in (raw.get("dependencies") or []) if str(d).strip()
            ],
            config_schema=raw.get("config_schema") or {},
            min_platform_version=str(raw.get("min_platform_version", "0.1.0")).strip(),
            source_dir=str(source_dir),
        )

    def install(
        self,
        cap_id: str,
        workspace_path: Path,
        source_dir: Path,
        config: dict[str, Any] | None = None,
        context: CapabilityProviderContext | None = None,
    ) -> InstallResult:
        if not get_skill_manager()._is_safe_name(cap_id):
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message="非法 skill 名称",
            )

        if not source_dir.exists() or not source_dir.is_dir():
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"Skill 源目录不存在: {source_dir}",
            )

        dest = workspace_path / ".aiasys" / "skills" / cap_id
        if dest.exists():
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"工作区中已启用 Skill '{cap_id}'",
            )

        tmp_path = dest.parent / (dest.name + ".new")
        if tmp_path.exists():
            shutil.rmtree(tmp_path, ignore_errors=True)

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_dir.resolve(), tmp_path)
            if config:
                self._write_skill_config(cap_id, tmp_path, config)
            else:
                self._init_config_from_example(tmp_path)
        except Exception as exc:
            if tmp_path.exists():
                shutil.rmtree(tmp_path, ignore_errors=True)
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"复制失败: {exc}",
            )

        # 原子替换
        if dest.is_symlink():
            dest.unlink()
        elif dest.is_dir():
            shutil.rmtree(dest)
        elif dest.exists():
            dest.unlink()
        tmp_path.rename(dest)

        # 写入 skill meta
        self._write_skill_meta(cap_id, dest, source_dir.resolve())

        return InstallResult(
            success=True,
            capability_id=cap_id,
            message=f"Skill '{cap_id}' 已启用",
        )

    def uninstall(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> InstallResult:
        result = get_skill_manager().disable_skill(cap_id, workspace_path)
        if not result.success:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=result.message,
            )

        return InstallResult(
            success=True,
            capability_id=cap_id,
            message=result.message,
        )

    def activate(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> InstallResult:
        """激活 skill：保留安装目录，仅将声明标记为 enabled。"""
        dest = workspace_path / ".aiasys" / "skills" / cap_id
        if dest.exists():
            return InstallResult(
                success=True,
                capability_id=cap_id,
                message=f"Skill '{cap_id}' 已激活",
            )
        return InstallResult(
            success=False,
            capability_id=cap_id,
            message=f"Skill '{cap_id}' 未安装，无法激活",
        )

    def deactivate(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> InstallResult:
        """禁用 skill：保留安装目录，仅将声明标记为 disabled。

        注意：这里只做软关闭，不调用 SkillManager.disable_skill 删除目录。
        真正的卸载由 CapabilityManager.uninstall 负责。
        """
        dest = workspace_path / ".aiasys" / "skills" / cap_id
        if dest.exists():
            return InstallResult(
                success=True,
                capability_id=cap_id,
                message=f"Skill '{cap_id}' 已禁用",
            )
        return InstallResult(
            success=False,
            capability_id=cap_id,
            message=f"Skill '{cap_id}' 未安装，无法禁用",
        )

    def verify(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> HealthStatus:
        dest = workspace_path / ".aiasys" / "skills" / cap_id
        if not dest.exists():
            return HealthStatus(
                status=CapabilityStatus.AVAILABLE,
                healthcheck=None,
                detail="未安装",
            )

        # 检查 SKILL.md
        skill_md = dest / "SKILL.md"
        if not skill_md.exists():
            return HealthStatus(
                status=CapabilityStatus.ERROR,
                healthcheck=None,
                detail="缺少 SKILL.md",
            )

        # 检查入口文件（SKILL.md 中声明的 entry）
        entry = self._read_entry_from_skill_md(skill_md)
        if entry:
            entry_path = dest / entry
            if not entry_path.exists():
                return HealthStatus(
                    status=CapabilityStatus.ERROR,
                    healthcheck=None,
                    detail=f"入口文件不存在: {entry}",
                )

        return HealthStatus(
            status=CapabilityStatus.ACTIVE,
            healthcheck=None,
            detail="正常",
        )

    def is_installed(
        self, cap_id: str, workspace_path: Path, context: CapabilityProviderContext | None = None
    ) -> bool:
        return (workspace_path / ".aiasys" / "skills" / cap_id).exists()

    # ---- 内部方法 ----

    def _write_skill_config(self, cap_id: str, skill_dir: Path, config: dict[str, Any]) -> None:
        config_path = skill_dir / "config.json"
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                json.dumps(config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Skill 配置写入失败 %s: %s", cap_id, exc)

    def _init_config_from_example(self, skill_dir: Path) -> None:
        json_example = skill_dir / "config.example.json"
        json_config = skill_dir / "config.json"
        if json_example.exists() and not json_config.exists():
            shutil.copy(json_example, json_config)
            return

        toml_example = skill_dir / "config.example.toml"
        toml_config = skill_dir / "config.toml"
        if toml_example.exists() and not toml_config.exists():
            shutil.copy(toml_example, toml_config)
            return

        yaml_example = skill_dir / "config.example.yaml"
        yaml_config = skill_dir / "config.yaml"
        if yaml_example.exists() and not yaml_config.exists():
            shutil.copy(yaml_example, yaml_config)

    def _write_skill_meta(
        self,
        cap_id: str,
        dest_path: Path,
        source_dir: Path,
    ) -> None:
        """在工作区副本目录下写入 .aiasys-skill-meta.json。"""
        from datetime import datetime, timezone

        # 从路径推断 source_type
        source_str = str(source_dir)
        if "/builtin/" in source_str or "\\builtin\\" in source_str:
            source_type = "builtin"
        elif "/store/" in source_str or "\\store\\" in source_str:
            source_type = "store"
        else:
            source_type = "external"

        # 从 manifest.toml 读取 version
        version = None
        manifest_path = source_dir / "manifest.toml"
        if manifest_path.exists():
            try:
                raw: dict[str, Any] = tomllib.loads(manifest_path.read_text(encoding="utf-8")) or {}
                version = str(raw.get("version", "")).strip() or None
            except Exception:
                pass

        fingerprint = compute_directory_fingerprint(source_dir)
        meta = SkillMetaInfo(
            name=cap_id,
            source_type=source_type,
            source_name=cap_id,
            source_fingerprint=fingerprint,
            installed_at=datetime.now(timezone.utc).isoformat(),
            version=version,
        )
        meta_path = dest_path / META_FILE_NAME
        meta_path.write_text(
            json.dumps(meta.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _read_entry_from_skill_md(self, skill_md: Path) -> str:
        """从 SKILL.md 中读取 entry 字段。"""
        try:
            import re

            text = skill_md.read_text(encoding="utf-8")
            match = re.search(r"^entry:\s*(.+)$", text, re.MULTILINE)
            if match:
                return match.group(1).strip()
        except Exception:
            pass
        return ""

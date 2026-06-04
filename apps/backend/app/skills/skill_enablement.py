"""Skill 启用/禁用 mixin — enable_skill / disable_skill / detach_skill。"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .models import SkillMetaInfo, SkillOperationResult
from .skill_fingerprint import META_FILE_NAME, compute_directory_fingerprint


class SkillEnablementMixin:
    """提供工作区 skill 启用、禁用、detach 能力。

    依赖 base class 提供的：
    - SKILLS_STORE_DIR
    - VERSIONS_DIR_NAME
    - CONFIG_EXAMPLE_NAME
    - WORKSPACE_SKILLS_DIR_NAME (used indirectly via get_workspace_skills_dir)
    - get_workspace_skills_dir()
    - get_workspace_skill_config_dir()
    - get_workspace_skill_config_path()
    - _is_safe_name()  (staticmethod, from skill_discovery)
    """

    # ---- 配置初始化 ----

    def _init_config_from_example(
        self,
        skill_name: str,
        workspace_path: Path,
        store_skill_dir: Path,
    ) -> None:
        config_path = self.get_workspace_skill_config_path(workspace_path, skill_name)
        if config_path.exists():
            return
        example = store_skill_dir / self.CONFIG_EXAMPLE_NAME
        if example.exists():
            config_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(example, config_path)

    def _cleanup_workspace_skill_config(
        self,
        skill_name: str,
        workspace_path: Path,
    ) -> None:
        config_path = self.get_workspace_skill_config_path(workspace_path, skill_name)
        if config_path.exists():
            config_path.unlink()

    # ---- 启用 / 禁用 ----

    def _resolve_store_skill_dir(self, skill_name: str) -> Path | None:
        """按优先级查找 skill 的源仓库目录：store > builtin。"""
        store_dir = self.SKILLS_STORE_DIR / skill_name
        if store_dir.exists():
            return store_dir
        builtin_dir = getattr(self, "SKILLS_BUILTIN_DIR", None)
        if builtin_dir is not None:
            builtin = builtin_dir / skill_name
            if builtin.exists():
                return builtin
        return None

    def _resolve_store_skill_dir_with_source(self, skill_name: str) -> tuple[Path | None, str]:
        """按优先级查找 skill 的源仓库目录，同时返回来源类型。

        返回: (源目录路径, source_type: "store" | "builtin" | "")
        """
        store_dir = self.SKILLS_STORE_DIR / skill_name
        if store_dir.exists():
            return store_dir, "store"
        builtin_dir = getattr(self, "SKILLS_BUILTIN_DIR", None)
        if builtin_dir is not None:
            builtin = builtin_dir / skill_name
            if builtin.exists():
                return builtin, "builtin"
        return None, ""

    def _write_skill_meta(
        self,
        skill_name: str,
        dest_path: Path,
        source_type: str,
        source_dir: Path,
        version: str | None = None,
    ) -> None:
        """在工作区副本目录下写入 .aiasys-skill-meta.json。"""
        fingerprint = compute_directory_fingerprint(source_dir)
        meta = SkillMetaInfo(
            name=skill_name,
            source_type=source_type,
            source_name=skill_name,
            source_fingerprint=fingerprint,
            installed_at=datetime.now(timezone.utc).isoformat(),
            version=version,
        )
        meta_path = dest_path / META_FILE_NAME
        meta_path.write_text(
            json.dumps(meta.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _remove_skill_meta(self, dest_path: Path) -> None:
        """删除工作区副本目录下的 .aiasys-skill-meta.json（如有）。"""
        meta_path = dest_path / META_FILE_NAME
        if meta_path.exists():
            meta_path.unlink()

    def enable_skill(
        self,
        skill_name: str,
        workspace_path: Path,
        *,
        version: str | None = None,
        force: bool = False,
    ) -> SkillOperationResult:
        """在工作区启用 skill：从源仓库复制到工作区。"""
        if not self._is_safe_name(skill_name):
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message="非法 skill 名称",
            )

        store_skill_dir, source_type = self._resolve_store_skill_dir_with_source(skill_name)
        if store_skill_dir is None:
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"Skill 仓库中不存在 Skill '{skill_name}'",
            )

        if version:
            target_dir = store_skill_dir / self.VERSIONS_DIR_NAME / version
            if not target_dir.exists():
                return SkillOperationResult(
                    success=False,
                    skill_name=skill_name,
                    message=f"版本 '{version}' 不存在",
                )
        else:
            target_dir = store_skill_dir

        ws_skills_dir = self.get_workspace_skills_dir(workspace_path)
        ws_skills_dir.mkdir(parents=True, exist_ok=True)
        dest_path = ws_skills_dir / skill_name

        if dest_path.exists():
            if not force:
                return SkillOperationResult(
                    success=False,
                    skill_name=skill_name,
                    message=f"工作区中已启用 Skill '{skill_name}'",
                )

        tmp_path = dest_path.parent / (dest_path.name + ".new")
        if tmp_path.exists():
            shutil.rmtree(tmp_path)

        try:
            shutil.copytree(target_dir.resolve(), tmp_path)
        except Exception as exc:
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"复制失败: {exc}",
            )

        # 原子替换：删除旧目录后重命名临时目录
        if dest_path.is_symlink():
            dest_path.unlink()
        elif dest_path.is_dir():
            shutil.rmtree(dest_path)
        elif dest_path.exists():
            dest_path.unlink()
        tmp_path.rename(dest_path)

        self._write_skill_meta(
            skill_name, dest_path, source_type, target_dir.resolve(), version=version
        )
        self._init_config_from_example(skill_name, workspace_path, store_skill_dir)

        return SkillOperationResult(
            success=True,
            skill_name=skill_name,
            package_path=dest_path,
            message=f"Skill '{skill_name}' 已启用" + (f" (版本: {version})" if version else ""),
        )

    def disable_skill(self, skill_name: str, workspace_path: Path) -> SkillOperationResult:
        """在工作区禁用 skill（删除目录）。"""
        if not self._is_safe_name(skill_name):
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message="非法 skill 名称",
            )

        link_path = self.get_workspace_skills_dir(workspace_path) / skill_name
        if not link_path.exists():
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"工作区中未启用 Skill '{skill_name}'",
            )

        try:
            if link_path.is_symlink():
                link_path.unlink()
            elif link_path.is_dir():
                shutil.rmtree(link_path)
            else:
                link_path.unlink()
        except Exception as exc:
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"禁用失败: {exc}",
            )

        self._cleanup_workspace_skill_config(skill_name, workspace_path)

        return SkillOperationResult(
            success=True,
            skill_name=skill_name,
            message=f"Skill '{skill_name}' 已禁用",
        )

    def enable_skill_global(
        self,
        skill_name: str,
        global_workspace_path: Path,
        *,
        version: str | None = None,
        force: bool = False,
    ) -> SkillOperationResult:
        """启用到我的默认：从源仓库复制到用户默认工作区。"""
        if not self._is_safe_name(skill_name):
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message="非法 skill 名称",
            )

        store_skill_dir, source_type = self._resolve_store_skill_dir_with_source(skill_name)
        if store_skill_dir is None:
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"Skill 仓库中不存在 Skill '{skill_name}'",
            )

        if version:
            target_dir = store_skill_dir / self.VERSIONS_DIR_NAME / version
            if not target_dir.exists():
                return SkillOperationResult(
                    success=False,
                    skill_name=skill_name,
                    message=f"版本 '{version}' 不存在",
                )
        else:
            target_dir = store_skill_dir

        ws_skills_dir = self.get_workspace_skills_dir(global_workspace_path)
        ws_skills_dir.mkdir(parents=True, exist_ok=True)
        dest_path = ws_skills_dir / skill_name

        if dest_path.exists():
            if not force:
                return SkillOperationResult(
                    success=False,
                    skill_name=skill_name,
                    message=f"我的默认中已启用 Skill '{skill_name}'",
                )

        tmp_path = dest_path.parent / (dest_path.name + ".new")
        if tmp_path.exists():
            shutil.rmtree(tmp_path)

        try:
            shutil.copytree(target_dir.resolve(), tmp_path)
        except Exception as exc:
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"复制失败: {exc}",
            )

        # 原子替换：删除旧目录后重命名临时目录
        if dest_path.is_symlink():
            dest_path.unlink()
        elif dest_path.is_dir():
            shutil.rmtree(dest_path)
        elif dest_path.exists():
            dest_path.unlink()
        tmp_path.rename(dest_path)

        self._write_skill_meta(
            skill_name, dest_path, source_type, target_dir.resolve(), version=version
        )
        self._init_config_from_example(skill_name, global_workspace_path, store_skill_dir)

        return SkillOperationResult(
            success=True,
            skill_name=skill_name,
            package_path=dest_path,
            message=f"Skill '{skill_name}' 已启用到我的默认"
            + (f" (版本: {version})" if version else ""),
        )

    def disable_skill_global(
        self, skill_name: str, global_workspace_path: Path
    ) -> SkillOperationResult:
        """从我的默认禁用 skill。"""
        if not self._is_safe_name(skill_name):
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message="非法 skill 名称",
            )

        link_path = self.get_workspace_skills_dir(global_workspace_path) / skill_name
        if not link_path.exists():
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"我的默认中未启用 Skill '{skill_name}'",
            )

        try:
            if link_path.is_symlink():
                link_path.unlink()
            elif link_path.is_dir():
                shutil.rmtree(link_path)
            else:
                link_path.unlink()
        except Exception as exc:
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"禁用失败: {exc}",
            )

        self._cleanup_workspace_skill_config(skill_name, global_workspace_path)

        return SkillOperationResult(
            success=True,
            skill_name=skill_name,
            message=f"Skill '{skill_name}' 已从我的默认禁用",
        )

    def detach_skill(self, skill_name: str, workspace_path: Path) -> SkillOperationResult:
        """从 Skill 仓库重新复制代码到工作区，覆盖本地修改。"""
        if not self._is_safe_name(skill_name):
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message="非法 skill 名称",
            )

        store_skill_dir = self._resolve_store_skill_dir(skill_name)
        if store_skill_dir is None:
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"Skill 仓库中不存在 Skill '{skill_name}'",
            )

        dest_path = self.get_workspace_skills_dir(workspace_path) / skill_name
        if not dest_path.exists():
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"工作区中未启用 Skill '{skill_name}'",
            )

        tmp_path = dest_path.parent / (dest_path.name + ".new")
        if tmp_path.exists():
            shutil.rmtree(tmp_path)

        try:
            shutil.copytree(store_skill_dir.resolve(), tmp_path)
        except Exception as exc:
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"重新复制失败: {exc}",
            )

        if dest_path.is_symlink():
            dest_path.unlink()
        elif dest_path.is_dir():
            shutil.rmtree(dest_path)
        elif dest_path.exists():
            dest_path.unlink()
        tmp_path.rename(dest_path)

        store_skill_dir, source_type = self._resolve_store_skill_dir_with_source(skill_name)
        if store_skill_dir is not None and source_type:
            self._write_skill_meta(skill_name, dest_path, source_type, store_skill_dir.resolve())

        return SkillOperationResult(
            success=True,
            skill_name=skill_name,
            package_path=dest_path,
            message=f"Skill '{skill_name}' 已从 Skill 仓库重新复制到工作区",
        )

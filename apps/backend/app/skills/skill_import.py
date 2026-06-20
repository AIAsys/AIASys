"""Skill 导入 mixin — import_skill_archive / install_skill_directory。"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from app.utils.path_utils import as_system_path

from .models import SkillOperationResult


class SkillImportMixin:
    """提供 zip 导入和目录安装能力。

    依赖 base class 提供的：
    - SKILLS_STORE_DIR
    - _ensure_store_dir()
    - _sanitize_package_name()  (staticmethod, from skill_discovery)
    - _safe_extract_zip()        (staticmethod)
    - _find_entry_file()         (staticmethod)
    - _select_import_root()      (staticmethod)
    """

    def import_skill_archive(
        self,
        *,
        workspace_path: Path | None = None,
        filename: str,
        content: bytes,
        force: bool = False,
    ) -> SkillOperationResult:
        """导入 zip 到全局仓库。"""
        if not filename.lower().endswith(".zip"):
            return SkillOperationResult(
                success=False,
                skill_name=Path(filename).stem or "skill",
                message="当前仅支持导入 zip 格式的 Skill 包",
            )

        skill_name = self._sanitize_package_name(Path(filename).stem or "skill")
        self._ensure_store_dir()
        target_dir = self.SKILLS_STORE_DIR / skill_name

        with tempfile.TemporaryDirectory(prefix="aiasys-skill-import-") as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            archive_path = temp_dir / "skill.zip"
            archive_path.write_bytes(content)

            try:
                with zipfile.ZipFile(archive_path) as archive:
                    self._safe_extract_zip(archive, temp_dir / "extracted")
            except zipfile.BadZipFile:
                return SkillOperationResult(
                    success=False,
                    skill_name=skill_name,
                    message="Skill 压缩包格式无效",
                )

            extracted_root = temp_dir / "extracted"
            package_dir = self._select_import_root(extracted_root)
            entry_path = self._find_entry_file(package_dir)
            if entry_path is None:
                return SkillOperationResult(
                    success=False,
                    skill_name=skill_name,
                    message="导入失败：压缩包中未找到可识别的 SKILL.md 入口文件",
                )

            return self._copy_package_dir(
                skill_name=skill_name,
                source_dir=package_dir,
                target_dir=target_dir,
                force=force,
            )

    def install_skill_directory(
        self,
        *,
        skill_name: str,
        source_dir: Path,
        workspace_path: Path,
        force: bool = False,
    ) -> SkillOperationResult:
        """将本地目录安装到全局仓库。"""
        entry = self._find_entry_file(source_dir)
        if not source_dir.exists() or entry is None:
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"导入失败：目录 '{skill_name}' 中未找到可识别的 SKILL.md 入口文件",
            )

        self._ensure_store_dir()
        target_dir = self.SKILLS_STORE_DIR / skill_name
        return self._copy_package_dir(
            skill_name=skill_name,
            source_dir=source_dir,
            target_dir=target_dir,
            force=force,
        )

    def _copy_package_dir(
        self,
        *,
        skill_name: str,
        source_dir: Path,
        target_dir: Path,
        force: bool,
    ) -> SkillOperationResult:
        if target_dir.exists():
            if not force:
                return SkillOperationResult(
                    success=False,
                    skill_name=skill_name,
                    package_path=target_dir,
                    message=f"全局仓库中已存在同名 Skill '{skill_name}'",
                )
            shutil.rmtree(as_system_path(str(target_dir)))

        target_dir.parent.mkdir(parents=True, exist_ok=True)

        tmp_dir = target_dir.with_suffix(".new")
        if tmp_dir.exists():
            shutil.rmtree(as_system_path(str(tmp_dir)))

        try:
            shutil.copytree(as_system_path(str(source_dir)), as_system_path(str(tmp_dir)))
        except Exception as exc:
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"导入失败: {exc}",
            )

        if target_dir.exists():
            shutil.rmtree(as_system_path(str(target_dir)))
        tmp_dir.rename(target_dir)

        return SkillOperationResult(
            success=True,
            skill_name=skill_name,
            package_path=target_dir,
            message=f"Skill '{skill_name}' 已导入到全局仓库",
        )

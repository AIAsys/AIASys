"""
Skill 管理器（全局存储 + 工作区复制启用模型）

设计口径：
- 全局 Skill 仓库：`apps/backend/skills/builtin/`（系统预装）+ `apps/backend/skills/store/`（用户导入）
- 工作区启用：`workspaces/{user_id}/{workspace_id}/.aiasys/skills/{name}` — 从全局仓库复制
- Skill 配置：`workspaces/{user_id}/{workspace_id}/.aiasys/skills/{name}/config.json`
- 版本管理：目录式 `skills/store/{skill}/.versions/{ver}/`（store 目录）
- Session 加载：扫描工作区 skills 目录 → 提取 name+description（渐进式披露）
- `.agents/skills/` 是 AIASys 开发协作 skill 仓库，不参与用户运行时
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from .models import SkillInfo, SkillMetaInfo, SkillOperationResult

logger = logging.getLogger(__name__)
from .skill_discovery import (
    ENTRY_FILE_NAME,
    VERSIONS_DIR_NAME,
    _find_entry_file,
    _is_safe_name,
    _list_skill_packages,
    _parse_skill_info,
    _safe_extract_zip,
    _sanitize_package_name,
    _select_import_root,
    get_skill_file_content,
    get_skill_versions,
    get_workspace_skill_entry_content,
    list_all_skills,
    list_store_skills,
    list_workspace_skills,
)
from .skill_enablement import SkillEnablementMixin
from .skill_fingerprint import META_FILE_NAME, compute_directory_fingerprint
from .skill_import import SkillImportMixin


class SkillManager(SkillEnablementMixin, SkillImportMixin):
    """Skill 包发现、导入与启用管理。

    架构：
    - 全局仓库 `skills/builtin/`（系统预装）+ `skills/store/`（用户导入）
    - 工作区启用 = 复制：`workspaces/{ws}/.aiasys/skills/{name}` 从 `skills/store/{name}` 复制
    - 版本管理 = 目录式：`skills/store/{skill}/.versions/{ver}/`

    SkillEnablementMixin — enable_skill / disable_skill / detach_skill
    SkillImportMixin      — import_skill_archive / install_skill_directory
    """

    BACKEND_ROOT = Path(__file__).resolve().parents[2]
    SKILLS_BUILTIN_DIR = BACKEND_ROOT / "skills" / "builtin"
    SKILLS_STORE_DIR = BACKEND_ROOT / "skills" / "store"
    WORKSPACE_SKILLS_DIR_NAME = ".aiasys/skills"
    CONFIG_EXAMPLE_NAME = "config.example.json"
    CONFIG_NAME = "config.json"

    # ---- 目录工具 ----

    def _ensure_store_dir(self) -> None:
        self.SKILLS_STORE_DIR.mkdir(parents=True, exist_ok=True)

    def get_workspace_skills_dir(self, workspace_path: Path) -> Path:
        return workspace_path / self.WORKSPACE_SKILLS_DIR_NAME

    def get_workspace_skill_config_dir(self, workspace_path: Path, skill_name: str) -> Path:
        return self.get_workspace_skills_dir(workspace_path) / skill_name

    def get_workspace_skill_config_path(self, workspace_path: Path, skill_name: str) -> Path:
        return self.get_workspace_skill_config_dir(workspace_path, skill_name) / self.CONFIG_NAME

    # ---- 全局仓库 ----

    def list_store_skills(self) -> list[SkillInfo]:
        return list_store_skills(self.SKILLS_BUILTIN_DIR, self.SKILLS_STORE_DIR)

    def get_skill_versions(self, skill_name: str) -> list[str]:
        store_dir = self.SKILLS_STORE_DIR / skill_name
        if store_dir.exists():
            return get_skill_versions(self.SKILLS_STORE_DIR, skill_name)
        return get_skill_versions(self.SKILLS_BUILTIN_DIR, skill_name)

    def remove_store_skill(self, skill_name: str) -> SkillOperationResult:
        """从全局仓库删除 skill（不能删除内置 skill）。"""
        if not self._is_safe_name(skill_name):
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message="非法 skill 名称",
            )

        builtin_dir = self.SKILLS_BUILTIN_DIR / skill_name
        if builtin_dir.exists():
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"Skill '{skill_name}' 是系统内置，不能删除",
            )

        target_dir = self.SKILLS_STORE_DIR / skill_name
        if not target_dir.exists():
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"全局仓库中不存在 Skill '{skill_name}'",
            )

        try:
            shutil.rmtree(target_dir)
        except Exception as exc:
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"删除失败: {exc}",
            )

        return SkillOperationResult(
            success=True,
            skill_name=skill_name,
            message=f"已从全局仓库删除 '{skill_name}'",
        )

    # ---- 工作区扫描 ----

    # ---- Skill Meta & Hash ----

    def _read_skill_meta(self, workspace_path: Path, skill_name: str) -> SkillMetaInfo | None:
        """读取工作区副本的 .aiasys-skill-meta.json。"""
        meta_path = self.get_workspace_skills_dir(workspace_path) / skill_name / META_FILE_NAME
        if not meta_path.exists():
            return None
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return SkillMetaInfo.model_validate(data)
        except Exception:
            logger.warning("Failed to read skill meta for %s: %s", skill_name, exc_info=True)
            return None

    def get_skill_hash_status(self, skill_name: str, workspace_path: Path) -> dict:
        """返回 skill 的 hash 状态和版本信息。

        返回:
            {
                "hash_status": "synced" | "modified" | "outdated" | "custom" | "unknown",
                "version": str | None,
                "source_type": str | None,
            }
        """
        skill_dir = self.get_workspace_skills_dir(workspace_path) / skill_name
        if not skill_dir.exists():
            return {
                "hash_status": "unknown",
                "version": None,
                "source_type": None,
            }

        meta = self._read_skill_meta(workspace_path, skill_name)
        if meta is None:
            # 无 meta 文件，视为 custom（可能是旧数据或手动放置的）
            return {
                "hash_status": "custom",
                "version": None,
                "source_type": None,
            }

        if meta.source_type == "custom":
            return {
                "hash_status": "custom",
                "version": meta.version,
                "source_type": "custom",
            }

        # 计算当前副本 fingerprint
        current_fp = compute_directory_fingerprint(skill_dir)
        if current_fp != meta.source_fingerprint:
            return {
                "hash_status": "modified",
                "version": meta.version,
                "source_type": meta.source_type,
            }

        # 副本未被修改，检查源是否有更新
        source_dir, _ = self._resolve_store_skill_dir_with_source(skill_name)
        if source_dir is not None:
            source_fp = compute_directory_fingerprint(source_dir)
            if source_fp != meta.source_fingerprint:
                return {
                    "hash_status": "outdated",
                    "version": meta.version,
                    "source_type": meta.source_type,
                }

        return {
            "hash_status": "synced",
            "version": meta.version,
            "source_type": meta.source_type,
        }

    def update_skill(self, skill_name: str, workspace_path: Path) -> SkillOperationResult:
        """更新工作区中的 skill：从源重新复制覆盖。

        仅当副本 fingerprint 与 source_fingerprint 匹配时允许更新。
        如果副本已被修改，返回失败，提示用户卸载后重装。
        """
        if not self._is_safe_name(skill_name):
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message="非法 skill 名称",
            )

        skill_dir = self.get_workspace_skills_dir(workspace_path) / skill_name
        if not skill_dir.exists():
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"工作区中未启用 Skill '{skill_name}'",
            )

        meta = self._read_skill_meta(workspace_path, skill_name)
        if meta is not None and meta.source_type == "custom":
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message="自定义 Skill 不支持更新",
            )

        if meta is not None and meta.source_fingerprint:
            current_fp = compute_directory_fingerprint(skill_dir)
            if current_fp != meta.source_fingerprint:
                return SkillOperationResult(
                    success=False,
                    skill_name=skill_name,
                    message=f"Skill '{skill_name}' 已被修改，请先卸载后重新安装",
                )

        # 调用 enable_skill 重新安装（force=True 覆盖）
        return self.enable_skill(skill_name, workspace_path, force=True)

    def list_workspace_skills(self, workspace_path: Path) -> list[SkillInfo]:
        return list_workspace_skills(workspace_path, self.WORKSPACE_SKILLS_DIR_NAME)

    def _infer_global_workspace_path(self, workspace_path: Path) -> Path | None:
        """从普通工作区路径推断对应的全局工作区路径。

        workspace_path = WORKSPACE_DIR / {user_id} / {workspace_id}
        global_workspace = WORKSPACE_DIR / {user_id} / global_workspace
        """
        try:
            resolved = workspace_path.resolve()
            user_dir = resolved.parent
            global_ws = user_dir / "global_workspace"
            if global_ws.exists() and global_ws.is_dir():
                return global_ws
        except Exception:
            logger.warning("Failed to infer global workspace path: %s", exc_info=True)
        return None

    def list_all_skills(self, workspace_path: Path) -> list[SkillInfo]:
        return list_all_skills(
            self.SKILLS_BUILTIN_DIR,
            self.SKILLS_STORE_DIR,
            workspace_path,
            self.WORKSPACE_SKILLS_DIR_NAME,
            global_workspace_path=self._infer_global_workspace_path(workspace_path),
        )

    # ---- 文件读取 ----

    def get_skill_file_content(
        self,
        skill_name: str,
        workspace_path: Path,
        relative_path: str = "SKILL.md",
    ) -> Optional[tuple[SkillInfo, str, list[str]]]:
        return get_skill_file_content(
            skill_name=skill_name,
            workspace_path=workspace_path,
            workspace_skills_dir_name=self.WORKSPACE_SKILLS_DIR_NAME,
            store_dir=self.SKILLS_STORE_DIR,
            builtin_dir=self.SKILLS_BUILTIN_DIR,
            relative_path=relative_path,
            global_workspace_path=self._infer_global_workspace_path(workspace_path),
        )

    def get_workspace_skill_entry_content(
        self,
        *,
        workspace_path: Path,
        skill_name: str,
    ) -> Optional[tuple[SkillInfo, str]]:
        return get_workspace_skill_entry_content(
            workspace_path=workspace_path,
            skill_name=skill_name,
            workspace_skills_dir_name=self.WORKSPACE_SKILLS_DIR_NAME,
            store_dir=self.SKILLS_STORE_DIR,
            builtin_dir=self.SKILLS_BUILTIN_DIR,
            global_workspace_path=self._infer_global_workspace_path(workspace_path),
        )

    def get_skill_readme_content(
        self,
        *,
        workspace_path: Path,
        skill_name: str,
    ) -> Optional[str]:
        from .skill_discovery import get_skill_readme_content

        return get_skill_readme_content(
            workspace_path=workspace_path,
            skill_name=skill_name,
            workspace_skills_dir_name=self.WORKSPACE_SKILLS_DIR_NAME,
            store_dir=self.SKILLS_STORE_DIR,
            builtin_dir=self.SKILLS_BUILTIN_DIR,
            global_workspace_path=self._infer_global_workspace_path(workspace_path),
        )

    def remove_workspace_skill(
        self,
        skill_name: str,
        workspace_path: Path,
    ) -> SkillOperationResult:
        """删除工作区中的 skill。"""
        if not self._is_safe_name(skill_name):
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message="非法 skill 名称",
            )

        target = self.get_workspace_skills_dir(workspace_path) / skill_name
        if not target.exists():
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"工作区 Skill '{skill_name}' 不存在",
            )

        try:
            if target.is_symlink():
                target.unlink()
            else:
                shutil.rmtree(target)
        except Exception as exc:
            return SkillOperationResult(
                success=False,
                skill_name=skill_name,
                message=f"删除失败: {exc}",
            )

        return SkillOperationResult(
            success=True,
            skill_name=skill_name,
            message=f"已从当前工作区删除 '{skill_name}'",
        )

    # ---- 内部工具 ----

    _is_safe_name = staticmethod(_is_safe_name)
    _list_skill_packages = staticmethod(_list_skill_packages)
    _parse_skill_info = staticmethod(_parse_skill_info)
    _find_entry_file = staticmethod(_find_entry_file)
    _select_import_root = staticmethod(_select_import_root)
    _safe_extract_zip = staticmethod(_safe_extract_zip)
    _sanitize_package_name = staticmethod(_sanitize_package_name)


_skill_manager: Optional[SkillManager] = None


def get_skill_manager() -> SkillManager:
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager()
    return _skill_manager


def get_available_skills_for_workspace(workspace_path: Path) -> dict:
    mgr = get_skill_manager()
    store_skills = mgr.list_store_skills()
    workspace_skills = mgr.list_workspace_skills(workspace_path)
    enabled_names = {s.name for s in workspace_skills}
    return {
        "store": [skill.model_dump() for skill in store_skills],
        "workspace": [skill.model_dump() for skill in workspace_skills],
        "all": [skill.model_dump() for skill in mgr.list_all_skills(workspace_path)],
        "enabled_names": sorted(enabled_names),
    }

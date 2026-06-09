"""Skill 发现与扫描逻辑。

从 manager.py 提取的纯函数：技能扫描、入口查找、元数据解析、ZIP 安全解压。
不依赖 SkillManager 实例状态，所有上下文通过参数显式传入。
"""

from __future__ import annotations

import logging
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Optional

from .models import SkillInfo, SkillSecurityInfo

logger = logging.getLogger(__name__)

ENTRY_FILE_NAME = "SKILL.md"
VERSIONS_DIR_NAME = ".versions"


def _is_safe_name(name: str) -> bool:
    """检查名称是否安全（无路径穿越）。"""
    if not name or name.startswith(".") or "/" in name or "\\" in name:
        return False
    if ".." in name:
        return False
    return True


def _sanitize_package_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-.")
    return normalized or "imported-skill"


def _find_entry_file(package_dir: Path) -> Optional[Path]:
    """在包目录中查找 SKILL.md 入口文件（优先最短路径）。"""
    if not package_dir.exists() or not package_dir.is_dir():
        return None

    candidates = sorted(
        (path for path in package_dir.rglob(ENTRY_FILE_NAME) if path.is_file()),
        key=lambda path: (len(path.relative_to(package_dir).parts), path.as_posix()),
    )
    return candidates[0] if candidates else None


# 脚本/可执行文件后缀
_SCRIPT_EXTENSIONS = {".py", ".sh", ".bash", ".zsh", ".js", ".ts", ".rb", ".pl"}
# 依赖声明文件
_DEPENDENCY_FILES = {"requirements.txt", "package.json", "pyproject.toml", "setup.py", "Cargo.toml", "Gemfile"}
# Skill 内容中暗示高风险工具调用的关键词
_HIGH_RISK_TOOL_KEYWORDS = ["Shell", "WriteFile", "StrReplaceFile", "CreateFile", "RuntimeEnvironment", "InstallMCPServer"]


def _infer_skill_security(
    package_dir: Path,
    base: "SkillSecurityInfo",
    source: str,
) -> "SkillSecurityInfo":
    """通过目录扫描保守推断 Skill 安全风险。

    当 frontmatter 没有显式声明 [security] 时调用。
    """
    import copy

    sec = copy.copy(base)
    sec.source_trust = "builtin" if source == "builtin" else "external"

    has_scripts_dir = False
    has_script_files = False
    has_deps = False
    mentions_high_risk_tools = False

    # 扫描目录结构
    for item in package_dir.rglob("*"):
        rel = item.relative_to(package_dir)
        # 跳过版本目录
        if rel.parts and rel.parts[0] == VERSIONS_DIR_NAME:
            continue

        if item.is_dir() and rel.name == "scripts":
            has_scripts_dir = True
        if item.is_file():
            if item.suffix in _SCRIPT_EXTENSIONS:
                has_script_files = True
            if item.name in _DEPENDENCY_FILES:
                has_deps = True

    # 扫描 SKILL.md 内容中是否暗示调用高风险工具
    entry = _find_entry_file(package_dir)
    if entry is not None:
        try:
            text = entry.read_text(encoding="utf-8")
            for kw in _HIGH_RISK_TOOL_KEYWORDS:
                if kw in text:
                    mentions_high_risk_tools = True
                    break
        except Exception:
            pass

    sec.has_scripts = has_scripts_dir or has_script_files
    sec.installs_dependencies = has_deps
    sec.uses_shell = mentions_high_risk_tools

    # 保守风险定级
    if sec.has_scripts or sec.installs_dependencies or sec.uses_shell:
        sec.risk_level = "high"
    elif sec.requires_env:
        sec.risk_level = "medium"
    else:
        sec.risk_level = "low"

    return sec


def _parse_skill_info(package_dir: Path, *, source: str) -> Optional[SkillInfo]:
    """解析技能包目录，提取 SkillInfo。"""
    if not package_dir.exists() or not package_dir.is_dir():
        return None

    entry_path = _find_entry_file(package_dir)
    if entry_path is None:
        return None

    try:
        content = entry_path.read_text(encoding="utf-8")
    except Exception:
        logger.warning("Failed to read skill entry file %s: %s", entry_path, exc_info=True)
        return None

    display_name = package_dir.name
    description = ""
    env_fields: list[dict[str, Any]] = []
    security = SkillSecurityInfo()
    if content.startswith("+++"):
        parts = content.split("+++", 2)
        if len(parts) >= 3:
            try:
                import tomllib

                fm = tomllib.loads(parts[1].strip())
                if isinstance(fm, dict):
                    if fm.get("name"):
                        display_name = str(fm["name"]).strip()
                    if fm.get("description"):
                        description = str(fm["description"]).strip()
                    raw_env = fm.get("env_fields")
                    if isinstance(raw_env, list):
                        env_fields = [
                            {
                                "name": str(item.get("name", "")),
                                "required": bool(item.get("required", False)),
                                "description": str(item.get("description", "")),
                                "default_value": (
                                    str(item.get("default_value", ""))
                                    if item.get("default_value") is not None
                                    else None
                                ),
                            }
                            for item in raw_env
                            if isinstance(item, dict) and item.get("name")
                        ]
                    raw_sec = fm.get("security")
                    if isinstance(raw_sec, dict):
                        security = SkillSecurityInfo(
                            source_trust=str(raw_sec.get("source_trust", security.source_trust)),
                            risk_level=str(raw_sec.get("risk_level", security.risk_level)),
                            has_scripts=bool(raw_sec.get("has_scripts", security.has_scripts)),
                            requires_env=bool(raw_sec.get("requires_env", security.requires_env)),
                            writes_workspace=bool(raw_sec.get("writes_workspace", security.writes_workspace)),
                            writes_global=bool(raw_sec.get("writes_global", security.writes_global)),
                            uses_shell=bool(raw_sec.get("uses_shell", security.uses_shell)),
                            uses_network=bool(raw_sec.get("uses_network", security.uses_network)),
                            installs_dependencies=bool(raw_sec.get("installs_dependencies", security.installs_dependencies)),
                            adds_tools=[str(t) for t in raw_sec.get("adds_tools", []) if t],
                        )
            except Exception:
                logger.warning(
                    "Failed to parse skill front matter for %s: %s",
                    package_dir,
                    exc_info=True,
                )

    if not description:
        for line in content.splitlines():
            stripped = line.strip()
            if (
                stripped
                and not stripped.startswith("#")
                and not stripped.startswith("-")
                and not stripped.startswith("+++")
            ):
                description = stripped[:120]
                break

    # 保守扫描：如果 frontmatter 没有显式声明 security，自动推断
    if security.risk_level == "medium" and not any(
        [
            security.has_scripts,
            security.requires_env,
            security.writes_workspace,
            security.writes_global,
            security.uses_shell,
            security.uses_network,
            security.installs_dependencies,
            security.adds_tools,
        ]
    ):
        security = _infer_skill_security(package_dir, security, source)

    return SkillInfo(
        name=package_dir.name,
        display_name=display_name,
        description=description,
        source=source,
        path=package_dir,
        entry_path=entry_path,
        entry_relative_path=entry_path.relative_to(package_dir).as_posix(),
        env_fields=env_fields,
        security=security,
    )


def _list_skill_packages(base_dir: Path, *, source: str) -> list[SkillInfo]:
    """扫描目录下所有技能包。"""
    if not base_dir.exists():
        return []

    packages: list[SkillInfo] = []
    for package_dir in sorted(base_dir.iterdir(), key=lambda item: item.name.lower()):
        if not package_dir.is_dir() or package_dir.name.startswith("."):
            continue
        info = _parse_skill_info(package_dir, source=source)
        if info is not None:
            packages.append(info)
    return packages


def _select_import_root(extracted_root: Path) -> Path:
    """ZIP 解压后选择合适的包根目录（跳过 __MACOSX，自动进入单层目录）。"""
    visible_children = [path for path in extracted_root.iterdir() if path.name != "__MACOSX"]

    if len(visible_children) == 1 and visible_children[0].is_dir():
        return visible_children[0]
    return extracted_root


def _safe_extract_zip(archive: zipfile.ZipFile, target_dir: Path) -> None:
    """安全解压 ZIP，防止路径穿越。"""
    target_dir.mkdir(parents=True, exist_ok=True)

    for member in archive.infolist():
        member_path = Path(member.filename)
        if member_path.is_absolute():
            raise ValueError("zip 中包含非法绝对路径")

        resolved_path = (target_dir / member_path).resolve()
        if not str(resolved_path).startswith(str(target_dir.resolve())):
            raise ValueError("zip 中包含路径穿越内容")

        if member.is_dir():
            resolved_path.mkdir(parents=True, exist_ok=True)
            continue

        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as src, resolved_path.open("wb") as dst:
            shutil.copyfileobj(src, dst)


# ---------------------------------------------------------------------------
# Store / workspace discovery
# ---------------------------------------------------------------------------


def list_store_skills(
    builtin_dir: Path,
    store_dir: Path,
) -> list[SkillInfo]:
    """扫描 builtin + store，返回所有全局仓库 skill。

    builtin 中的 skill source 标记为 "builtin"，store 中的标记为 "store"。
    同名时 store 覆盖 builtin（允许用户导入同名 skill 覆盖系统内置）。
    """
    builtin_dir.mkdir(parents=True, exist_ok=True)
    store_dir.mkdir(parents=True, exist_ok=True)
    builtin = _list_skill_packages(builtin_dir, source="builtin")
    store = _list_skill_packages(store_dir, source="store")
    merged = {s.name: s for s in builtin}
    merged.update({s.name: s for s in store})
    return list(merged.values())


def get_skill_versions(store_dir: Path, skill_name: str) -> list[str]:
    """返回某 skill 的所有历史版本列表。"""
    if not _is_safe_name(skill_name):
        return []
    versions_dir = store_dir / skill_name / VERSIONS_DIR_NAME
    if not versions_dir.exists():
        return []
    return sorted(v_dir.name for v_dir in versions_dir.iterdir() if v_dir.is_dir())


def list_workspace_skills(
    workspace_path: Path,
    workspace_skills_dir_name: str,
    source: str = "workspace",
) -> list[SkillInfo]:
    """返回工作区已启用的 skill。"""
    ws_dir = workspace_path / workspace_skills_dir_name
    if not ws_dir.exists():
        return []

    packages: list[SkillInfo] = []
    for item in sorted(ws_dir.iterdir(), key=lambda x: x.name.lower()):
        if not (item.is_symlink() or item.is_dir()):
            continue
        info = _parse_skill_info(item, source=source)
        if info is not None:
            packages.append(info)
    return packages


def list_all_skills(
    builtin_dir: Path,
    store_dir: Path,
    workspace_path: Path,
    workspace_skills_dir_name: str,
    global_workspace_path: Path | None = None,
) -> list[SkillInfo]:
    """返回 builtin + store + global_workspace + workspace 合并后的 skill 列表。

    优先级：workspace 同名覆盖 global_workspace，global_workspace 同名覆盖 store，
    store 同名覆盖 builtin。
    """
    builtin = list_store_skills(builtin_dir, store_dir)
    global_ws: list[SkillInfo] = []
    if global_workspace_path is not None:
        global_ws = list_workspace_skills(
            global_workspace_path, workspace_skills_dir_name, source="global"
        )
    workspace = list_workspace_skills(workspace_path, workspace_skills_dir_name)
    merged = {s.name: s for s in builtin}
    merged.update({s.name: s for s in global_ws})
    merged.update({s.name: s for s in workspace})
    return list(merged.values())


def get_skill_file_content(
    *,
    skill_name: str,
    workspace_path: Path,
    workspace_skills_dir_name: str,
    store_dir: Path,
    builtin_dir: Path,
    relative_path: str = "SKILL.md",
    global_workspace_path: Path | None = None,
) -> Optional[tuple[SkillInfo, str, list[str]]]:
    """读取指定 Skill 的指定文件内容。

    查找优先级：workspace > global_workspace > store > builtin。
    返回: (SkillInfo, 文件内容, 该 skill 目录下所有文件相对路径列表)
    """
    if not _is_safe_name(skill_name):
        return None
    path_obj = Path(relative_path)
    if path_obj.is_absolute() or ".." in path_obj.parts:
        return None

    ws_dir = workspace_path / workspace_skills_dir_name / skill_name
    global_dir = (
        global_workspace_path / workspace_skills_dir_name / skill_name
        if global_workspace_path is not None
        else None
    )
    store_skill_dir = store_dir / skill_name
    builtin_skill_dir = builtin_dir / skill_name

    if ws_dir.exists() and (ws_dir.is_symlink() or ws_dir.is_dir()):
        skill_dir = ws_dir
        source = "workspace"
    elif (
        global_dir is not None
        and global_dir.exists()
        and (global_dir.is_symlink() or global_dir.is_dir())
    ):
        skill_dir = global_dir
        source = "global"
    elif store_skill_dir.exists():
        skill_dir = store_skill_dir
        source = "store"
    elif builtin_skill_dir.exists():
        skill_dir = builtin_skill_dir
        source = "builtin"
    else:
        return None

    info = _parse_skill_info(skill_dir, source=source)
    if info is None:
        return None

    target = (skill_dir / relative_path).resolve()
    if not str(target).startswith(str(skill_dir.resolve())):
        return None
    if not target.exists() or not target.is_file():
        return None

    try:
        content = target.read_text(encoding="utf-8")
    except Exception:
        logger.warning("Failed to read skill file %s: %s", target, exc_info=True)
        return None

    files: list[str] = []
    try:
        for f in sorted(skill_dir.rglob("*")):
            if f.is_file():
                rel = f.relative_to(skill_dir).as_posix()
                files.append(rel)
    except Exception:
        logger.warning("Failed to list files in skill directory %s: %s", skill_dir, exc_info=True)

    return info, content, files


def get_workspace_skill_entry_content(
    *,
    workspace_path: Path,
    skill_name: str,
    workspace_skills_dir_name: str,
    store_dir: Path,
    builtin_dir: Path,
    global_workspace_path: Path | None = None,
) -> Optional[tuple[SkillInfo, str]]:
    """读取指定 skill 的 SKILL.md。

    查找优先级：workspace > global_workspace > store > builtin。
    """
    if not _is_safe_name(skill_name):
        return None

    ws_dir = workspace_path / workspace_skills_dir_name / skill_name
    global_dir = (
        global_workspace_path / workspace_skills_dir_name / skill_name
        if global_workspace_path is not None
        else None
    )
    store_skill_dir = store_dir / skill_name
    builtin_skill_dir = builtin_dir / skill_name

    if ws_dir.exists() and (ws_dir.is_symlink() or ws_dir.is_dir()):
        info = _parse_skill_info(ws_dir, source="workspace")
    elif (
        global_dir is not None
        and global_dir.exists()
        and (global_dir.is_symlink() or global_dir.is_dir())
    ):
        info = _parse_skill_info(global_dir, source="global")
    elif store_skill_dir.exists():
        info = _parse_skill_info(store_skill_dir, source="store")
    elif builtin_skill_dir.exists():
        info = _parse_skill_info(builtin_skill_dir, source="builtin")
    else:
        return None

    if info is None:
        return None

    try:
        content = info.entry_path.read_text(encoding="utf-8")
    except Exception:
        logger.warning(
            "Failed to read skill entry content for %s: %s",
            info.entry_path,
            exc_info=True,
        )
        return None
    return info, content


README_FILE_NAME = "README.md"


def get_skill_readme_content(
    *,
    workspace_path: Path,
    skill_name: str,
    workspace_skills_dir_name: str,
    store_dir: Path,
    builtin_dir: Path,
    global_workspace_path: Path | None = None,
) -> Optional[str]:
    """读取指定 skill 的 README.md 内容。

    查找优先级：workspace > global_workspace > store > builtin。
    若均未找到，返回 None。
    """
    if not _is_safe_name(skill_name):
        return None

    ws_dir = workspace_path / workspace_skills_dir_name / skill_name
    global_dir = (
        global_workspace_path / workspace_skills_dir_name / skill_name
        if global_workspace_path is not None
        else None
    )
    store_skill_dir = store_dir / skill_name
    builtin_skill_dir = builtin_dir / skill_name

    for skill_dir in (ws_dir, global_dir, store_skill_dir, builtin_skill_dir):
        if skill_dir is None:
            continue
        if not skill_dir.exists() or not (skill_dir.is_symlink() or skill_dir.is_dir()):
            continue
        readme_path = skill_dir / README_FILE_NAME
        if readme_path.exists() and readme_path.is_file():
            try:
                return readme_path.read_text(encoding="utf-8")
            except Exception:
                continue
    return None

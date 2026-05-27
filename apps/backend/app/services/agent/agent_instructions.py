"""Agent 规范文件（agent.md / AGENTS.md）读取服务。

对齐 Codex 设计：
- 多层级扫描（项目根 → 工作区路径上的所有目录）
- 支持 AGENTS.override.md 本地覆盖
- 基于 mtime 的缓存（替代 lru_cache）
- budget 控制防止规范文件过大
"""

from __future__ import annotations

import logging
import os
from collections import OrderedDict
from pathlib import Path

from app.core.config import BASE_DIR

logger = logging.getLogger(__name__)

# 按查找优先级排序
_LOCAL_OVERRIDE: str = "AGENTS.override.md"
_AGENT_MD_VARIANTS: tuple[str, ...] = (
    "AGENTS.md",
    "agents.md",
    "Agent.md",
    "agent.md",
)

# mtime 缓存: path -> (mtime, content)
_FILE_CACHE_MAX_SIZE = 100
_file_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()


def _find_project_root(start: Path) -> Path | None:
    """从 start 向上查找包含 .git 或 AGENTS.md 的目录作为项目根。"""
    for parent in [start] + list(start.parents):
        if (parent / ".git").exists() or (parent / "AGENTS.md").exists():
            return parent
    return None


def _find_first_matching_file(directory: Path, variants: tuple[str, ...]) -> Path | None:
    """在目录中查找第一个匹配的文件。"""
    for variant in variants:
        candidate = directory / variant
        if candidate.is_file():
            return candidate
    return None


def _load_file(path: Path) -> str:
    """基于 mtime 的缓存读取（LRU 上限 100）。"""
    path_str = str(path.resolve())
    mtime = os.path.getmtime(path_str)
    cached = _file_cache.get(path_str)
    if cached is not None and cached[0] == mtime:
        _file_cache.move_to_end(path_str)
        return cached[1]
    content = path.read_text(encoding="utf-8").strip()
    _file_cache[path_str] = (mtime, content)
    if len(_file_cache) > _FILE_CACHE_MAX_SIZE:
        _file_cache.popitem(last=False)
    return content


def _collect_agents_md_dirs(
    project_root: Path,
    workspace_dir: Path | None,
) -> list[Path]:
    """收集从项目根到 workspace_dir 路径上的所有目录（包含两端）。"""
    if workspace_dir is None:
        return [project_root]

    try:
        rel = workspace_dir.relative_to(project_root)
    except ValueError:
        # workspace_dir 不在 project_root 下，只返回两端
        return [project_root, workspace_dir]

    dirs: list[Path] = [project_root]
    current = project_root
    for part in rel.parts:
        current = current / part
        dirs.append(current)
    return dirs


def _load_dir_instructions(directory: Path) -> str | None:
    """加载单个目录下的规范文件。优先级：override > AGENTS.md > 变体。"""
    override = directory / _LOCAL_OVERRIDE
    if override.is_file():
        try:
            content = _load_file(override)
            if content:
                return content
        except Exception:
            logger.warning("读取 override 规范失败: %s", override, exc_info=True)

    agents_file = _find_first_matching_file(directory, _AGENT_MD_VARIANTS)
    if agents_file is not None:
        try:
            content = _load_file(agents_file)
            if content:
                return content
        except Exception:
            logger.warning("读取规范文件失败: %s", agents_file, exc_info=True)
    return None


def load_agent_instructions(
    workspace_dir: str | Path | None = None,
    max_bytes: int = 50_000,
) -> str | None:
    """
    加载并合并 agent.md 规范文件。

    扫描规则（对齐 Codex）：
    1. 确定项目根（从 BASE_DIR 向上查找 .git / AGENTS.md）
    2. 从项目根到 workspace_dir 路径上的所有目录，逐层收集规范文件
    3. 每个目录优先查找 AGENTS.override.md，其次查找 AGENTS.md / agent.md
    4. 按"项目根 → 子目录"顺序拼接，深层覆盖语义由模型自行处理
    5. 总内容超过 max_bytes 时自动截断

    返回合并后的规范文本；如果均未找到则返回 None。
    """
    project_root = _find_project_root(BASE_DIR)
    if project_root is None:
        project_root = BASE_DIR

    workspace_path = Path(workspace_dir) if workspace_dir is not None else None
    dirs = _collect_agents_md_dirs(project_root, workspace_path)

    sections: list[str] = []
    remaining = max_bytes

    for d in dirs:
        content = _load_dir_instructions(d)
        if content is None:
            continue

        encoded = content.encode("utf-8")
        if len(encoded) > remaining:
            truncated = encoded[:remaining].decode("utf-8", errors="ignore").rstrip()
            if truncated:
                sections.append(truncated)
                logger.warning(
                    "规范文件预算耗尽，已截断: dir=%s, max_bytes=%s",
                    d,
                    max_bytes,
                )
            break

        sections.append(content)
        remaining -= len(encoded)

    if not sections:
        return None

    if len(sections) == 1:
        return sections[0]

    # 两层时保持兼容格式；多层时用通用拼接
    if len(sections) == 2:
        return (
            "# Agent Instructions\n\n"
            "## Global\n\n" + sections[0] + "\n\n---\n\n"
            "## Workspace\n\n" + sections[1]
        )

    parts: list[str] = ["# Agent Instructions\n"]
    for i, section in enumerate(sections):
        parts.append(f"\n## Layer {i + 1}\n\n{section}")
    return "\n---\n".join(parts)


def invalidate_agent_instructions_cache(path: str | None = None) -> None:
    """使 agent instructions 缓存失效。"""
    if path is not None:
        _file_cache.pop(path, None)
    else:
        _file_cache.clear()

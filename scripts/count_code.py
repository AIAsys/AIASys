#!/usr/bin/env python3
"""
统计项目代码量。

用法：
    python scripts/count_code.py [路径]

默认扫描项目根目录，按语言和目录分组输出代码行数、文件数。
支持通过 --format 指定输出格式：text（默认）、json、markdown。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class LanguageStats:
    files: int = 0
    lines: int = 0


@dataclass
class DirectoryStats:
    files: int = 0
    lines: int = 0
    languages: dict[str, LanguageStats] = field(default_factory=lambda: defaultdict(LanguageStats))


LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript / TSX",
    ".js": "JavaScript",
    ".jsx": "JavaScript / JSX",
    ".css": "CSS",
    ".html": "HTML",
    ".md": "Markdown",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".sh": "Shell",
    ".bash": "Shell",
    ".cjs": "JavaScript",
    ".mjs": "JavaScript",
    ".toml": "TOML",
    ".sql": "SQL",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C/C++ Header",
    ".hpp": "C++ Header",
}

EXCLUDE_DIRS: set[str] = {
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".git",
    ".github",
    ".codex",
    ".kimi-code",
    ".agents",
    ".team-skills",
    "target",
    ".pytest_cache",
    ".mypy_cache",
    ".next",
    ".turbo",
    "out",
    "coverage",
    "storybook-static",
}

EXCLUDE_FILES: set[str] = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "uv.lock",
    "poetry.lock",
    "Cargo.lock",
}


def is_excluded(path: Path) -> bool:
    if path.name in EXCLUDE_DIRS:
        return True
    if path.name in EXCLUDE_FILES:
        return True
    if any(part in EXCLUDE_DIRS for part in path.parts):
        return True
    return False


def iter_source_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if is_excluded(path):
            continue
        if path.suffix.lower() in LANGUAGE_MAP:
            yield path


def count_lines(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def collect_stats(root: Path) -> tuple[dict[str, LanguageStats], dict[str, DirectoryStats], int]:
    lang_stats: dict[str, LanguageStats] = defaultdict(LanguageStats)
    dir_stats: dict[str, DirectoryStats] = defaultdict(DirectoryStats)
    total_files = 0

    for path in iter_source_files(root):
        ext = path.suffix.lower()
        lang = LANGUAGE_MAP.get(ext, "Other")
        lines = count_lines(path)

        rel = path.relative_to(root)
        top_dir = rel.parts[0] if rel.parts else "."

        lang_stats[lang].files += 1
        lang_stats[lang].lines += lines

        dir_stats[top_dir].files += 1
        dir_stats[top_dir].lines += lines
        dir_stats[top_dir].languages[lang].files += 1
        dir_stats[top_dir].languages[lang].lines += lines

        total_files += 1

    return dict(lang_stats), dict(dir_stats), total_files


def format_text(lang_stats: dict[str, LanguageStats], dir_stats: dict[str, DirectoryStats], total_files: int) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("代码量统计")
    lines.append("=" * 60)
    lines.append(f"文件总数: {total_files}")
    lines.append("")

    lines.append("按语言统计")
    lines.append("-" * 40)
    sorted_langs = sorted(lang_stats.items(), key=lambda x: -x[1].lines)
    for lang, stat in sorted_langs:
        lines.append(f"{lang:24s} {stat.files:>6} 文件  {stat.lines:>10,} 行")
    lines.append("")

    lines.append("按顶层目录统计")
    lines.append("-" * 40)
    sorted_dirs = sorted(dir_stats.items(), key=lambda x: -x[1].lines)
    for dname, dstat in sorted_dirs:
        lines.append(f"{dname:24s} {dstat.files:>6} 文件  {dstat.lines:>10,} 行")
    lines.append("")

    return "\n".join(lines)


def format_markdown(lang_stats: dict[str, LanguageStats], dir_stats: dict[str, DirectoryStats], total_files: int) -> str:
    lines: list[str] = []
    lines.append("# 代码量统计")
    lines.append("")
    lines.append(f"- 文件总数: **{total_files}**")
    lines.append("")
    lines.append("## 按语言统计")
    lines.append("")
    lines.append("| 语言 | 文件数 | 代码行数 |")
    lines.append("|------|--------|----------|")
    for lang, stat in sorted(lang_stats.items(), key=lambda x: -x[1].lines):
        lines.append(f"| {lang} | {stat.files} | {stat.lines:,} |")
    lines.append("")
    lines.append("## 按顶层目录统计")
    lines.append("")
    lines.append("| 目录 | 文件数 | 代码行数 |")
    lines.append("|------|--------|----------|")
    for dname, dstat in sorted(dir_stats.items(), key=lambda x: -x[1].lines):
        lines.append(f"| `{dname}` | {dstat.files} | {dstat.lines:,} |")
    lines.append("")
    return "\n".join(lines)


def format_json(lang_stats: dict[str, LanguageStats], dir_stats: dict[str, DirectoryStats], total_files: int) -> str:
    payload = {
        "total_files": total_files,
        "total_lines": sum(s.lines for s in lang_stats.values()),
        "languages": {lang: {"files": s.files, "lines": s.lines} for lang, s in lang_stats.items()},
        "directories": {
            dname: {
                "files": dstat.files,
                "lines": dstat.lines,
                "languages": {lang: {"files": s.files, "lines": s.lines} for lang, s in dstat.languages.items()},
            }
            for dname, dstat in dir_stats.items()
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="统计项目代码量")
    parser.add_argument("path", nargs="?", default=".", help="要扫描的路径（默认当前目录）")
    parser.add_argument("--format", choices=["text", "json", "markdown"], default="text", help="输出格式")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"路径不存在: {root}", file=sys.stderr)
        return 1

    lang_stats, dir_stats, total_files = collect_stats(root)

    if args.format == "json":
        print(format_json(lang_stats, dir_stats, total_files))
    elif args.format == "markdown":
        print(format_markdown(lang_stats, dir_stats, total_files))
    else:
        print(format_text(lang_stats, dir_stats, total_files))

    return 0


if __name__ == "__main__":
    sys.exit(main())

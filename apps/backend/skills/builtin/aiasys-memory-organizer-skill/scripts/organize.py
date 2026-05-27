#!/usr/bin/env python3
"""Memory Organizer 工具脚本。

只提供文件操作工具（备份、diff、原子写入），不调用 LLM。
整理逻辑由读取 SKILL.md 的 Agent 自行完成。

用法:
    # 备份当前 memory 文件
    python3 scripts/organize.py --mode backup --target memory

    # 生成 diff 报告（对比当前文件和 Agent 整理后的新文件）
    python3 scripts/organize.py --mode diff --target memory --from-file /tmp/new_memory.md

    # 原子写入整理后的内容（自动备份 + 生成 diff 报告）
    python3 scripts/organize.py --mode write --target memory --from-file /tmp/new_memory.md

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录（必需）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from utils import (
    atomic_write_file,
    backup_file,
    error_output,
    generate_diff_report,
    get_workspace_root,
    json_output,
    read_text_file,
    resolve_memory_paths,
)


def run_backup(target: str, paths: dict[str, Path]) -> dict:
    """备份目标 memory 文件。"""
    path_map = {
        "memory": paths["memory"],
        "summary": paths["summary"],
        "workspace": paths["workspace"],
    }
    target_path = path_map.get(target)
    if target_path is None:
        raise ValueError(f"不支持的 target: {target}")

    if not target_path.exists():
        return {
            "mode": "backup",
            "target": target,
            "file": str(target_path),
            "backup_path": None,
            "message": "目标文件不存在，无需备份",
        }

    backup_path = backup_file(target_path)
    return {
        "mode": "backup",
        "target": target,
        "file": str(target_path),
        "backup_path": str(backup_path),
        "message": f"已备份到 {backup_path.name}",
    }


def run_diff(target: str, paths: dict[str, Path], from_file: Path) -> dict:
    """对比当前文件和整理后的新文件，生成 diff 报告。"""
    path_map = {
        "memory": paths["memory"],
        "summary": paths["summary"],
        "workspace": paths["workspace"],
    }
    target_path = path_map.get(target)
    if target_path is None:
        raise ValueError(f"不支持的 target: {target}")

    original = read_text_file(target_path)
    if not from_file.exists():
        raise ValueError(f"对比文件不存在: {from_file}")
    new = from_file.read_text(encoding="utf-8")

    report = generate_diff_report(original, new, target)
    report["mode"] = "diff"
    report["original_file"] = str(target_path)
    report["new_file"] = str(from_file)
    return report


def run_write(target: str, paths: dict[str, Path], from_file: Path) -> dict:
    """原子写入整理后的内容，自动备份并生成 diff 报告。"""
    path_map = {
        "memory": paths["memory"],
        "summary": paths["summary"],
        "workspace": paths["workspace"],
    }
    target_path = path_map.get(target)
    if target_path is None:
        raise ValueError(f"不支持的 target: {target}")

    if not from_file.exists():
        raise ValueError(f"写入源文件不存在: {from_file}")

    original = read_text_file(target_path)
    new = from_file.read_text(encoding="utf-8")

    if original.strip() == new.strip():
        return {
            "mode": "write",
            "target": target,
            "file": str(target_path),
            "changed": False,
            "reason": "内容与原文一致，无需写入",
        }

    # 先备份
    backup_result = run_backup(target, paths)

    # 原子写入
    atomic_write_file(target_path, new)

    # 生成报告
    report = generate_diff_report(original, new, target)
    report["mode"] = "write"
    report["file"] = str(target_path)
    report["changed"] = True
    report["backup_path"] = backup_result.get("backup_path")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="AIASys Memory Organizer（工具脚本）")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["backup", "diff", "write"],
        help="backup=备份, diff=对比报告, write=原子写入",
    )
    parser.add_argument(
        "--target",
        required=True,
        choices=["memory", "summary", "workspace"],
        help="目标文件: memory=MEMORY.md, summary=memory_summary.md, workspace=workspace_memory.md",
    )
    parser.add_argument(
        "--from-file",
        default=None,
        help="diff/write 模式时，指定 Agent 整理后的新文件路径",
    )
    args = parser.parse_args()

    if args.mode in ("diff", "write") and not args.from_file:
        error_output(f"--mode {args.mode} 必须提供 --from-file")
        sys.exit(1)

    try:
        workspace_root = get_workspace_root()
        paths = resolve_memory_paths(workspace_root)

        if args.mode == "backup":
            result = run_backup(args.target, paths)
        elif args.mode == "diff":
            result = run_diff(args.target, paths, Path(args.from_file))
        else:
            result = run_write(args.target, paths, Path(args.from_file))

        json_output(result)
    except Exception as exc:
        error_output(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()

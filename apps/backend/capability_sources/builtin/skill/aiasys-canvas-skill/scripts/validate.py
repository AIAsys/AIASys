#!/usr/bin/env python3
"""Validate a JSON Canvas file."""

from __future__ import annotations

import argparse
import json
import sys

from canvas_utils import get_workspace_root, load_canvas, resolve_file, validate_canvas


def main() -> None:
    parser = argparse.ArgumentParser(description="校验 .canvas 文件")
    parser.add_argument("--file", required=True, help=".canvas 文件路径")
    args = parser.parse_args()

    try:
        workspace_root = get_workspace_root()
        file_path = resolve_file(args.file, workspace_root)
        data = load_canvas(file_path)
        stats = validate_canvas(data)
        print(
            json.dumps(
                {
                    "status": "success",
                    "file": args.file,
                    **stats,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

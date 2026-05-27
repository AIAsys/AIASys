#!/usr/bin/env python3
"""读取 .canvas 文件并输出完整 JSON。

用法:
    python3 read.py --file /workspace/board.canvas

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录
"""

from __future__ import annotations

import argparse
import json
import sys

from canvas_utils import get_workspace_root, load_canvas, resolve_file, validate_canvas


def main():
    parser = argparse.ArgumentParser(description="读取 .canvas 文件")
    parser.add_argument("--file", required=True, help=".canvas 文件路径")
    args = parser.parse_args()

    try:
        workspace_root = get_workspace_root()
        file_path = resolve_file(args.file, workspace_root)

        result = load_canvas(file_path)
        validate_canvas(result)

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

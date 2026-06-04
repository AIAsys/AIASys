#!/usr/bin/env python3
"""完整覆盖写入 .canvas 文件。

用法:
    python3 write.py --file /workspace/board.canvas --json '{"nodes":[],"edges":[]}'

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录
"""

from __future__ import annotations

import argparse
import json
import sys

from canvas_utils import get_workspace_root, resolve_file, save_canvas, validate_canvas


def main():
    parser = argparse.ArgumentParser(description="写入 .canvas 文件")
    parser.add_argument("--file", required=True, help=".canvas 文件路径")
    parser.add_argument("--json", required=True, dest="json_str", help="完整 canvas JSON 字符串")
    args = parser.parse_args()

    try:
        workspace_root = get_workspace_root()
        file_path = resolve_file(args.file, workspace_root)

        data = json.loads(args.json_str)
        stats = validate_canvas(data)
        save_canvas(file_path, data)

        print(json.dumps({"status": "success", "file": args.file, **stats}, ensure_ascii=False))

    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

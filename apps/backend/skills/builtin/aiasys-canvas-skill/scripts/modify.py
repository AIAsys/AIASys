#!/usr/bin/env python3
"""语义化修改 .canvas 文件的节点和边。

用法:
    python3 modify.py --file /workspace/board.canvas --action add_node --text "新节点" --x 100 --y 200
    python3 modify.py --file /workspace/board.canvas --action remove_node --node_id <uuid>
    python3 modify.py --file /workspace/board.canvas --action add_edge --from_node <id> --to_node <id>
    python3 modify.py --file /workspace/board.canvas --action remove_edge --edge_id <uuid>

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录
"""

from __future__ import annotations

import argparse
import json
import sys
from canvas_utils import (
    get_workspace_root,
    load_canvas,
    new_id,
    resolve_file,
    save_canvas,
    validate_canvas,
)

NODE_FIELDS = ("text", "file", "url", "label")


def build_node_content(args: argparse.Namespace) -> dict[str, object]:
    if args.node_type == "file":
        if not args.file_path:
            raise ValueError("file 节点必须提供 --file_path")
        node: dict[str, object] = {"file": args.file_path}
        if args.subpath:
            node["subpath"] = args.subpath
        return node
    if args.node_type == "link":
        if not args.url:
            raise ValueError("link 节点必须提供 --url")
        return {"url": args.url}
    if args.node_type == "group":
        return {"label": args.label or args.text or "分组"}
    if not args.text:
        raise ValueError("text 节点必须提供 --text")
    return {"text": args.text}


def apply_optional_node_updates(target: dict[str, object], args: argparse.Namespace) -> None:
    if args.node_type:
        target["type"] = args.node_type
    if args.text is not None:
        target["text"] = args.text
    if args.file_path is not None:
        target["file"] = args.file_path
    if args.url is not None:
        target["url"] = args.url
    if args.label is not None:
        target["label"] = args.label
    if args.subpath is not None:
        if args.subpath:
            target["subpath"] = args.subpath
        else:
            target.pop("subpath", None)
    if args.color is not None:
        if args.color:
            target["color"] = args.color
        else:
            target.pop("color", None)
    if args.x is not None:
        target["x"] = args.x
    if args.y is not None:
        target["y"] = args.y
    if args.width is not None:
        target["width"] = args.width
    if args.height is not None:
        target["height"] = args.height


def main():
    parser = argparse.ArgumentParser(description="修改 .canvas 文件的节点和边")
    parser.add_argument("--file", required=True, help=".canvas 文件路径")
    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "add_node",
            "update_node",
            "remove_node",
            "add_edge",
            "update_edge",
            "remove_edge",
        ],
    )
    parser.add_argument("--node_id", default=None, help="节点 ID（update/remove 时必需）")
    parser.add_argument("--text", default=None, help="节点文本内容")
    parser.add_argument("--x", type=float, default=None, help="节点 X 坐标")
    parser.add_argument("--y", type=float, default=None, help="节点 Y 坐标")
    parser.add_argument("--width", type=float, default=None, help="节点宽度")
    parser.add_argument("--height", type=float, default=None, help="节点高度")
    parser.add_argument(
        "--node_type",
        default="text",
        choices=["text", "file", "link", "group"],
        help="节点类型（默认 text）",
    )
    parser.add_argument("--file_path", default=None, help="file 节点引用的工作区路径")
    parser.add_argument("--url", default=None, help="link 节点 URL")
    parser.add_argument("--subpath", default=None, help="file 节点内部位置，如 #标题")
    parser.add_argument("--color", default=None, help="节点或边颜色")
    parser.add_argument("--from_node", default=None, help="add_edge: 起始节点 ID")
    parser.add_argument("--to_node", default=None, help="add_edge: 目标节点 ID")
    parser.add_argument(
        "--from_side",
        default=None,
        choices=["top", "right", "bottom", "left"],
        help="add_edge: 起始侧",
    )
    parser.add_argument(
        "--to_side",
        default=None,
        choices=["top", "right", "bottom", "left"],
        help="add_edge: 目标侧",
    )
    parser.add_argument("--label", default=None, help="add_edge: 边标签")
    parser.add_argument("--edge_id", default=None, help="remove_edge: 边 ID")
    args = parser.parse_args()

    try:
        workspace_root = get_workspace_root()
        file_path = resolve_file(args.file, workspace_root)
        canvas = load_canvas(file_path)
        validate_canvas(canvas)

        if args.action == "add_node":
            node = {
                "id": new_id("node"),
                "type": args.node_type,
                "x": args.x if args.x is not None else 0,
                "y": args.y if args.y is not None else 0,
                "width": args.width if args.width is not None else 250,
                "height": args.height if args.height is not None else 120,
                **build_node_content(args),
            }
            if args.color:
                node["color"] = args.color
            canvas["nodes"].append(node)
            save_canvas(file_path, canvas)
            print(
                json.dumps(
                    {"status": "success", "action": "add_node", "node": node},
                    ensure_ascii=False,
                    indent=2,
                )
            )

        elif args.action == "update_node":
            if not args.node_id:
                raise ValueError("update_node 操作必须提供 --node_id")
            target = next((n for n in canvas["nodes"] if n["id"] == args.node_id), None)
            if target is None:
                raise ValueError(f"节点 {args.node_id} 不存在")
            apply_optional_node_updates(target, args)
            save_canvas(file_path, canvas)
            print(
                json.dumps(
                    {"status": "success", "action": "update_node", "node": target},
                    ensure_ascii=False,
                    indent=2,
                )
            )

        elif args.action == "remove_node":
            if not args.node_id:
                raise ValueError("remove_node 操作必须提供 --node_id")
            canvas["nodes"] = [n for n in canvas["nodes"] if n["id"] != args.node_id]
            canvas["edges"] = [
                e
                for e in canvas["edges"]
                if e.get("fromNode") != args.node_id and e.get("toNode") != args.node_id
            ]
            save_canvas(file_path, canvas)
            print(
                json.dumps(
                    {"status": "success", "action": "remove_node", "node_id": args.node_id},
                    ensure_ascii=False,
                )
            )

        elif args.action == "add_edge":
            if not args.from_node or not args.to_node:
                raise ValueError("add_edge 操作必须提供 --from_node 和 --to_node")
            node_ids = {node.get("id") for node in canvas["nodes"]}
            if args.from_node not in node_ids:
                raise ValueError(f"from_node 不存在: {args.from_node}")
            if args.to_node not in node_ids:
                raise ValueError(f"to_node 不存在: {args.to_node}")
            edge = {
                "id": new_id("edge"),
                "fromNode": args.from_node,
                "toNode": args.to_node,
                "toEnd": "arrow",
            }
            if args.from_side:
                edge["fromSide"] = args.from_side
            if args.to_side:
                edge["toSide"] = args.to_side
            if args.label:
                edge["label"] = args.label
            if args.color:
                edge["color"] = args.color
            canvas["edges"].append(edge)
            save_canvas(file_path, canvas)
            print(
                json.dumps(
                    {"status": "success", "action": "add_edge", "edge": edge},
                    ensure_ascii=False,
                    indent=2,
                )
            )

        elif args.action == "update_edge":
            if not args.edge_id:
                raise ValueError("update_edge 操作必须提供 --edge_id")
            target = next((e for e in canvas["edges"] if e.get("id") == args.edge_id), None)
            if target is None:
                raise ValueError(f"边 {args.edge_id} 不存在")
            if args.from_side is not None:
                target["fromSide"] = args.from_side
            if args.to_side is not None:
                target["toSide"] = args.to_side
            if args.label is not None:
                if args.label:
                    target["label"] = args.label
                else:
                    target.pop("label", None)
            if args.color is not None:
                if args.color:
                    target["color"] = args.color
                else:
                    target.pop("color", None)
            save_canvas(file_path, canvas)
            print(
                json.dumps(
                    {"status": "success", "action": "update_edge", "edge": target},
                    ensure_ascii=False,
                    indent=2,
                )
            )

        elif args.action == "remove_edge":
            if not args.edge_id:
                raise ValueError("remove_edge 操作必须提供 --edge_id")
            canvas["edges"] = [e for e in canvas["edges"] if e.get("id") != args.edge_id]
            save_canvas(file_path, canvas)
            print(
                json.dumps(
                    {"status": "success", "action": "remove_edge", "edge_id": args.edge_id},
                    ensure_ascii=False,
                )
            )

    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

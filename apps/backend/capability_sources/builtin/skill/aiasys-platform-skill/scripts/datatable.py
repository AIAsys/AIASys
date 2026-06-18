#!/usr/bin/env python3
"""多维数据表管理脚本。

用法:
    python3 manage.py create --name <名称> --id <ID> --columns <JSON>
    python3 manage.py list
    python3 manage.py query --file <相对路径> [--operation schema|records] [--limit N]
    python3 manage.py insert --file <相对路径> --records <JSON>
    python3 manage.py update --file <相对路径> --record-id <ID> --data <JSON>
    python3 manage.py delete --file <相对路径> --record-id <ID>
    python3 manage.py modify-column --file <相对路径> --action add|remove|update ...

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 脚本位于 skills/builtin/datatable-skill/scripts/ 下，将 backend 根目录加入 sys.path
_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _SCRIPT_DIR.parent.parent.parent.parent  # -> apps/backend
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.data_table_service import (  # noqa: E402
    DataTableColumnDef,
    DataTableCreateRequest,
    add_data_table_column,
    create_data_table,
    delete_data_table_record,
    insert_data_table_records,
    read_data_table_records,
    read_data_table_schema,
    remove_data_table_column,
    update_data_table_column,
    update_data_table_record,
)


def get_workspace_root() -> Path:
    ws_root = os.environ.get("AIASYS_WORKSPACE_ROOT", "")
    if ws_root:
        return Path(ws_root).resolve()
    raise RuntimeError("AIASYS_WORKSPACE_ROOT 环境变量未设置")


def resolve_table_path(relative_path: str, workspace_root: Path) -> Path:
    p = (workspace_root / relative_path).resolve()
    try:
        p.relative_to(workspace_root)
    except ValueError:
        raise PermissionError(f"路径超出工作区: {relative_path}")
    return p


def cmd_create(args):
    ws = get_workspace_root()
    columns = json.loads(args.columns)
    column_defs = [DataTableColumnDef(**col) for col in columns]
    request = DataTableCreateRequest(
        name=args.name,
        id=args.id,
        directory=args.directory or "",
        columns=column_defs,
    )
    result = create_data_table(ws, request)
    print(
        json.dumps(
            {
                "status": "success",
                "name": result.name,
                "relative_path": result.relative_path,
                "record_count": result.record_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_list(args):
    ws = get_workspace_root()
    tables = []
    for file_path in sorted(ws.rglob("*.table.db")):
        if file_path.is_file():
            rel = file_path.relative_to(ws).as_posix()
            tables.append(rel)
    print(
        json.dumps(
            {
                "count": len(tables),
                "tables": tables,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_query(args):
    ws = get_workspace_root()
    file_path = resolve_table_path(args.file, ws)

    if not file_path.exists():
        print(json.dumps({"error": f"数据表文件不存在: {args.file}"}, ensure_ascii=False))
        sys.exit(1)

    if args.operation == "schema":
        schema = read_data_table_schema(file_path)
        print(json.dumps(schema, ensure_ascii=False, indent=2))
    else:
        records = read_data_table_records(file_path, limit=args.limit)
        schema = read_data_table_schema(file_path)
        columns = schema.get("columns", [])
        col_names = ["_id"] + [c["name"] for c in columns]

        if args.filter_column and args.filter_value:
            filtered = []
            for rec in records:
                val = rec.get(args.filter_column)
                if val is not None and str(val) == args.filter_value:
                    filtered.append(rec)
            records = filtered

        print(
            json.dumps(
                {
                    "table": schema.get("metadata", {}).get("name", args.file),
                    "count": len(records),
                    "columns": col_names,
                    "records": records,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


def cmd_insert(args):
    ws = get_workspace_root()
    file_path = resolve_table_path(args.file, ws)

    if not file_path.exists():
        print(json.dumps({"error": f"数据表文件不存在: {args.file}"}, ensure_ascii=False))
        sys.exit(1)

    records = json.loads(args.records)
    inserted_ids = insert_data_table_records(file_path, records)
    print(
        json.dumps(
            {
                "status": "success",
                "inserted_count": len(inserted_ids),
                "inserted_ids": inserted_ids,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_update(args):
    ws = get_workspace_root()
    file_path = resolve_table_path(args.file, ws)

    if not file_path.exists():
        print(json.dumps({"error": f"数据表文件不存在: {args.file}"}, ensure_ascii=False))
        sys.exit(1)

    data = json.loads(args.data)
    success = update_data_table_record(file_path, args.record_id, data)
    print(
        json.dumps(
            {
                "status": "success" if success else "not_found",
                "record_id": args.record_id,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_delete(args):
    ws = get_workspace_root()
    file_path = resolve_table_path(args.file, ws)

    if not file_path.exists():
        print(json.dumps({"error": f"数据表文件不存在: {args.file}"}, ensure_ascii=False))
        sys.exit(1)

    success = delete_data_table_record(file_path, args.record_id)
    print(
        json.dumps(
            {
                "status": "success" if success else "not_found",
                "record_id": args.record_id,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_modify_column(args):
    ws = get_workspace_root()
    file_path = resolve_table_path(args.file, ws)

    if not file_path.exists():
        print(json.dumps({"error": f"数据表文件不存在: {args.file}"}, ensure_ascii=False))
        sys.exit(1)

    options = json.loads(args.options) if args.options else []

    if args.action == "add":
        col_def = DataTableColumnDef(
            name=args.column_name,
            type=args.column_type or "text",
            required=args.required,
            options=options,
        )
        add_data_table_column(file_path, col_def)
        print(
            json.dumps(
                {"status": "success", "action": "add", "column": args.column_name},
                ensure_ascii=False,
            )
        )

    elif args.action == "remove":
        remove_data_table_column(file_path, args.column_name)
        print(
            json.dumps(
                {"status": "success", "action": "remove", "column": args.column_name},
                ensure_ascii=False,
            )
        )

    elif args.action == "update":
        col_def = DataTableColumnDef(
            name=args.new_name or args.column_name,
            type=args.column_type or "text",
            required=args.required,
            options=options,
        )
        update_data_table_column(file_path, args.column_name, col_def)
        print(
            json.dumps(
                {"status": "success", "action": "update", "column": args.column_name},
                ensure_ascii=False,
            )
        )


def main():
    parser = argparse.ArgumentParser(description="多维数据表管理工具")
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="创建数据表")
    p_create.add_argument("--name", required=True)
    p_create.add_argument("--id", required=True)
    p_create.add_argument("--columns", required=True, help="列定义的 JSON 数组")
    p_create.add_argument("--directory", default="")

    # list
    sub.add_parser("list", help="列出所有数据表")

    # query
    p_query = sub.add_parser("query", help="查询数据表 schema 或记录")
    p_query.add_argument("--file", required=True)
    p_query.add_argument("--operation", default="records", choices=["schema", "records"])
    p_query.add_argument("--limit", type=int, default=50)
    p_query.add_argument("--filter-column", default="")
    p_query.add_argument("--filter-value", default="")

    # insert
    p_insert = sub.add_parser("insert", help="插入记录")
    p_insert.add_argument("--file", required=True)
    p_insert.add_argument("--records", required=True, help="记录 JSON 数组")

    # update
    p_update = sub.add_parser("update", help="更新记录")
    p_update.add_argument("--file", required=True)
    p_update.add_argument("--record-id", required=True)
    p_update.add_argument("--data", required=True, help="更新的字段 JSON 对象")

    # delete
    p_delete = sub.add_parser("delete", help="删除记录")
    p_delete.add_argument("--file", required=True)
    p_delete.add_argument("--record-id", required=True)

    # modify-column
    p_modcol = sub.add_parser("modify-column", help="修改列结构")
    p_modcol.add_argument("--file", required=True)
    p_modcol.add_argument("--action", required=True, choices=["add", "remove", "update"])
    p_modcol.add_argument("--column-name", required=True)
    p_modcol.add_argument("--column-type", default="text")
    p_modcol.add_argument("--new-name", default="")
    p_modcol.add_argument("--required", action="store_true", default=False)
    p_modcol.add_argument("--options", default="")

    args = parser.parse_args()

    try:
        if args.command == "create":
            cmd_create(args)
        elif args.command == "list":
            cmd_list(args)
        elif args.command == "query":
            cmd_query(args)
        elif args.command == "insert":
            cmd_insert(args)
        elif args.command == "update":
            cmd_update(args)
        elif args.command == "delete":
            cmd_delete(args)
        elif args.command == "modify-column":
            cmd_modify_column(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

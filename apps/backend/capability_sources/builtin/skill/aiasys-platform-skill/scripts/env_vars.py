#!/usr/bin/env python3
"""工作区环境变量管理脚本。

读写 .aiasys/workspace/workspace.json 中的 runtime_binding.env_vars。

用法:
    python3 manage.py get --name <变量名>
    python3 manage.py set --name <变量名> --value <值>
    python3 manage.py delete --name <变量名>

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SENSITIVE_KEY_PATTERNS = (
    "KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASS",
    "AUTH",
    "CREDENTIAL",
    "PRIVATE",
)


def _is_sensitive_key(name: str) -> bool:
    upper = name.upper()
    return any(pattern in upper for pattern in SENSITIVE_KEY_PATTERNS)


def _mask_sensitive(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def get_workspace_root() -> Path:
    ws_root = os.environ.get("AIASYS_WORKSPACE_ROOT", "")
    if ws_root:
        return Path(ws_root).resolve()
    raise RuntimeError("AIASYS_WORKSPACE_ROOT 环境变量未设置")


def _workspace_meta_path(ws: Path) -> Path:
    return ws / ".aiasys" / "workspace" / "workspace.json"


def _read_env_vars(ws: Path) -> dict[str, str]:
    metadata_path = _workspace_meta_path(ws)
    if not metadata_path.exists():
        return {}
    try:
        meta = json.loads(metadata_path.read_text(encoding="utf-8"))
        runtime_binding = meta.get("runtime_binding")
        if isinstance(runtime_binding, dict):
            env_vars = runtime_binding.get("env_vars")
            if isinstance(env_vars, dict):
                return {str(k): str(v) for k, v in env_vars.items()}
    except Exception:
        pass
    return {}


def _write_env_vars(ws: Path, env_vars: dict[str, str]) -> None:
    metadata_path = _workspace_meta_path(ws)
    meta: dict = {}
    if metadata_path.exists():
        try:
            meta = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if not isinstance(meta, dict):
        meta = {}
    runtime_binding = meta.get("runtime_binding")
    if not isinstance(runtime_binding, dict):
        runtime_binding = {}
    runtime_binding["env_vars"] = env_vars
    meta["runtime_binding"] = runtime_binding
    meta["_schema_version"] = meta.get("_schema_version", 1)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_get(args):
    ws = get_workspace_root()
    env_vars = _read_env_vars(ws)

    if args.name not in env_vars:
        print(
            json.dumps(
                {
                    "status": "not_found",
                    "name": args.name,
                    "message": f"环境变量 '{args.name}' 不存在",
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    raw_value = env_vars[args.name]
    sensitive = _is_sensitive_key(args.name)
    display_value = _mask_sensitive(raw_value) if sensitive else raw_value

    print(
        json.dumps(
            {
                "status": "success",
                "name": args.name,
                "value": display_value,
                "masked": sensitive,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_set(args):
    ws = get_workspace_root()
    env_vars = _read_env_vars(ws)
    env_vars[args.name] = args.value
    _write_env_vars(ws, env_vars)

    print(
        json.dumps(
            {
                "status": "success",
                "name": args.name,
                "message": f"环境变量 '{args.name}' 已设置",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_delete(args):
    ws = get_workspace_root()
    env_vars = _read_env_vars(ws)

    if args.name not in env_vars:
        print(
            json.dumps(
                {
                    "status": "not_found",
                    "name": args.name,
                    "message": f"环境变量 '{args.name}' 不存在",
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    del env_vars[args.name]
    _write_env_vars(ws, env_vars)

    print(
        json.dumps(
            {
                "status": "success",
                "name": args.name,
                "message": f"环境变量 '{args.name}' 已删除",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description="工作区环境变量管理")
    sub = parser.add_subparsers(dest="command", required=True)

    p_get = sub.add_parser("get", help="读取环境变量")
    p_get.add_argument("--name", required=True)

    p_set = sub.add_parser("set", help="设置环境变量")
    p_set.add_argument("--name", required=True)
    p_set.add_argument("--value", required=True)

    p_del = sub.add_parser("delete", help="删除环境变量")
    p_del.add_argument("--name", required=True)

    args = parser.parse_args()

    try:
        if args.command == "get":
            cmd_get(args)
        elif args.command == "set":
            cmd_set(args)
        elif args.command == "delete":
            cmd_delete(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

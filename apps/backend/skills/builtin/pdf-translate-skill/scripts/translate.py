#!/usr/bin/env python3
"""PDF 翻译脚本 — 通过 pdf2zh 翻译当前工作区内的 PDF 文件。

用法:
    python3 translate.py --pdf_path /workspace/doc.pdf [--source_lang en] [--target_lang zh] [--translator google]

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录（由 Shell 自动注入）
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def get_workspace_root() -> Path:
    ws_root = os.environ.get("AIASYS_WORKSPACE_ROOT", "")
    if ws_root:
        return Path(ws_root).resolve()
    cwd = Path.cwd()
    if (cwd / "metadata.json").exists():
        return cwd
    raise RuntimeError("无法确定工作区根目录，请设置 AIASYS_WORKSPACE_ROOT 环境变量")


def resolve_path(raw_path: str, workspace_root: Path) -> tuple[Path, str]:
    """解析用户传入的路径，返回 (宿主机绝对路径, 可见路径)。"""
    agent_path = Path(raw_path)
    if agent_path.is_absolute():
        rel = Path(*agent_path.parts[1:]) if str(agent_path).startswith("/workspace") else agent_path
    else:
        rel = agent_path

    host_path = (workspace_root / rel).resolve()
    try:
        host_path.relative_to(workspace_root)
    except ValueError:
        raise PermissionError(f"路径超出当前 workspace: {raw_path}")

    visible = "/workspace/" + rel.as_posix() if rel != Path(".") else "/workspace"
    return host_path, visible


def get_pdf2zh_command() -> list[str]:
    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, "--from", "pdf2zh", "pdf2zh"]
    uv = shutil.which("uv")
    if uv:
        return [uv, "tool", "run", "--from", "pdf2zh", "pdf2zh"]
    raise RuntimeError("未找到 uvx 或 uv，无法启动隔离的 pdf2zh 运行环境")


def run_translate(
    *,
    pdf_path: Path,
    output_dir: Path,
    source_lang: str,
    target_lang: str,
    translator: str,
    ignore_cache: bool,
) -> tuple[str, str]:
    runner = get_pdf2zh_command()
    command = [
        *runner,
        "--service", translator,
        "--lang-in", source_lang,
        "--lang-out", target_lang,
        "--output", str(output_dir),
    ]
    if ignore_cache:
        command.append("--ignore-cache")
    command.append(str(pdf_path))

    completed = subprocess.run(command, capture_output=True, text=True, timeout=1800)

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        raise RuntimeError(f"pdf2zh 执行失败: {stderr or stdout or '未知错误'}")

    mono = output_dir / f"{pdf_path.stem}-mono.pdf"
    dual = output_dir / f"{pdf_path.stem}-dual.pdf"
    if not mono.exists() or not dual.exists():
        raise RuntimeError("pdf2zh 执行完成，但未生成预期的 mono/dual PDF 文件")
    return str(mono), str(dual)


def main():
    parser = argparse.ArgumentParser(description="翻译 PDF 文件（基于 pdf2zh）")
    parser.add_argument("--pdf_path", required=True, help="PDF 文件路径（相对或 /workspace/ 形式）")
    parser.add_argument("--output_dir", default=None, help="输出目录（默认 pdf_translations/<文件名>/）")
    parser.add_argument("--source_lang", default="en", help="源语言代码（默认 en）")
    parser.add_argument("--target_lang", default="zh", help="目标语言代码（默认 zh）")
    parser.add_argument("--translator", default="google", help="翻译服务: google/openai/gemini")
    parser.add_argument("--ignore_cache", action="store_true", help="忽略 pdf2zh 缓存")
    args = parser.parse_args()

    try:
        workspace_root = get_workspace_root()
        host_pdf, visible_pdf = resolve_path(args.pdf_path, workspace_root)

        if not host_pdf.exists():
            print(json.dumps({"error": f"文件不存在: {visible_pdf}"}, ensure_ascii=False))
            sys.exit(1)
        if host_pdf.suffix.lower() != ".pdf":
            print(json.dumps({"error": f"不是 PDF 文件: {visible_pdf}"}, ensure_ascii=False))
            sys.exit(1)

        if args.output_dir:
            output_host, output_visible = resolve_path(args.output_dir, workspace_root)
        else:
            output_host = workspace_root / "pdf_translations" / host_pdf.stem
            output_visible = f"/workspace/pdf_translations/{host_pdf.stem}"

        output_host.mkdir(parents=True, exist_ok=True)

        mono_path, dual_path = run_translate(
            pdf_path=host_pdf,
            output_dir=output_host,
            source_lang=args.source_lang,
            target_lang=args.target_lang,
            translator=args.translator,
            ignore_cache=args.ignore_cache,
        )

        def to_visible(p: str) -> str:
            pp = Path(p).resolve()
            try:
                rel = pp.relative_to(workspace_root)
                return f"/workspace/{rel.as_posix()}"
            except ValueError:
                return str(pp)

        result = {
            "status": "success",
            "source_pdf": visible_pdf,
            "output_dir": output_visible,
            "mono_pdf": to_visible(mono_path),
            "dual_pdf": to_visible(dual_path),
            "translator": args.translator,
            "source_lang": args.source_lang,
            "target_lang": args.target_lang,
        }

        manifest = output_host / "translation_manifest.json"
        manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["manifest"] = to_visible(str(manifest))

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

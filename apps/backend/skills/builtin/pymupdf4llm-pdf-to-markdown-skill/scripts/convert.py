#!/usr/bin/env python3
"""PDF 转 Markdown 转换脚本。

用法:
    python3 convert.py --input /workspace/paper.pdf --output /workspace/paper.md [--pages all]

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def get_workspace_root() -> Path:
    ws_root = os.environ.get("AIASYS_WORKSPACE_ROOT", "")
    if ws_root:
        return Path(ws_root).resolve()
    raise RuntimeError("无法确定工作区根目录")


def resolve_path(raw: str, workspace_root: Path) -> Path:
    normalized = raw.replace("\\", "/").strip()
    if normalized.startswith("/workspace/"):
        rel = Path(normalized[len("/workspace/") :])
    elif normalized == "/workspace":
        rel = Path(".")
    else:
        rel = Path(normalized)
    host = (workspace_root / rel).resolve()
    try:
        host.relative_to(workspace_root)
    except ValueError:
        raise PermissionError(f"路径超出工作区: {raw}")
    return host


def parse_pages(pages_str: str) -> list[int] | None:
    if pages_str.lower() == "all":
        return None
    pages: list[int] = []
    for part in pages_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start.strip()) - 1, int(end.strip())))
        else:
            pages.append(int(part) - 1)
    return sorted(set(pages))


def _try_pymupdf4llm(input_path: Path, output_path: Path, pages: list[int] | None) -> bool:
    pages_repr = repr(pages) if pages is not None else "None"
    code = (
        f"import pymupdf4llm; "
        f"md = pymupdf4llm.to_markdown({str(input_path)!r}, pages={pages_repr}); "
        f"open({str(output_path)!r}, 'w', encoding='utf-8').write(md)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
        return True
    if "ModuleNotFoundError" in result.stderr or "No module named" in result.stderr:
        install = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pymupdf4llm"],
            capture_output=True,
            text=True,
        )
        if install.returncode != 0:
            return False
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0
    return False


def _try_fitz(input_path: Path, output_path: Path, pages: list[int] | None) -> bool:
    pages_repr = repr(pages) if pages is not None else "None"
    code = (
        f"import fitz; "
        f"doc = fitz.open({str(input_path)!r}); "
        f"pages = {pages_repr}; "
        f"text = chr(10).join(doc[i].get_text() for i in (pages if pages else range(len(doc)))); "
        f"open({str(output_path)!r}, 'w', encoding='utf-8').write(text)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0


def _try_pdftotext(input_path: Path, output_path: Path, pages: list[int] | None) -> bool:
    cmd = ["pdftotext", "-layout", str(input_path), str(output_path)]
    if pages is not None:
        first = min(pages) + 1
        last = max(pages) + 1
        cmd.extend(["-f", str(first), "-l", str(last)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def validate_output(output_path: Path) -> int:
    if not output_path.exists():
        raise RuntimeError("输出文件未生成")
    size = output_path.stat().st_size
    if size == 0:
        raise RuntimeError("输出文件为空")
    if size < 1024:
        raise RuntimeError(f"输出文件过小 ({size} bytes)，可能转换不完整")
    return size


def main():
    parser = argparse.ArgumentParser(description="PDF 转 Markdown")
    parser.add_argument("--input", required=True, help="输入 PDF 文件路径")
    parser.add_argument("--output", required=True, help="输出 Markdown 文件路径")
    parser.add_argument("--pages", default="all", help="页码范围，例如 'all'、'1,2,3' 或 '1-5'")
    args = parser.parse_args()

    try:
        workspace_root = get_workspace_root()
        input_path = resolve_path(args.input, workspace_root)
        output_path = resolve_path(args.output, workspace_root)

        if not input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        pages = parse_pages(args.pages)

        method = None
        if _try_pymupdf4llm(input_path, output_path, pages):
            method = "pymupdf4llm"
        elif _try_fitz(input_path, output_path, pages):
            method = "fitz"
        elif _try_pdftotext(input_path, output_path, pages):
            method = "pdftotext"
        else:
            raise RuntimeError("所有转换方法均失败")

        size_bytes = validate_output(output_path)

        result = {
            "status": "ok",
            "input": str(input_path),
            "output": str(output_path),
            "method": method,
            "pages": args.pages,
            "size_bytes": size_bytes,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

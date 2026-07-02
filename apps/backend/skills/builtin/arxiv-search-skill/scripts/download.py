#!/usr/bin/env python3
"""下载 arXiv PDF 并输出 JSON。

用法:
    python3 download.py --paper_id 2305.00362 --output_dir /workspace/papers

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

ARXIV_PDF_URL_TEMPLATE = "https://arxiv.org/pdf/{paper_id}.pdf"
USER_AGENT = "AIASys/1.0"


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


def download_pdf(paper_id: str, output_dir: Path) -> dict:
    """下载指定 arXiv 论文的 PDF。"""
    url = ARXIV_PDF_URL_TEMPLATE.format(paper_id=paper_id)
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=120, stream=True)
    resp.raise_for_status()

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{paper_id}.pdf"

    with output_path.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    file_size = output_path.stat().st_size
    return {
        "paper_id": paper_id,
        "status": "success",
        "file_path": str(output_path),
        "file_size": file_size,
        "url": url,
    }


def main():
    parser = argparse.ArgumentParser(description="下载 arXiv PDF")
    parser.add_argument("--paper_id", required=True, help="arXiv 论文 ID")
    parser.add_argument("--output_dir", required=True, help="保存目录")
    args = parser.parse_args()

    try:
        workspace_root = get_workspace_root()
        output_dir = resolve_path(args.output_dir, workspace_root)
        result = download_pdf(args.paper_id, output_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

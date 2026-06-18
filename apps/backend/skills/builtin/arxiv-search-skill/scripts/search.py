#!/usr/bin/env python3
"""搜索 arXiv 论文并输出 JSON。

用法:
    python3 search.py --query "electricity+price+forecasting" --max_results 10 --output_dir /workspace/papers

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote_plus

import requests

ARXIV_API_URL = "https://export.arxiv.org/api/query"
USER_AGENT = "AIASys/1.0"


def get_workspace_root() -> Path:
    ws_root = os.environ.get("AIASYS_WORKSPACE_ROOT", "")
    if ws_root:
        return Path(ws_root).resolve()
    raise RuntimeError("无法确定工作区根目录")


def resolve_path(raw: str, workspace_root: Path) -> Path:
    p = Path(raw)
    if p.is_absolute():
        rel = Path(*p.parts[1:]) if str(p).startswith("/workspace") else p
    else:
        rel = p
    host = (workspace_root / rel).resolve()
    try:
        host.relative_to(workspace_root)
    except ValueError:
        raise PermissionError(f"路径超出工作区: {raw}")
    return host


def extract_arxiv_id(entry_id: str) -> str:
    """从 arXiv URL 中提取论文 ID。"""
    if "/abs/" in entry_id:
        return entry_id.split("/abs/")[-1].strip()
    if "/pdf/" in entry_id:
        return entry_id.split("/pdf/")[-1].replace(".pdf", "").strip()
    return entry_id.strip()


def search_arxiv(query: str, max_results: int) -> list[dict]:
    """调用 arXiv API 搜索论文。"""
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(ARXIV_API_URL, params=params, headers=headers, timeout=60)
    resp.raise_for_status()

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    root = ET.fromstring(resp.content)
    entries = []

    for entry in root.findall("atom:entry", ns):
        entry_id_elem = entry.find("atom:id", ns)
        entry_id = entry_id_elem.text if entry_id_elem is not None else ""
        paper_id = extract_arxiv_id(entry_id)

        title_elem = entry.find("atom:title", ns)
        title = (title_elem.text or "").replace("\n", " ").strip() if title_elem is not None else ""

        summary_elem = entry.find("atom:summary", ns)
        summary = (summary_elem.text or "").strip() if summary_elem is not None else ""

        published_elem = entry.find("atom:published", ns)
        published = published_elem.text if published_elem is not None else ""

        updated_elem = entry.find("atom:updated", ns)
        updated = updated_elem.text if updated_elem is not None else ""

        authors = []
        for author in entry.findall("atom:author", ns):
            name_elem = author.find("atom:name", ns)
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text.strip())

        categories = []
        for cat in entry.findall("atom:category", ns):
            term = cat.get("term")
            if term:
                categories.append(term)

        pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"

        entries.append(
            {
                "id": paper_id,
                "title": title,
                "authors": authors,
                "summary": summary,
                "published": published,
                "updated": updated,
                "categories": categories,
                "pdf_url": pdf_url,
                "entry_id": entry_id,
            }
        )

    return entries


def main():
    parser = argparse.ArgumentParser(description="搜索 arXiv 论文")
    parser.add_argument("--query", required=True, help="搜索关键词")
    parser.add_argument("--max_results", type=int, default=10, help="最大结果数 (默认 10)")
    parser.add_argument("--output_dir", help="结果保存目录 (可选)")
    args = parser.parse_args()

    try:
        workspace_root = get_workspace_root()
        entries = search_arxiv(args.query, args.max_results)

        result = {
            "query": args.query,
            "max_results": args.max_results,
            "found": len(entries),
            "papers": entries,
        }

        if args.output_dir:
            output_dir = resolve_path(args.output_dir, workspace_root)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / "search_results.json"
            output_file.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            result["saved_to"] = str(output_file)

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

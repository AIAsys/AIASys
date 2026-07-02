#!/usr/bin/env python3
"""竞赛文献搜索（arXiv API，支持分类过滤、日期范围、字段限定）并输出 JSON。

用法:
    # 基础搜索
    python3 arxiv_search.py --query "electricity price forecasting" --max_results 10

    # 限定机器学习分类 + 近2年
    python3 arxiv_search.py \
      --query "transformer time series" \
      --categories "cs.LG,cs.AI,stat.ML" \
      --date_from 2023-01-01 \
      --max_results 20

    # 只在摘要中搜索 + 按提交日期排序
    python3 arxiv_search.py \
      --query "attention mechanism" \
      --search_field abs \
      --sort_by submittedDate \
      --sort_order descending

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

ARXIV_API_URL = "https://export.arxiv.org/api/query"
USER_AGENT = "AIASys/1.0"

# 常用 arXiv 机器学习相关分类
ML_CATEGORIES = {
    "cs.LG": "机器学习",
    "cs.AI": "人工智能",
    "cs.CL": "计算语言学",
    "cs.CV": "计算机视觉",
    "cs.IR": "信息检索",
    "cs.NE": "神经与进化计算",
    "stat.ML": "统计机器学习",
    "eess.SP": "信号处理",
}


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


def extract_arxiv_id(entry_id: str) -> str:
    """从 arXiv URL 中提取论文 ID。"""
    if "/abs/" in entry_id:
        return entry_id.split("/abs/")[-1].strip()
    if "/pdf/" in entry_id:
        return entry_id.split("/pdf/")[-1].replace(".pdf", "").strip()
    return entry_id.strip()


def load_existing_ids(references_dir: Path) -> set[str]:
    """从 references_dir 下的 meta.json 或 index.json 读取已有论文 ID。"""
    existing: set[str] = set()

    for filename in ("meta.json", "index.json"):
        file_path = references_dir / filename
        if file_path.exists():
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    if "papers" in data and isinstance(data["papers"], list):
                        for paper in data["papers"]:
                            if isinstance(paper, dict):
                                pid = (
                                    paper.get("id")
                                    or paper.get("paper_id")
                                    or paper.get("arxiv_id")
                                )
                                if pid:
                                    existing.add(str(pid).strip())
                    elif "entries" in data and isinstance(data["entries"], list):
                        for entry in data["entries"]:
                            if isinstance(entry, dict):
                                pid = (
                                    entry.get("id")
                                    or entry.get("paper_id")
                                    or entry.get("arxiv_id")
                                )
                                if pid:
                                    existing.add(str(pid).strip())
                    else:
                        for key in ("id", "paper_id", "arxiv_id"):
                            if key in data:
                                existing.add(str(data[key]).strip())
                                break
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            pid = item.get("id") or item.get("paper_id") or item.get("arxiv_id")
                            if pid:
                                existing.add(str(pid).strip())
            except (json.JSONDecodeError, OSError):
                continue

    return existing


def build_search_query(
    query: str,
    search_field: str,
    categories: list[str] | None,
) -> str:
    """构造 arXiv API 的 search_query 参数。

    注意：arXiv API 的 submittedDate 过滤器在实际使用中不可靠，始终返回零结果。
    日期过滤改为在客户端根据 <published> 字段进行。
    """
    parts: list[str] = []

    # 关键词部分
    field_prefix = ""
    if search_field and search_field != "all":
        field_prefix = f"{search_field}:"

    # 处理空格：替换为 +，保留用户可能的 AND/OR 语法
    normalized_query = query.strip().replace(" ", "+")
    parts.append(f"{field_prefix}{normalized_query}")

    # 分类过滤
    if categories:
        cat_conditions = [f"cat:{cat.strip()}" for cat in categories if cat.strip()]
        if len(cat_conditions) == 1:
            parts.append(cat_conditions[0])
        elif len(cat_conditions) > 1:
            parts.append(" OR ".join(f"({c})" for c in cat_conditions))

    # 组合所有条件（默认 AND）
    if len(parts) == 1:
        return parts[0]
    return "+AND+".join(f"({p})" for p in parts)


def filter_by_date(
    entries: list[dict],
    date_from: str | None,
    date_to: str | None,
) -> list[dict]:
    """根据 <published> 字段在客户端过滤日期范围。"""
    if not date_from and not date_to:
        return entries

    df_parsed = None
    dt_parsed = None

    if date_from:
        df_parsed = datetime.strptime(date_from.replace("/", "-"), "%Y-%m-%d")
    if date_to:
        dt_parsed = datetime.strptime(date_to.replace("/", "-"), "%Y-%m-%d")

    filtered: list[dict] = []
    for entry in entries:
        published = entry.get("published", "")
        if not published:
            continue
        try:
            # published 格式如 "2022-02-15T01:43:27Z"
            entry_date = datetime.strptime(published[:10], "%Y-%m-%d")
        except ValueError:
            continue

        if df_parsed and entry_date < df_parsed:
            continue
        if dt_parsed and entry_date > dt_parsed:
            continue
        filtered.append(entry)

    return filtered


def search_arxiv(
    query: str,
    search_field: str,
    categories: list[str] | None,
    max_results: int,
    sort_by: str,
    sort_order: str,
) -> list[dict]:
    """调用 arXiv API 搜索论文。"""
    search_query = build_search_query(query, search_field, categories)

    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.get(ARXIV_API_URL, params=params, headers=headers, timeout=60)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"arXiv API 请求失败: {exc}")

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
    parser = argparse.ArgumentParser(
        description="竞赛文献搜索（arXiv API，支持分类过滤、日期范围、字段限定）"
    )
    parser.add_argument("--query", required=True, help="搜索关键词")
    parser.add_argument(
        "--search_field",
        default="all",
        choices=["all", "ti", "tiabs", "abs", "au", "cat"],
        help="搜索字段: all(全部)=默认, ti(标题), tiabs(标题+摘要), abs(摘要), au(作者), cat(分类)",
    )
    parser.add_argument(
        "--categories",
        help="arXiv 分类过滤，多个用逗号分隔，如 'cs.LG,cs.AI,stat.ML'",
    )
    parser.add_argument(
        "--date_from",
        help="起始日期 (YYYY-MM-DD)，只搜该日期之后提交的论文",
    )
    parser.add_argument(
        "--date_to",
        help="结束日期 (YYYY-MM-DD)，只搜该日期之前提交的论文",
    )
    parser.add_argument("--max_results", type=int, default=10, help="最大结果数 (默认 10)")
    parser.add_argument(
        "--sort_by",
        default="relevance",
        choices=["relevance", "lastUpdatedDate", "submittedDate"],
        help="排序方式 (默认 relevance)",
    )
    parser.add_argument(
        "--sort_order",
        default="descending",
        choices=["ascending", "descending"],
        help="排序方向 (默认 descending)",
    )
    parser.add_argument(
        "--references_dir",
        help="本地参考文献目录，用于去重",
    )
    parser.add_argument(
        "--output_dir",
        help="结果保存目录 (可选)",
    )
    args = parser.parse_args()

    try:
        workspace_root = get_workspace_root()

        categories = None
        if args.categories:
            categories = [c.strip() for c in args.categories.split(",") if c.strip()]

        all_entries = search_arxiv(
            query=args.query,
            search_field=args.search_field,
            categories=categories,
            max_results=args.max_results,
            sort_by=args.sort_by,
            sort_order=args.sort_order,
        )

        # 客户端日期过滤（arXiv API 的 submittedDate 过滤器不可靠）
        all_entries = filter_by_date(all_entries, args.date_from, args.date_to)

        existing_ids: set[str] = set()
        if args.references_dir:
            references_dir = resolve_path(args.references_dir, workspace_root)
            if references_dir.exists():
                existing_ids = load_existing_ids(references_dir)

        new_papers: list[dict] = []
        excluded: list[dict] = []

        for paper in all_entries:
            if paper["id"] in existing_ids:
                excluded.append(paper)
            else:
                new_papers.append(paper)

        result = {
            "query": args.query,
            "search_field": args.search_field,
            "categories": categories,
            "date_from": args.date_from,
            "date_to": args.date_to,
            "sort_by": args.sort_by,
            "sort_order": args.sort_order,
            "max_results": args.max_results,
            "total_found": len(all_entries),
            "new_papers": new_papers,
            "new_count": len(new_papers),
            "excluded_count": len(excluded),
            "existing_ids_loaded": len(existing_ids),
        }

        if args.output_dir:
            output_dir = resolve_path(args.output_dir, workspace_root)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / "results.json"
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

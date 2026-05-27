#!/usr/bin/env python3
"""将论文摄入 AIASys SQLite 知识图谱和注册表。

用法:
    python3 ingest.py --paper_dir /workspace/references/2305.00362 --experiments /workspace/experiments/index.json

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def get_workspace_root() -> Path:
    ws_root = os.environ.get("AIASYS_WORKSPACE_ROOT", "")
    if ws_root:
        return Path(ws_root).resolve()
    raise RuntimeError("无法确定工作区根目录")


def resolve_path(raw: str, workspace_root: Path) -> Path:
    p = Path(raw)
    if p.is_absolute():
        rel = Path(*p.parts[2:]) if str(p) == "/workspace" or str(p).startswith("/workspace/") else p
    else:
        rel = p
    host = (workspace_root / rel).resolve()
    try:
        host.relative_to(workspace_root)
    except ValueError:
        raise PermissionError(f"路径超出工作区: {raw}")
    return host


def resolve_graph_db_path(
    experiments_data: dict,
    project_dir: Path,
    workspace_root: Path,
) -> Path | None:
    """按 AIASys 工作区约定解析知识图谱路径。"""
    kg_path = str(experiments_data.get("knowledge_graph_db_path") or "").strip()
    if kg_path:
        if kg_path.startswith("/workspace/"):
            candidate = workspace_root / kg_path[len("/workspace/") :]
        elif kg_path.startswith("/global/"):
            candidate = workspace_root.parent / "global_workspace" / kg_path[len("/global/") :]
        else:
            candidate = Path(kg_path)
            if not candidate.is_absolute():
                candidate = project_dir / kg_path
        return candidate

    kg_id = str(experiments_data.get("knowledge_graph_id") or "").strip()
    if kg_id:
        return workspace_root.parent / "global_workspace" / "resources" / "graphs" / f"{kg_id}.db"

    graph_file = str(experiments_data.get("knowledge_graph_file") or "").strip()
    if not graph_file:
        return None
    candidate = project_dir / graph_file
    if candidate.exists():
        return candidate
    return project_dir / Path(graph_file).name


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _ensure_graph_db(graph_db_path: Path) -> None:
    """确保知识图谱数据库存在且有基本表结构。"""
    graph_db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(graph_db_path)) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS entities (
                entity_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                description TEXT,
                properties TEXT,
                source_doc_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS relations (
                relation_id TEXT PRIMARY KEY,
                source_entity_id TEXT NOT NULL,
                target_entity_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                description TEXT,
                strength REAL DEFAULT 1.0,
                properties TEXT,
                source_doc_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS graph_metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')


def _insert_or_update_entity(
    conn: sqlite3.Connection,
    entity_id: str,
    name: str,
    entity_type: str,
    description: str = "",
    properties: dict | None = None,
    source_doc_id: str = "",
) -> None:
    """插入或更新实体。"""
    props_json = json.dumps(properties, ensure_ascii=False) if properties else "{}"
    conn.execute(
        '''
        INSERT INTO entities (entity_id, name, entity_type, description, properties, source_doc_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_id) DO UPDATE SET
            name=excluded.name,
            entity_type=excluded.entity_type,
            description=excluded.description,
            properties=excluded.properties,
            source_doc_id=excluded.source_doc_id,
            created_at=excluded.created_at
        ''',
        (entity_id, name, entity_type, description, props_json, source_doc_id, datetime.now(timezone.utc).isoformat()),
    )


def _insert_or_update_relation(
    conn: sqlite3.Connection,
    relation_id: str,
    source_entity_id: str,
    target_entity_id: str,
    relation_type: str,
    description: str = "",
    strength: float = 1.0,
    properties: dict | None = None,
    source_doc_id: str = "",
) -> None:
    """插入或更新关系。"""
    props_json = json.dumps(properties, ensure_ascii=False) if properties else "{}"
    conn.execute(
        '''
        INSERT INTO relations (relation_id, source_entity_id, target_entity_id, relation_type, description, strength, properties, source_doc_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(relation_id) DO UPDATE SET
            source_entity_id=excluded.source_entity_id,
            target_entity_id=excluded.target_entity_id,
            relation_type=excluded.relation_type,
            description=excluded.description,
            strength=excluded.strength,
            properties=excluded.properties,
            source_doc_id=excluded.source_doc_id,
            created_at=excluded.created_at
        ''',
        (relation_id, source_entity_id, target_entity_id, relation_type, description, strength, props_json, source_doc_id, datetime.now(timezone.utc).isoformat()),
    )


def _entity_exists(conn: sqlite3.Connection, entity_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM entities WHERE entity_id = ? LIMIT 1", (entity_id,)).fetchone()
    return row is not None


def _get_entity_id_by_name(conn: sqlite3.Connection, name: str, entity_type: str) -> str | None:
    row = conn.execute(
        "SELECT entity_id FROM entities WHERE name = ? AND entity_type = ? LIMIT 1",
        (name, entity_type),
    ).fetchone()
    return row[0] if row else None


def ingest_paper_to_graph(
    graph_db_path: Path,
    paper_id: str,
    title: str,
    authors: list[str],
    abstract: str,
    tags: list[str],
    url: str,
    year: str,
) -> dict:
    """将论文信息写入知识图谱。"""
    _ensure_graph_db(graph_db_path)

    with sqlite3.connect(str(graph_db_path)) as conn:
        # 1. 论文实体
        paper_entity_id = f"paper:{paper_id}"
        _insert_or_update_entity(
            conn,
            entity_id=paper_entity_id,
            name=title,
            entity_type="paper",
            description=abstract[:500] if abstract else "",
            properties={
                "paper_id": paper_id,
                "title": title,
                "url": url,
                "year": year,
                "tags": tags,
            },
            source_doc_id=paper_id,
        )

        # 2. 作者实体 + 关系
        for author in authors:
            author_name = str(author).strip()
            if not author_name:
                continue
            author_entity_id = f"author:{author_name.lower().replace(' ', '_')}"
            _insert_or_update_entity(
                conn,
                entity_id=author_entity_id,
                name=author_name,
                entity_type="author",
                source_doc_id=paper_id,
            )
            _insert_or_update_relation(
                conn,
                relation_id=f"wrote:{author_entity_id}:{paper_entity_id}",
                source_entity_id=author_entity_id,
                target_entity_id=paper_entity_id,
                relation_type="wrote",
                description=f"{author_name} 撰写了 {title}",
                source_doc_id=paper_id,
            )

        # 3. 关键词/方法实体 + 关系
        for tag in tags:
            tag_name = str(tag).strip()
            if not tag_name:
                continue
            # 检查是否已存在同名实体
            existing_id = _get_entity_id_by_name(conn, tag_name, "method")
            if existing_id:
                method_entity_id = existing_id
            else:
                method_entity_id = f"method:{uuid.uuid4().hex[:12]}"

            _insert_or_update_entity(
                conn,
                entity_id=method_entity_id,
                name=tag_name,
                entity_type="method",
                source_doc_id=paper_id,
            )
            _insert_or_update_relation(
                conn,
                relation_id=f"contains:{paper_entity_id}:{method_entity_id}",
                source_entity_id=paper_entity_id,
                target_entity_id=method_entity_id,
                relation_type="contains",
                description=f"论文 {title} 涉及方法 {tag_name}",
                source_doc_id=paper_id,
            )

        conn.commit()

    return {
        "paper_entity_id": paper_entity_id,
        "author_count": len(authors),
        "method_count": len(tags),
    }


def _extract_year(published: str) -> str:
    """从 published 日期字符串中提取年份。"""
    if not published:
        return ""
    match = re.match(r"(\d{4})", published)
    return match.group(1) if match else ""


def ingest_single_paper(
    workspace_root: Path,
    paper_dir: Path,
    experiments_path: Path,
    paper_id: str,
    title: str,
    authors: list,
    url: str,
    year: str,
    abstract: str,
    tags: list,
    paper_md_content: str = "",
) -> dict:
    """摄入单篇论文到 references/index.json 和 graph.db。"""
    # 更新 references/index.json
    references_dir = paper_dir.parent
    references_index_path = references_dir / "index.json"

    references_index = load_json(references_index_path)
    if "project" not in references_index:
        references_index["project"] = "unknown"
    if "last_updated" not in references_index:
        references_index["last_updated"] = datetime.now(timezone.utc).isoformat()
    if "papers" not in references_index:
        references_index["papers"] = []

    existing = None
    for p in references_index["papers"]:
        # 兼容旧 paper_id 和新 id 两种字段名
        if p.get("id") == paper_id or p.get("paper_id") == paper_id:
            existing = p
            break

    paper_entry = {
        "id": paper_id,
        "title": title,
        "authors": authors,
        "url": url,
        "year": year,
        "abstract": abstract,
        "tags": tags,
        "directory": str(paper_dir.relative_to(workspace_root)).replace("\\", "/"),
        "has_markdown": bool(paper_md_content),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }

    if existing:
        existing.update(paper_entry)
        ingest_status = "updated"
    else:
        references_index["papers"].append(paper_entry)
        ingest_status = "created"

    references_index["last_updated"] = datetime.now(timezone.utc).isoformat()
    save_json(references_index_path, references_index)

    # 写入知识图谱
    experiments_data = load_json(experiments_path)
    project_dir = experiments_path.parent.parent
    graph_db_path = resolve_graph_db_path(experiments_data, project_dir, workspace_root)
    graph_result = None
    graph_status = "skipped"

    if graph_db_path:
        graph_result = ingest_paper_to_graph(
            graph_db_path=graph_db_path,
            paper_id=paper_id,
            title=title,
            authors=authors,
            abstract=abstract,
            tags=tags,
            url=url,
            year=year,
        )
        graph_result["graph_db_path"] = str(graph_db_path)
        graph_status = "ingested"
    else:
        graph_result = {
            "reason": "experiments/index.json 中未配置 knowledge_graph_id、knowledge_graph_db_path 或 knowledge_graph_file"
        }

    return {
        "ingest_status": ingest_status,
        "paper": {
            "paper_id": paper_id,
            "title": title,
            "authors": authors,
            "year": year,
            "has_markdown": bool(paper_md_content),
        },
        "references_index": str(references_index_path.relative_to(workspace_root)).replace("\\", "/"),
        "experiments_index": str(experiments_path.relative_to(workspace_root)).replace("\\", "/"),
        "graph_status": graph_status,
        "graph_result": graph_result,
    }


def ingest_from_paper_dir(paper_dir: Path, experiments_path: Path, workspace_root: Path) -> dict:
    """从论文目录摄入。"""
    meta_path = paper_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"论文元数据文件不存在: {meta_path}")

    meta = load_json(meta_path)
    paper_id = meta.get("paper_id") or paper_dir.name
    title = meta.get("title", "")
    authors = meta.get("authors", [])
    url = meta.get("url", "")
    year = meta.get("year", "")
    abstract = meta.get("abstract", "")
    tags = meta.get("tags", [])

    paper_md_path = paper_dir / "paper.md"
    paper_md_content = ""
    if paper_md_path.exists():
        paper_md_content = paper_md_path.read_text(encoding="utf-8")

    return ingest_single_paper(
        workspace_root=workspace_root,
        paper_dir=paper_dir,
        experiments_path=experiments_path,
        paper_id=paper_id,
        title=title,
        authors=authors,
        url=url,
        year=year,
        abstract=abstract,
        tags=tags,
        paper_md_content=paper_md_content,
    )


def ingest_from_results_json(
    results_json_path: Path,
    experiments_path: Path,
    workspace_root: Path,
) -> dict:
    """从 arxiv_search.py 的 results.json 批量摄入。"""
    data = load_json(results_json_path)
    new_papers = data.get("new_papers", [])

    if not new_papers:
        return {
            "status": "ok",
            "ingested_count": 0,
            "message": "results.json 中没有新论文",
        }

    # 确定 references 目录
    experiments_data = load_json(experiments_path)
    paper_registry_path = experiments_data.get("paper_registry_path", "references/index.json")
    references_dir = experiments_path.parent.parent / Path(paper_registry_path).parent

    results = []
    errors = []
    for paper in new_papers:
        try:
            paper_id = paper.get("id", "")
            if not paper_id:
                continue

            # 创建 paper_dir 和 meta.json
            paper_dir = references_dir / paper_id
            paper_dir.mkdir(parents=True, exist_ok=True)

            meta = {
                "paper_id": paper_id,
                "title": paper.get("title", ""),
                "authors": paper.get("authors", []),
                "url": paper.get("pdf_url", ""),
                "year": _extract_year(paper.get("published", "")),
                "abstract": paper.get("summary", ""),
                "tags": paper.get("categories", []),
                "published": paper.get("published", ""),
                "updated": paper.get("updated", ""),
            }
            meta_path = paper_dir / "meta.json"
            save_json(meta_path, meta)

            result = ingest_single_paper(
                workspace_root=workspace_root,
                paper_dir=paper_dir,
                experiments_path=experiments_path,
                paper_id=paper_id,
                title=meta["title"],
                authors=meta["authors"],
                url=meta["url"],
                year=meta["year"],
                abstract=meta["abstract"],
                tags=meta["tags"],
            )
            results.append(result)
        except Exception as exc:
            errors.append({"paper_id": paper.get("id", "unknown"), "error": str(exc)})

    return {
        "status": "ok",
        "ingested_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description="将论文摄入知识图谱（本地 SQLite）和注册表")
    parser.add_argument(
        "--paper_dir",
        help="论文目录路径（包含 meta.json 和可选的 paper.md）。与 --results_json 二选一",
    )
    parser.add_argument(
        "--results_json",
        help="arxiv_search.py 输出的 results.json 路径，批量摄入。与 --paper_dir 二选一",
    )
    parser.add_argument(
        "--experiments",
        required=True,
        help="experiments/index.json 路径",
    )
    args = parser.parse_args()

    if not args.paper_dir and not args.results_json:
        parser.error("必须提供 --paper_dir 或 --results_json 之一")
    if args.paper_dir and args.results_json:
        parser.error("--paper_dir 和 --results_json 不能同时使用")

    try:
        workspace_root = get_workspace_root()
        experiments_path = resolve_path(args.experiments, workspace_root)

        if args.paper_dir:
            paper_dir = resolve_path(args.paper_dir, workspace_root)
            if not paper_dir.is_dir():
                raise NotADirectoryError(f"论文目录不存在: {paper_dir}")
            result = ingest_from_paper_dir(paper_dir, experiments_path, workspace_root)
        else:
            results_json_path = resolve_path(args.results_json, workspace_root)
            if not results_json_path.exists():
                raise FileNotFoundError(f"results.json 不存在: {results_json_path}")
            result = ingest_from_results_json(results_json_path, experiments_path, workspace_root)

        print(json.dumps({"status": "ok", **result}, ensure_ascii=False, indent=2))

    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

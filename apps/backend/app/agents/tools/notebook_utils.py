"""
Notebook 工具共享辅助方法。

目标：
- 统一 notebook 文件的路径校验、读写、规范化和摘要逻辑
- 默认返回适合 Agent 消费的安全摘要，避免把整份 ipynb JSON 或
  base64 图像直接塞进模型上下文
"""

from __future__ import annotations

import json
import re
import uuid
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.history import current_session_root, current_workspace

DEFAULT_NOTEBOOK_CELL_PREVIEW_CHARS = 120
DEFAULT_NOTEBOOK_OUTPUT_PREVIEW_CHARS = 160
NOTEBOOK_BINARY_MIME_TYPES = frozenset({"image/png", "image/jpeg", "application/pdf"})
DATA_URL_BASE64_PATTERN = re.compile(
    r"data:[^\s\"')>]+;base64,[A-Za-z0-9+/=\r\n]+",
    re.IGNORECASE,
)


def resolve_workspace_root_from_context() -> Path | None:
    workspace = current_workspace.get()
    if workspace:
        return Path(workspace)
    return None


def resolve_session_root_from_context() -> Path | None:
    session_root = current_session_root.get()
    if session_root:
        return Path(session_root)
    return None


def normalize_notebook_path(notebook_path: str) -> Path:
    normalized = Path(notebook_path.replace("\\", "/"))
    if (
        not notebook_path
        or normalized.is_absolute()
        or any(part == ".." for part in normalized.parts)
    ):
        raise ValueError("Notebook 路径无效，必须是当前工作区内的相对路径")

    if normalized.parts and normalized.parts[0] == ".aiasys":
        raise ValueError("不允许编辑 .aiasys 内部 notebook")
    if normalized.suffix.lower() != ".ipynb":
        raise ValueError("仅允许编辑 .ipynb notebook 文件")
    return normalized


@dataclass(frozen=True, slots=True)
class NotebookPathTargets:
    """Notebook 在当前上下文下的读写目标路径。"""

    relative_path: Path
    workspace_file_path: Path
    session_file_path: Path | None
    read_path: Path
    write_path: Path


def _ensure_path_under_root(root: Path, relative_path: Path) -> Path:
    file_path = (root / relative_path).resolve()
    root_resolved = root.resolve()
    try:
        file_path.relative_to(root_resolved)
    except ValueError:
        raise ValueError("Notebook 路径超出当前允许范围。")
    return file_path


def resolve_notebook_targets(
    *,
    workspace_root: Path,
    notebook_path: str,
    session_root: Path | None = None,
) -> NotebookPathTargets:
    relative_path = normalize_notebook_path(notebook_path)
    workspace_file_path = _ensure_path_under_root(workspace_root, relative_path)

    session_file_path: Path | None = None
    if session_root is not None:
        session_file_path = _ensure_path_under_root(session_root, relative_path)

    # session 有副本 → 从 session 读，写到 session
    if session_file_path is not None and session_file_path.exists():
        read_path = session_file_path
        write_path = session_file_path
    # session 没副本但 session_root 已提供 → 从 workspace 读，写到 session
    elif session_file_path is not None:
        read_path = workspace_file_path
        write_path = session_file_path
    # 无 session_root → 纯 workspace 模式（工具层调用）
    else:
        read_path = workspace_file_path
        write_path = workspace_file_path

    return NotebookPathTargets(
        relative_path=relative_path,
        workspace_file_path=workspace_file_path,
        session_file_path=session_file_path,
        read_path=read_path,
        write_path=write_path,
    )


def deep_merge(existing: Any, patch: Any) -> Any:
    if isinstance(existing, dict) and isinstance(patch, dict):
        merged = dict(existing)
        for key, value in patch.items():
            if key in merged:
                merged[key] = deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged
    return patch


def default_notebook() -> dict[str, Any]:
    return {
        "cells": [],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def ensure_notebook_shape(payload: dict[str, Any]) -> dict[str, Any]:
    notebook = dict(payload)
    cells = notebook.get("cells")
    if not isinstance(cells, list):
        notebook["cells"] = []
    metadata = notebook.get("metadata")
    if not isinstance(metadata, dict):
        notebook["metadata"] = {}
    if not isinstance(notebook.get("nbformat"), int):
        notebook["nbformat"] = 4
    if not isinstance(notebook.get("nbformat_minor"), int):
        notebook["nbformat_minor"] = 5

    normalized_cells: list[dict[str, Any]] = []
    for raw_cell in notebook["cells"]:
        if not isinstance(raw_cell, dict):
            continue
        cell = dict(raw_cell)
        if not isinstance(cell.get("cell_type"), str):
            continue
        if "source" not in cell:
            cell["source"] = ""
        if not isinstance(cell.get("metadata"), dict):
            cell["metadata"] = {}
        if cell["cell_type"] == "code":
            if not isinstance(cell.get("outputs"), list):
                cell["outputs"] = []
            if "execution_count" not in cell:
                cell["execution_count"] = None
        else:
            cell.pop("outputs", None)
            cell.pop("execution_count", None)
        if not isinstance(cell.get("id"), str) or not cell["id"].strip():
            cell["id"] = f"cell-{uuid.uuid4().hex[:12]}"
        normalized_cells.append(cell)

    notebook["cells"] = normalized_cells
    return notebook


def load_notebook(file_path: Path) -> dict[str, Any]:
    if not file_path.exists():
        return default_notebook()
    return ensure_notebook_shape(json.loads(file_path.read_text(encoding="utf-8")))


def write_notebook(file_path: Path, notebook: dict[str, Any]) -> str:
    normalized = ensure_notebook_shape(notebook)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    file_path.write_text(serialized, encoding="utf-8")
    return serialized


def source_to_text(source: str | list[str] | Any) -> str:
    if isinstance(source, list):
        return "".join(str(item) for item in source)
    return str(source or "")


def sanitize_notebook_preview_text(text: str) -> str:
    """清理输出预览里的内联 base64，避免污染 Agent 上下文。"""

    return DATA_URL_BASE64_PATTERN.sub("[base64 payload omitted]", text)


def sanitize_notebook_data_payload(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_notebook_preview_text(value)
    if isinstance(value, list):
        return [sanitize_notebook_data_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): sanitize_notebook_data_payload(item) for key, item in value.items()}
    return value


def build_text_preview(text: str, limit: int) -> str:
    preview = sanitize_notebook_preview_text(text).strip().replace("\n", " ")
    if len(preview) > limit:
        return preview[:limit].rstrip() + "..."
    return preview


def sanitize_notebook_for_agent(notebook: dict[str, Any]) -> dict[str, Any]:
    """返回适合 Agent 读取的 notebook 副本，移除大二进制输出。"""

    sanitized = ensure_notebook_shape(deepcopy(notebook))
    for cell in sanitized.get("cells", []):
        outputs = cell.get("outputs")
        if not isinstance(outputs, list):
            continue
        for output in outputs:
            if not isinstance(output, dict):
                continue
            data = output.get("data")
            if not isinstance(data, dict):
                continue
            for mime_type in list(data.keys()):
                if mime_type in NOTEBOOK_BINARY_MIME_TYPES:
                    raw_payload = data.get(mime_type)
                    data[mime_type] = {
                        "omitted": True,
                        "reason": "binary_payload",
                        "mime_type": mime_type,
                        "original_size": len(str(raw_payload or "")),
                    }
                else:
                    data[mime_type] = sanitize_notebook_data_payload(data.get(mime_type))
    return sanitized


def summarize_notebook_output(
    output: dict[str, Any],
    *,
    preview_chars: int = DEFAULT_NOTEBOOK_OUTPUT_PREVIEW_CHARS,
) -> dict[str, Any]:
    output_type = str(output.get("output_type") or "unknown")
    summary: dict[str, Any] = {
        "output_type": output_type,
    }

    if output_type == "stream":
        summary["name"] = output.get("name")
        summary["text_preview"] = build_text_preview(
            source_to_text(output.get("text", "")),
            preview_chars,
        )
        return summary

    if output_type in {"execute_result", "display_data"}:
        data = output.get("data")
        if isinstance(data, dict):
            mime_types = [str(key) for key in data.keys()]
            summary["mime_types"] = mime_types
            summary["has_binary_payload"] = any(
                key in NOTEBOOK_BINARY_MIME_TYPES for key in mime_types
            )
            if "text/plain" in data:
                summary["text_preview"] = build_text_preview(
                    source_to_text(data.get("text/plain")),
                    preview_chars,
                )
            elif "text/html" in data:
                summary["text_preview"] = build_text_preview(
                    source_to_text(data.get("text/html")),
                    preview_chars,
                )
        return summary

    if output_type == "error":
        error_preview = ""
        traceback = output.get("traceback")
        if isinstance(traceback, list) and traceback:
            error_preview = "\n".join(str(item) for item in traceback)
        if not error_preview:
            error_preview = source_to_text(
                output.get("text")
                or output.get("evalue")
                or output.get("ename")
                or "Execution error"
            )
        summary["name"] = output.get("name") or output.get("ename") or "Error"
        summary["text_preview"] = build_text_preview(error_preview, preview_chars)
        return summary

    summary["text_preview"] = build_text_preview(
        source_to_text(output),
        preview_chars,
    )
    return summary


def summarize_cells(
    cells: list[dict[str, Any]],
    *,
    preview_chars: int = DEFAULT_NOTEBOOK_CELL_PREVIEW_CHARS,
    output_preview_chars: int = DEFAULT_NOTEBOOK_OUTPUT_PREVIEW_CHARS,
    include_output_summaries: bool = True,
    start_index: int = 0,
    max_cells: int | None = None,
) -> list[dict[str, Any]]:
    if start_index < 0:
        start_index = 0
    sliced_cells = cells[start_index:]
    if max_cells is not None:
        sliced_cells = sliced_cells[: max(0, max_cells)]

    summaries: list[dict[str, Any]] = []
    for offset, cell in enumerate(sliced_cells):
        outputs = list(cell.get("outputs") or [])
        summary: dict[str, Any] = {
            "index": start_index + offset,
            "cell_id": cell.get("id"),
            "cell_type": cell.get("cell_type"),
            "execution_count": cell.get("execution_count"),
            "output_count": len(outputs),
            "source_preview": build_text_preview(
                source_to_text(cell.get("source", "")),
                preview_chars,
            ),
        }
        if include_output_summaries and outputs:
            summary["output_summaries"] = [
                summarize_notebook_output(
                    output,
                    preview_chars=output_preview_chars,
                )
                for output in outputs[:3]
                if isinstance(output, dict)
            ]
            if len(outputs) > 3:
                summary["output_summary_truncated_count"] = len(outputs) - 3
        summaries.append(summary)
    return summaries


def find_cell_index(
    notebook: dict[str, Any],
    *,
    cell_id: str | None,
    cell_index: int | None,
) -> int | None:
    cells = notebook["cells"]
    if cell_id:
        for index, cell in enumerate(cells):
            if cell.get("id") == cell_id:
                return index
        return None

    if cell_index is None:
        return None
    if cell_index < 0 or cell_index >= len(cells):
        return None
    return cell_index


def apply_patches(source: str, patches: list[dict[str, str]]) -> str:
    """对 source 文本依次应用 find/replace patch。

    每个 patch 只替换第一次匹配，按 patches 列表顺序执行。
    如果某个 patch 的 find 内容在 source 中不存在，抛出 ValueError。
    """
    result = source
    for index, patch in enumerate(patches):
        find = patch.get("find", "")
        replace = patch.get("replace", "")
        if find not in result:
            raise ValueError(
                f"patch[{index}] 的 find 内容未找到: {find[:80]}{'...' if len(find) > 80 else ''}"
            )
        result = result.replace(find, replace, 1)
    return result

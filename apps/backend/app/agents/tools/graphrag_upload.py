"""
GraphRAG 工具 — 文档上传到知识图谱

从 graphrag_tool.py 拆分，包含 _resolve_workspace_file_path 辅助函数和 UploadDocumentsToGraph。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult

from .graphrag_models import GraphUploadExtractionMode, UploadDocumentsToGraphParams
from .knowledge_tool import _resolve_upload_file_path

logger = logging.getLogger(__name__)


def _resolve_workspace_file_path(raw_path: str) -> tuple[str, Path]:
    normalized = str(raw_path or "").strip()
    if not normalized:
        raise ValueError("文件路径不能为空")
    path = _resolve_upload_file_path(normalized)
    if not path.exists():
        raise ValueError(f"`{normalized}` 不存在")
    if not path.is_file():
        raise ValueError(f"`{normalized}` 不是文件")
    return normalized, path


class UploadDocumentsToGraph(AiasysTool):
    """
    把当前工作区文件导入指定知识图谱并构建实体关系。

    适用场景：
    - 用户要求把当前工作区已有 PDF、Markdown、TXT、Office 或表格文件导入图谱
    - 需要由 Agent 在任务过程中增量构建知识图谱
    - 需要批量导入多个文件并返回抽取统计
    """

    name: str = "UploadDocumentsToGraph"
    description: str = """
把当前工作区中的一个或多个文件上传到指定知识图谱，并触发 GraphRAG 实体/关系抽取。

该工具等价于图谱工作台的文档上传构图能力。它读取当前工作区路径下的文件，并调用 GraphRAG 文档导入服务。

参数：
- base_id: 知识图谱 ID
- files: 文件路径列表，支持相对路径、/workspace/...、/global/...
- doc_id_prefix: 可选，批量导入时给 doc_id 加统一前缀
- resolve_entities: 可选，是否实体消歧，默认 true
- extraction_mode: 可选，basic / enhanced / docling。不填时使用系统默认模式。

返回每个文件的实体数、关系数、token 数、解析模式和告警信息。
"""
    params: type[BaseModel] = UploadDocumentsToGraphParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = UploadDocumentsToGraphParams.model_validate(kwargs)
        try:
            base_id = params.base_id.strip()
            if not base_id:
                return ToolResult(content="base_id 不能为空。", is_error=True)

            from .graphrag_tool import get_graphrag_service_for_tools

            service = get_graphrag_service_for_tools(base_id, auto_init_llm=True)
            results: list[dict[str, Any]] = []
            errors: list[str] = []
            for index, raw_path in enumerate(params.files, 1):
                try:
                    display_path, file_path = _resolve_workspace_file_path(raw_path)
                    file_bytes = file_path.read_bytes()
                    doc_id = None
                    if params.doc_id_prefix:
                        safe_prefix = params.doc_id_prefix.strip()
                        if safe_prefix:
                            doc_id = f"{safe_prefix}-{index}"

                    result = await service.add_document_from_file(
                        filename=file_path.name,
                        file_bytes=file_bytes,
                        extraction_mode=params.extraction_mode,
                        doc_id=doc_id,
                        resolve_entities=params.resolve_entities,
                    )
                    results.append(
                        {
                            "path": display_path,
                            **result,
                        }
                    )
                except Exception as exc:
                    logger.error("上传文档到知识图谱失败: %s", exc, exc_info=True)
                    errors.append(f"{raw_path}: {exc}")

            if not results and errors:
                return ToolResult(
                    content="所有文件导入知识图谱失败：\n" + "\n".join(f"- {e}" for e in errors),
                    is_error=True,
                )

            lines = [
                f"图谱: {base_id}",
                f"成功导入 {len(results)} 个文件。",
                "",
            ]
            for index, result in enumerate(results, 1):
                warnings = result.get("warnings") or []
                lines.extend(
                    [
                        f"[{index}] {result.get('path')}",
                        f"  doc_id: {result.get('doc_id')}",
                        f"  文件类型: {result.get('file_type', 'unknown')}",
                        f"  解析模式: {result.get('extraction_mode', 'unknown')}",
                        f"  实体数: {result.get('entity_count', 0)}",
                        f"  关系数: {result.get('relation_count', 0)}",
                        f"  token 数: {result.get('token_count', 0)}",
                        f"  文本长度: {result.get('text_length', 0)}",
                    ]
                )
                if warnings:
                    lines.append("  告警: " + "；".join(str(item) for item in warnings))
                lines.append("")

            if errors:
                lines.append("以下文件导入失败：")
                lines.extend(f"- {error}" for error in errors)

            return ToolResult(
                content="\n".join(lines).strip(),
                is_error=bool(errors),
            )

        except Exception as exc:
            logger.error("上传文档到知识图谱失败: %s", exc, exc_info=True)
            return ToolResult(
                content=f"上传文档到知识图谱失败: {exc}",
                is_error=True,
            )

"""
知识库工具集

允许 Agent 查询用户知识库列表，以及查询指定知识库中的文档内容
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal, Optional, Sequence

from pydantic import BaseModel, Field, field_validator

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.knowledge import SQLiteKBService
from app.knowledge.models import (
    KnowledgeBaseCreate,
    KnowledgeBaseKind,
    KnowledgeBaseUpdate,
    QueryRequest,
    SearchMode,
)
from app.services.history import (
    current_global_workspace,
    current_session_root,
    current_user_id,
    current_workspace,
)
from app.services.task_resource_context import (
    resolve_mounted_knowledge_base_ids,
    resolve_mounted_knowledge_base_summaries,
)

logger = logging.getLogger(__name__)


def _resolve_current_workspace_dir() -> Path | None:
    workspace = current_workspace.get()
    if workspace is None:
        return None
    return Path(workspace)


def _resolve_current_session_root() -> Path | None:
    session_root = current_session_root.get()
    if session_root is None:
        return None
    return Path(session_root)


def _resolve_current_global_workspace_dir() -> Path | None:
    global_workspace = current_global_workspace.get()
    if global_workspace is None:
        return None
    return Path(global_workspace)


def _resolve_workspace_root(scope: Literal["workspace", "global"]) -> Path:
    if scope == "global":
        root = _resolve_current_global_workspace_dir()
        if root is None:
            raise ValueError("当前上下文未设置全局工作区，无法创建到全局工作区")
        return root.resolve()
    root = _resolve_current_workspace_dir()
    if root is None:
        raise ValueError("当前上下文未设置工作区，无法创建知识库")
    return root.resolve()


def _resolve_current_user_id() -> str:
    user_id = current_user_id.get()
    if user_id:
        return user_id

    workspace = _resolve_current_workspace_dir()
    if workspace:
        parts = workspace.resolve().parts
        for index, part in enumerate(parts):
            if part == "workspaces" and index + 1 < len(parts):
                return parts[index + 1]

    logger.warning("无法从上下文获取 user_id，使用默认值")
    return "anonymous"


def _dedupe_ids(values: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _allowed_upload_roots() -> list[Path]:
    roots = [
        _resolve_current_workspace_dir(),
        _resolve_current_session_root(),
        _resolve_current_global_workspace_dir(),
    ]
    return [root.resolve() for root in roots if root is not None]


def _is_under_allowed_roots(path: Path, allowed_roots: Sequence[Path]) -> bool:
    return any(path == root or path.is_relative_to(root) for root in allowed_roots)


def _resolve_upload_file_path(path_str: str) -> Path:
    normalized = str(path_str or "").replace("\\", "/").strip()
    if not normalized:
        raise ValueError("文件路径不能为空")

    allowed_roots = _allowed_upload_roots()
    if not allowed_roots:
        raise ValueError("当前上下文未设置工作区或会话目录，无法读取上传文件")

    if normalized.startswith("/workspace/"):
        workspace = _resolve_current_workspace_dir()
        if workspace is None:
            raise ValueError(f"路径 `{path_str}` 指向当前工作区，但当前上下文未设置工作区")
        relative_part = normalized[len("/workspace/") :]
        candidate = Path(relative_part)
        if ".." in candidate.parts:
            raise ValueError(f"路径 `{path_str}` 包含非法的 .. 逃逸")
        resolved = (workspace / candidate).resolve()
    elif normalized.startswith("/session/"):
        session_root = _resolve_current_session_root()
        if session_root is None:
            raise ValueError(f"路径 `{path_str}` 指向当前会话目录，但当前上下文未设置会话目录")
        relative_part = normalized[len("/session/") :]
        candidate = Path(relative_part)
        if ".." in candidate.parts:
            raise ValueError(f"路径 `{path_str}` 包含非法的 .. 逃逸")
        resolved = (session_root / candidate).resolve()
    elif normalized.startswith("/global/"):
        global_workspace = _resolve_current_global_workspace_dir()
        if global_workspace is None:
            raise ValueError(f"路径 `{path_str}` 指向全局工作区，但当前上下文未设置全局工作区")
        relative_part = normalized[len("/global/") :]
        candidate = Path(relative_part)
        if ".." in candidate.parts:
            raise ValueError(f"路径 `{path_str}` 包含非法的 .. 逃逸")
        resolved = (global_workspace / candidate).resolve()
    else:
        candidate = Path(normalized)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            base = _resolve_current_workspace_dir() or _resolve_current_session_root()
            if base is None:
                raise ValueError("当前上下文未设置工作区或会话目录，无法解析相对路径")
            resolved = (base / candidate).resolve()

    if not _is_under_allowed_roots(resolved, allowed_roots):
        raise ValueError(
            f"路径 `{path_str}` 解析后超出允许范围。"
            "请使用当前工作区、当前会话目录或 /global/ 前缀下的文件。"
        )
    return resolved


def _validate_tool_params(
    params: BaseModel | dict[str, Any],
    model_cls: type[BaseModel],
) -> BaseModel:
    if isinstance(params, model_cls):
        return params
    return model_cls.model_validate(params)


class KnowledgeQueryParams(BaseModel):
    """知识库查询参数"""

    knowledge_base_id: Optional[str] = Field(
        default=None, description="可选。显式指定某一个知识库 ID"
    )
    knowledge_base_ids: list[str] = Field(
        default_factory=list, description="可选。显式指定多个知识库 ID 做聚合检索"
    )
    scope: Literal["mounted", "all"] = Field(
        default="mounted",
        description="未显式指定知识库时，默认只查当前任务挂载知识库；可切换为 all",
    )
    query: str = Field(description="查询内容，描述你想要查找的信息")
    top_k: int = Field(default=5, description="返回的最相似结果数量，默认5条", ge=1, le=20)
    search_mode: Optional[SearchMode] = Field(
        default=None,
        description="可选。检索策略，fulltext / vector / hybrid；为空时使用知识库默认检索策略",
    )


class KnowledgeQueryResult(BaseModel):
    """知识库查询结果"""

    content: str = Field(description="文档片段内容")
    score: float = Field(description="相关度分数(0-1)")
    document_name: str = Field(description="来源文档名称")
    chunk_index: int = Field(description="文档分块索引")


class KnowledgeBaseQuery(AiasysTool):
    """
    知识库查询工具 - 允许 Agent 检索用户知识库中的文档

    当 Agent 需要参考用户上传的文档、资料或历史记录时使用此工具。
    工具基于向量相似度进行语义检索，支持自然语言查询。

    使用场景：
    - 用户询问与上传文档相关的问题
    - 需要基于特定资料进行分析和总结
    - 需要引用历史文档中的信息

    注意：
    - 默认优先查询当前任务已挂载知识库
    - 如果显式提供 knowledge_base_id / knowledge_base_ids，则按显式列表查询
    - 返回的内容是文档片段，可能不是完整文档
    """

    name: str = "KnowledgeBaseQuery"
    description: str = """
查询用户知识库中的文档内容。

当用户的问题与之前上传的文档、资料相关时，使用此工具检索相关信息。
工具会基于语义检索返回最相关的文档片段。

如果用户提到了具体的知识库名称但没有提供 ID，先调用 ListKnowledgeBases 获取知识库 ID，再将 knowledge_base_id 传入本工具进行查询。

参数说明：
- knowledge_base_id: 可选，显式指定某一个知识库 ID。当用户想查询特定知识库时使用。
- knowledge_base_ids: 可选，显式指定多个知识库 ID
- scope: 未显式指定时的默认查询范围，mounted 或 all
- query: 查询内容（自然语言描述你要找的信息）
- top_k: 返回结果数量（默认5条，最多20条）
- search_mode: 可选，指定本次查询策略；为空时使用知识库默认检索策略

返回结果包含：
- content: 文档片段内容
- score: 相关度分数（越接近1越相关）
- knowledge_base: 命中的知识库
- document_name: 来源文档名称
- chunk_index: 文档分块索引
"""
    params: type[BaseModel] = KnowledgeQueryParams
    parameters: dict[str, Any] = KnowledgeQueryParams.model_json_schema()

    def __init__(self):
        """初始化工具"""
        self._kb_service = SQLiteKBService()

    def _resolve_candidate_knowledge_base_ids(
        self,
        params: KnowledgeQueryParams,
        user_id: str,
    ) -> tuple[list[str], str]:
        explicit_ids = _dedupe_ids(
            [
                *(params.knowledge_base_ids or []),
                params.knowledge_base_id or "",
            ]
        )
        if explicit_ids:
            return explicit_ids, "explicit"

        workspace_dir = _resolve_current_workspace_dir()
        mounted_summaries = resolve_mounted_knowledge_base_summaries(
            user_id=user_id,
            workspace_dir=workspace_dir,
        )
        mounted_ids = [str(item.get("id") or "").strip() for item in mounted_summaries]
        mounted_ids = [item for item in mounted_ids if item]
        if mounted_ids:
            return mounted_ids, "mounted"

        all_ids = [
            str(kb.id)
            for kb in self._kb_service.list_knowledge_bases(user_id)
            if getattr(kb, "id", None)
        ]
        if params.scope == "mounted":
            return all_ids, "fallback_all"
        return all_ids, "all"

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = KnowledgeQueryParams.model_validate(kwargs)
        try:
            user_id = _resolve_current_user_id()
            candidate_kb_ids, resolved_scope = self._resolve_candidate_knowledge_base_ids(
                params,
                user_id,
            )
            if not candidate_kb_ids:
                return ToolResult(
                    content="当前没有可查询的知识库。请先挂载任务知识库，或创建知识库后再试。"
                )

            visible_knowledge_bases = self._kb_service.list_knowledge_bases(user_id)
            kb_name_by_id = {
                str(item.id): getattr(item, "name", str(item.id))
                for item in visible_knowledge_bases
                if getattr(item, "id", None)
            }

            aggregated_results: list[dict[str, Any]] = []
            for kb_id in candidate_kb_ids:
                query_request = QueryRequest(
                    query=params.query,
                    top_k=params.top_k,
                    search_mode=params.search_mode,
                )
                query_response = await self._kb_service.query(
                    user_id=user_id, kb_id=kb_id, request=query_request
                )
                for item in query_response.results:
                    aggregated_results.append(
                        {
                            "knowledge_base_id": kb_id,
                            "knowledge_base_name": kb_name_by_id.get(kb_id, kb_id),
                            "content": item.content,
                            "score": round(item.score, 4),
                            "document_name": item.document_name,
                            "chunk_index": item.chunk_index,
                        }
                    )

            aggregated_results.sort(key=lambda item: item["score"], reverse=True)
            aggregated_results = aggregated_results[: params.top_k]

            if not aggregated_results:
                return ToolResult(content="未找到相关内容。")

            output_lines = [f"找到 {len(aggregated_results)} 条相关结果：", ""]

            if resolved_scope == "mounted":
                output_lines.append("查询范围：当前任务已挂载知识库")
                output_lines.append("")
            elif resolved_scope == "fallback_all":
                output_lines.append("查询范围：当前任务未挂载知识库，已回退到用户全部知识库")
                output_lines.append("")
            elif resolved_scope == "all":
                output_lines.append("查询范围：用户全部知识库")
                output_lines.append("")
            else:
                output_lines.append("查询范围：显式指定知识库")
                output_lines.append("")

            for i, r in enumerate(aggregated_results, 1):
                output_lines.extend(
                    [
                        f"[{i}] 知识库：{r['knowledge_base_name']} ({r['knowledge_base_id']})",
                        f"来源：{r['document_name']} (相关度: {r['score']})",
                        f"内容：{r['content'][:500]}{'...' if len(r['content']) > 500 else ''}",
                        "",
                    ]
                )

            return ToolResult(content="\n".join(output_lines))

        except Exception as e:
            logger.error(f"知识库查询失败: {e}", exc_info=True)
            return ToolResult(
                content=f"查询知识库失败: {str(e)}",
                is_error=True,
            )


# 全局实例（单例）
_knowledge_query_tool: Optional[KnowledgeBaseQuery] = None


def get_knowledge_query_tool() -> KnowledgeBaseQuery:
    """
    获取 KnowledgeBaseQuery 单例

    Returns:
        KnowledgeBaseQuery: 工具实例
    """
    global _knowledge_query_tool
    if _knowledge_query_tool is None:
        _knowledge_query_tool = KnowledgeBaseQuery()
    return _knowledge_query_tool


def reset_knowledge_query_tool() -> None:
    """重置工具实例（用于测试）"""
    global _knowledge_query_tool
    _knowledge_query_tool = None


# ==================== 列出知识库工具 ====================


class ListKnowledgeBasesParams(BaseModel):
    """列出知识库参数"""

    scope: Literal["mounted", "all"] = Field(
        default="mounted",
        description="默认只列出当前任务挂载知识库；如需查看全部可切换为 all",
    )


class ListKnowledgeBases(AiasysTool):
    """
    列出知识库工具 - 获取当前用户的所有知识库列表

    当需要查看用户有哪些知识库、获取知识库ID时使用此工具。

    使用场景：
    - 用户想查询知识库但不知道知识库ID
    - 需要展示用户所有的知识库供选择
    - 查看知识库的基本信息（名称、描述、文档数量）

    返回结果包含：
    - 知识库ID
    - 知识库名称
    - 描述
    - 文档数量
    - 创建时间
    """

    name: str = "ListKnowledgeBases"
    description: str = """
列出知识库。

默认优先列出当前任务已挂载的知识库；如果没有挂载，或显式指定 scope=all，再列出当前用户的全部知识库。

返回结果包含每个知识库的：
- id: 知识库唯一标识（查询时需要用到）
- name: 知识库名称
- description: 知识库描述
- document_count: 文档数量
- created_at: 创建时间

使用示例：
用户问："我想查询我的知识库"
→ 先调用 ListKnowledgeBases 获取列表
→ 展示给用户选择
→ 用户选择后使用 KnowledgeBaseQuery 查询具体内容
"""
    params: type[BaseModel] = ListKnowledgeBasesParams
    parameters: dict[str, Any] = ListKnowledgeBasesParams.model_json_schema()

    def __init__(self):
        """初始化工具"""
        self._kb_service = SQLiteKBService()

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = ListKnowledgeBasesParams.model_validate(kwargs)
        try:
            user_id = _resolve_current_user_id()
            all_knowledge_bases = self._kb_service.list_knowledge_bases(user_id)
            all_by_id = {
                str(item.id): item for item in all_knowledge_bases if getattr(item, "id", None)
            }
            mounted_ids = resolve_mounted_knowledge_base_ids(
                workspace_dir=_resolve_current_workspace_dir()
            )
            mounted_knowledge_bases = [
                all_by_id[kb_id] for kb_id in mounted_ids if kb_id in all_by_id
            ]

            if params.scope == "mounted":
                knowledge_bases = mounted_knowledge_bases or all_knowledge_bases
                resolved_scope = "mounted" if mounted_knowledge_bases else "fallback_all"
            else:
                knowledge_bases = all_knowledge_bases
                resolved_scope = "all"

            if not knowledge_bases:
                return ToolResult(content="您还没有创建知识库。可以通过知识库管理页面创建一个。")

            output_lines = [f"找到 {len(knowledge_bases)} 个知识库：", ""]
            if resolved_scope == "mounted":
                output_lines.append("列出范围：当前任务已挂载知识库")
                output_lines.append("")
            elif resolved_scope == "fallback_all":
                output_lines.append("列出范围：当前任务未挂载知识库，已回退到用户全部知识库")
                output_lines.append("")
            else:
                output_lines.append("列出范围：用户全部知识库")
                output_lines.append("")

            for i, kb in enumerate(knowledge_bases, 1):
                output_lines.extend(
                    [
                        f"[{i}] {kb.name}",
                        f"    ID: {kb.id}",
                        f"    描述: {kb.description or '无描述'}",
                        f"    文档数: {kb.document_count or 0}",
                        f"    创建时间: {kb.created_at}",
                        "",
                    ]
                )

            return ToolResult(content="\n".join(output_lines))

        except Exception as e:
            logger.error(f"列出知识库失败: {e}", exc_info=True)
            return ToolResult(
                content=f"获取知识库列表失败: {str(e)}",
                is_error=True,
            )


# 全局实例（单例）
_list_knowledge_bases_tool: Optional[ListKnowledgeBases] = None


def get_list_knowledge_bases_tool() -> ListKnowledgeBases:
    """获取 ListKnowledgeBases 单例"""
    global _list_knowledge_bases_tool
    if _list_knowledge_bases_tool is None:
        _list_knowledge_bases_tool = ListKnowledgeBases()
    return _list_knowledge_bases_tool


def reset_list_knowledge_bases_tool() -> None:
    """重置工具实例（用于测试）"""
    global _list_knowledge_bases_tool
    _list_knowledge_bases_tool = None


# ==================== 管理知识库工具 ====================


class CreateKnowledgeBaseParams(BaseModel):
    """创建知识库参数"""

    name: str = Field(
        description="知识库名称",
        min_length=1,
        max_length=100,
    )
    description: Optional[str] = Field(
        default=None,
        description="知识库描述",
        max_length=500,
    )
    scope: Literal["workspace", "global"] = Field(
        default="workspace",
        description="创建位置：workspace（当前工作区）或 global（全局工作区），默认 workspace",
    )
    kind: KnowledgeBaseKind = Field(
        default=KnowledgeBaseKind.DOCUMENT,
        description="知识库类型，默认 document",
    )
    embedding_model: Optional[str] = Field(
        default=None,
        description="可选。指定 embedding 模型；为空时使用当前用户默认 embedding 模型",
    )
    chunk_size: Optional[int] = Field(
        default=512,
        description="文档切片大小，默认 512",
        ge=1,
    )
    chunk_overlap: Optional[int] = Field(
        default=50,
        description="文档切片重叠大小，默认 50",
        ge=0,
    )
    default_search_mode: SearchMode = Field(
        default=SearchMode.FULLTEXT,
        description="默认检索策略，fulltext / vector / hybrid",
    )


class CreateKnowledgeBase(AiasysTool):
    """创建知识库。"""

    name: str = "CreateKnowledgeBase"
    description: str = """
创建知识库。

当用户希望新增一个用于存放文档、资料或项目知识的知识库时使用。
默认创建在当前工作区 .aiasys/knowledge/ 下，scope=global 时创建到全局工作区。
创建后会返回知识库 ID，后续上传文档、查询或删除都需要使用这个 ID。

参数说明：
- name: 知识库名称
- description: 可选，知识库描述
- scope: 可选，创建位置，workspace（默认，当前工作区）或 global（全局工作区）
- kind: 可选，知识库类型，默认 document
- embedding_model: 可选，指定 embedding 模型；为空时使用用户默认 embedding 模型
- chunk_size: 可选，文档切片大小
- chunk_overlap: 可选，文档切片重叠大小
- default_search_mode: 可选，默认检索策略，fulltext / vector / hybrid
"""
    params: type[BaseModel] = CreateKnowledgeBaseParams
    parameters: dict[str, Any] = CreateKnowledgeBaseParams.model_json_schema()

    def __init__(self):
        self._kb_service = SQLiteKBService()

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = CreateKnowledgeBaseParams.model_validate(kwargs)
        try:
            user_id = _resolve_current_user_id()
            workspace_root = _resolve_workspace_root(params.scope)
            # 从路径提取 workspace_id（全局工作区时为 None）
            workspace_id_val: str | None = None
            if params.scope == "workspace":
                workspace_id_val = workspace_root.name
            request = KnowledgeBaseCreate(
                name=params.name,
                description=params.description,
                kind=params.kind,
                embedding_model=params.embedding_model,
                chunk_size=params.chunk_size,
                chunk_overlap=params.chunk_overlap,
                default_search_mode=params.default_search_mode,
            )
            kb = self._kb_service.create_knowledge_base(
                user_id,
                request,
                workspace_root=workspace_root,
                scope=params.scope,
                workspace_id=workspace_id_val,
            )
            scope_label = "全局工作区" if params.scope == "global" else "当前工作区"
            return ToolResult(
                content="\n".join(
                    [
                        f"知识库创建成功：{kb.name}",
                        f"ID: {kb.id}",
                        f"位置: {scope_label}",
                        f"类型: {kb.kind}",
                        f"Embedding 模型: {kb.embedding_model}",
                        f"切片配置: chunk_size={kb.chunk_size}, chunk_overlap={kb.chunk_overlap}",
                        f"默认检索策略: {kb.default_search_mode}",
                    ]
                ),
                artifacts=[{"knowledge_base": kb.model_dump(mode="json")}],
            )
        except Exception as e:
            logger.error(f"创建知识库失败: {e}", exc_info=True)
            return ToolResult(
                content=f"创建知识库失败: {str(e)}",
                is_error=True,
            )


class UploadDocumentsToKnowledgeBaseParams(BaseModel):
    """上传文档到知识库参数"""

    base_id: str = Field(description="目标知识库 ID")
    files: list[str] = Field(
        description=(
            "要上传的文件路径列表。相对路径基于当前工作区。"
            "也支持 /workspace/、/session/、/global/ 前缀。"
        ),
        min_length=1,
    )
    extraction_mode: Optional[str] = Field(
        default=None,
        description="可选。文档解析模式，保持为空时由后端自动选择",
    )
    embedding_model: Optional[str] = Field(
        default=None,
        description="可选。空知识库可指定 embedding 模型；已有文档时不能直接切换模型",
    )
    chunk_size: Optional[int] = Field(
        default=None,
        description="可选。本次导入使用的文档切片大小，并写回知识库默认值",
        ge=64,
        le=8192,
    )
    chunk_overlap: Optional[int] = Field(
        default=None,
        description="可选。本次导入使用的文档切片重叠大小，并写回知识库默认值",
        ge=0,
        le=4096,
    )
    search_mode: Optional[SearchMode] = Field(
        default=None,
        description="可选。知识库默认检索策略，fulltext / vector / hybrid",
    )

    @field_validator("files", mode="before")
    @classmethod
    def _coerce_files(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [value]
        return value


class UploadDocumentsToKnowledgeBase(AiasysTool):
    """上传一个或多个当前工作区文件到知识库。"""

    name: str = "UploadDocumentsToKnowledgeBase"
    description: str = """
上传文档到指定知识库。

当用户希望把当前工作区、当前会话目录或全局工作区中的文件加入知识库时使用。
files 参数可以传一个路径字符串，也可以传多个路径组成的列表。

参数说明：
- base_id: 目标知识库 ID。若用户只给出知识库名称，先调用 ListKnowledgeBases 获取 ID。
- files: 文件路径列表，支持相对路径、/workspace/、/session/、/global/ 前缀。
- extraction_mode: 可选，文档解析模式；为空时由后端自动选择。
- embedding_model: 可选，空知识库可指定 embedding 模型；已有文档时不能直接切换模型。
- chunk_size / chunk_overlap: 可选，本次导入使用的分块配置，并写回知识库默认值。
- search_mode: 可选，写回知识库默认检索策略。
"""
    params: type[BaseModel] = UploadDocumentsToKnowledgeBaseParams
    parameters: dict[str, Any] = UploadDocumentsToKnowledgeBaseParams.model_json_schema()

    def __init__(self):
        self._kb_service = SQLiteKBService()

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = UploadDocumentsToKnowledgeBaseParams.model_validate(kwargs)
        try:
            user_id = _resolve_current_user_id()
            kb = self._kb_service.get_knowledge_base(user_id, params.base_id)
            if not kb:
                return ToolResult(
                    content=f"知识库不存在：{params.base_id}",
                    is_error=True,
                )

            upload_results: list[dict[str, Any]] = []
            failed_items: list[str] = []

            for file_ref in _dedupe_ids(params.files):
                try:
                    file_path = _resolve_upload_file_path(file_ref)
                    if not file_path.exists():
                        raise FileNotFoundError(f"`{file_ref}` 不存在")
                    if not file_path.is_file():
                        raise ValueError(f"`{file_ref}` 不是文件")
                    file_bytes = file_path.read_bytes()
                    result = await self._kb_service.upload_document(
                        user_id=user_id,
                        kb_id=params.base_id,
                        filename=file_path.name,
                        file_bytes=file_bytes,
                        extraction_mode=params.extraction_mode,
                        embedding_model=params.embedding_model,
                        chunk_size=params.chunk_size,
                        chunk_overlap=params.chunk_overlap,
                        search_mode=params.search_mode,
                    )
                    upload_results.append(result.model_dump(mode="json"))
                    if not result.success:
                        failed_items.append(f"{file_ref}: {result.message}")
                except Exception as exc:
                    logger.warning("上传知识库文档失败: file=%s", file_ref, exc_info=True)
                    failed_items.append(f"{file_ref}: {exc}")
                    upload_results.append(
                        {
                            "success": False,
                            "filename": Path(str(file_ref)).name,
                            "message": str(exc),
                            "document_id": None,
                            "chunk_count": None,
                            "extraction_mode": params.extraction_mode,
                        }
                    )

            successful_results = [item for item in upload_results if item.get("success")]
            lines = [
                f"知识库：{kb.name} ({kb.id})",
                f"上传成功：{len(successful_results)} 个",
                f"上传失败：{len(failed_items)} 个",
            ]
            if successful_results:
                lines.append("")
                lines.append("成功文档：")
                for item in successful_results:
                    lines.append(
                        f"- {item.get('filename')} (document_id={item.get('document_id')}, chunks={item.get('chunk_count')})"
                    )
            if failed_items:
                lines.append("")
                lines.append("失败项：")
                for item in failed_items:
                    lines.append(f"- {item}")

            return ToolResult(
                content="\n".join(lines),
                is_error=bool(failed_items),
                artifacts=[
                    {
                        "knowledge_base_id": params.base_id,
                        "uploads": upload_results,
                    }
                ],
            )
        except Exception as e:
            logger.error(f"上传知识库文档失败: {e}", exc_info=True)
            return ToolResult(
                content=f"上传知识库文档失败: {str(e)}",
                is_error=True,
            )


class DeleteDocumentsFromKnowledgeBaseParams(BaseModel):
    """从知识库删除文档参数"""

    base_id: str = Field(description="知识库 ID")
    doc_ids: list[str] = Field(description="要删除的文档 ID 列表", min_length=1)

    @field_validator("doc_ids", mode="before")
    @classmethod
    def _coerce_doc_ids(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [value]
        return value


class DeleteDocumentsFromKnowledgeBase(AiasysTool):
    """从知识库中删除一个或多个文档。"""

    name: str = "DeleteDocumentsFromKnowledgeBase"
    description: str = """
从指定知识库删除文档。

当用户要求移除知识库中的一个或多个文档时使用。
如果用户只给出文档名称，需要先通过知识库管理界面或其他可用信息确认 document_id。

参数说明：
- base_id: 知识库 ID。
- doc_ids: 文档 ID 列表，也可以传单个文档 ID 字符串。
"""
    params: type[BaseModel] = DeleteDocumentsFromKnowledgeBaseParams
    parameters: dict[str, Any] = DeleteDocumentsFromKnowledgeBaseParams.model_json_schema()

    def __init__(self):
        self._kb_service = SQLiteKBService()

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = DeleteDocumentsFromKnowledgeBaseParams.model_validate(kwargs)
        try:
            user_id = _resolve_current_user_id()
            kb = self._kb_service.get_knowledge_base(user_id, params.base_id)
            if not kb:
                return ToolResult(
                    content=f"知识库不存在：{params.base_id}",
                    is_error=True,
                )

            deleted_ids: list[str] = []
            failed_ids: list[str] = []
            for doc_id in _dedupe_ids(params.doc_ids):
                if self._kb_service.delete_document(user_id, params.base_id, doc_id):
                    deleted_ids.append(doc_id)
                else:
                    failed_ids.append(doc_id)

            lines = [
                f"知识库：{kb.name} ({kb.id})",
                f"已删除文档：{len(deleted_ids)} 个",
                f"未删除文档：{len(failed_ids)} 个",
            ]
            if deleted_ids:
                lines.append("")
                lines.append("已删除：")
                lines.extend(f"- {doc_id}" for doc_id in deleted_ids)
            if failed_ids:
                lines.append("")
                lines.append("未删除，可能是文档不存在或不属于该知识库：")
                lines.extend(f"- {doc_id}" for doc_id in failed_ids)

            return ToolResult(
                content="\n".join(lines),
                is_error=bool(failed_ids),
                artifacts=[
                    {
                        "knowledge_base_id": params.base_id,
                        "deleted_document_ids": deleted_ids,
                        "failed_document_ids": failed_ids,
                    }
                ],
            )
        except Exception as e:
            logger.error(f"删除知识库文档失败: {e}", exc_info=True)
            return ToolResult(
                content=f"删除知识库文档失败: {str(e)}",
                is_error=True,
            )


class DeleteKnowledgeBaseParams(BaseModel):
    """删除知识库参数"""

    base_id: str = Field(description="要删除的知识库 ID")


class DeleteKnowledgeBase(AiasysTool):
    """删除当前用户的知识库。"""

    name: str = "DeleteKnowledgeBase"
    description: str = """
删除知识库。

当用户明确要求删除某个知识库时使用。删除知识库会同时删除该知识库下的文档和分块数据。
如果用户只给出知识库名称，先调用 ListKnowledgeBases 获取 ID 并向用户确认。

参数说明：
- base_id: 要删除的知识库 ID。
"""
    params: type[BaseModel] = DeleteKnowledgeBaseParams
    parameters: dict[str, Any] = DeleteKnowledgeBaseParams.model_json_schema()

    def __init__(self):
        self._kb_service = SQLiteKBService()

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = DeleteKnowledgeBaseParams.model_validate(kwargs)
        try:
            user_id = _resolve_current_user_id()
            success = self._kb_service.delete_knowledge_base(user_id, params.base_id)
            if not success:
                return ToolResult(
                    content=f"知识库不存在：{params.base_id}",
                    is_error=True,
                )
            return ToolResult(
                content=f"知识库已删除：{params.base_id}",
                artifacts=[
                    {
                        "knowledge_base_id": params.base_id,
                        "deleted": True,
                    }
                ],
            )
        except Exception as e:
            logger.error(f"删除知识库失败: {e}", exc_info=True)
            return ToolResult(
                content=f"删除知识库失败: {str(e)}",
                is_error=True,
            )


class ListKnowledgeBaseDocumentsParams(BaseModel):
    """列出知识库文档参数"""

    base_id: str = Field(description="知识库 ID")
    limit: int = Field(
        default=100,
        description="返回文档数量上限，默认 100",
        ge=1,
        le=500,
    )
    skip: int = Field(
        default=0,
        description="跳过的文档数量，默认 0",
        ge=0,
    )
    status: Optional[str] = Field(
        default=None,
        description="可选。按文档状态过滤，例如 completed、failed、processing",
    )


class ListKnowledgeBaseDocuments(AiasysTool):
    """列出指定知识库中的文档。"""

    name: str = "ListKnowledgeBaseDocuments"
    description: str = """
列出知识库中的文档。

当用户想查看知识库里有哪些文档，或删除文档前需要确认 document_id 时使用。

参数说明：
- base_id: 知识库 ID。
- limit: 返回文档数量上限，默认 100，最多 500。
- skip: 跳过的文档数量，默认 0。
- status: 可选，按文档状态过滤，例如 completed、failed、processing。
"""
    params: type[BaseModel] = ListKnowledgeBaseDocumentsParams
    parameters: dict[str, Any] = ListKnowledgeBaseDocumentsParams.model_json_schema()

    def __init__(self):
        self._kb_service = SQLiteKBService()

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = ListKnowledgeBaseDocumentsParams.model_validate(kwargs)
        try:
            user_id = _resolve_current_user_id()
            kb = self._kb_service.get_knowledge_base(user_id, params.base_id)
            if not kb:
                return ToolResult(
                    content=f"知识库不存在：{params.base_id}",
                    is_error=True,
                )

            documents = self._kb_service.list_documents(
                user_id=user_id,
                kb_id=params.base_id,
                skip=params.skip,
                limit=params.limit,
            )
            status_filter = str(params.status or "").strip()
            if status_filter:
                documents = [
                    item
                    for item in documents
                    if str(getattr(item, "status", "")).lower() == status_filter.lower()
                ]

            if not documents:
                scope_text = f"状态为 {status_filter} 的文档" if status_filter else "文档"
                return ToolResult(
                    content=f"知识库 {kb.name} ({kb.id}) 暂无{scope_text}。",
                    artifacts=[
                        {
                            "knowledge_base_id": params.base_id,
                            "documents": [],
                        }
                    ],
                )

            lines = [
                f"知识库：{kb.name} ({kb.id})",
                f"文档数量：{len(documents)}",
                "",
            ]
            for index, document in enumerate(documents, 1):
                lines.extend(
                    [
                        f"[{index}] {document.filename}",
                        f"    document_id: {document.id}",
                        f"    类型: {document.file_type}",
                        f"    状态: {document.status}",
                        f"    分块数: {document.chunk_count}",
                        f"    大小: {document.file_size} bytes",
                        f"    创建时间: {document.created_at}",
                        "",
                    ]
                )

            return ToolResult(
                content="\n".join(lines).strip(),
                artifacts=[
                    {
                        "knowledge_base_id": params.base_id,
                        "documents": [
                            (
                                item.model_dump(mode="json")
                                if hasattr(item, "model_dump")
                                else dict(item)
                            )
                            for item in documents
                        ],
                    }
                ],
            )
        except Exception as e:
            logger.error(f"列出知识库文档失败: {e}", exc_info=True)
            return ToolResult(
                content=f"列出知识库文档失败: {str(e)}",
                is_error=True,
            )


class UpdateKnowledgeBaseParams(BaseModel):
    """更新知识库参数"""

    base_id: str = Field(description="知识库 ID")
    name: Optional[str] = Field(
        default=None, description="新的知识库名称", min_length=1, max_length=100
    )
    description: Optional[str] = Field(default=None, description="新的知识库描述", max_length=500)
    embedding_model: Optional[str] = Field(
        default=None,
        description="新的 embedding 模型。已有文档的知识库不能直接切换模型",
    )
    chunk_size: Optional[int] = Field(
        default=None,
        description="新的文档切片大小。已有文档的知识库不能直接修改",
        ge=64,
        le=8192,
    )
    chunk_overlap: Optional[int] = Field(
        default=None,
        description="新的文档切片重叠大小。已有文档的知识库不能直接修改",
        ge=0,
        le=4096,
    )
    default_search_mode: Optional[SearchMode] = Field(
        default=None,
        description="新的默认检索策略，fulltext / vector / hybrid",
    )
    default_extraction_mode: Optional[str] = Field(
        default=None,
        description="新的默认文档解析模式；传空字符串可清除默认值",
    )
    extraction_mode_mapping: Optional[dict[str, str]] = Field(
        default=None,
        description="按文件扩展名配置解析模式，例如 {'.pdf': 'docling'}",
    )


class UpdateKnowledgeBase(AiasysTool):
    """更新当前用户的知识库配置。"""

    name: str = "UpdateKnowledgeBase"
    description: str = """
更新知识库信息和默认配置。

当用户希望修改知识库名称、描述、默认检索策略、默认解析模式或解析映射时使用。
已有文档的知识库不能直接切换 embedding 模型或分块配置，服务层会返回明确错误。

参数说明：
- base_id: 知识库 ID。
- name / description: 新的名称和描述。
- embedding_model: 新的 embedding 模型。
- chunk_size / chunk_overlap: 新的分块配置。
- default_search_mode: 默认检索策略，fulltext / vector / hybrid。
- default_extraction_mode: 默认解析模式。
- extraction_mode_mapping: 文件扩展名到解析模式的映射。
"""
    params: type[BaseModel] = UpdateKnowledgeBaseParams
    parameters: dict[str, Any] = UpdateKnowledgeBaseParams.model_json_schema()

    def __init__(self):
        self._kb_service = SQLiteKBService()

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = UpdateKnowledgeBaseParams.model_validate(kwargs)
        try:
            user_id = _resolve_current_user_id()
            update_data = params.model_dump(
                exclude={"base_id"},
                exclude_unset=True,
            )
            if not update_data:
                return ToolResult(
                    content="没有提供需要更新的知识库字段。",
                    is_error=True,
                )

            request = KnowledgeBaseUpdate.model_validate(update_data)
            kb = self._kb_service.update_knowledge_base(
                user_id,
                params.base_id,
                request,
            )
            if not kb:
                return ToolResult(
                    content=f"知识库不存在：{params.base_id}",
                    is_error=True,
                )

            return ToolResult(
                content="\n".join(
                    [
                        f"知识库已更新：{kb.name}",
                        f"ID: {kb.id}",
                        f"描述: {kb.description or '无描述'}",
                        f"Embedding 模型: {kb.embedding_model or '未配置'}",
                        f"切片配置: chunk_size={kb.chunk_size}, chunk_overlap={kb.chunk_overlap}",
                        f"默认检索策略: {kb.default_search_mode}",
                        f"默认解析模式: {kb.default_extraction_mode or '未配置'}",
                        f"需要重建索引: {'是' if kb.requires_reindex else '否'}",
                    ]
                ),
                artifacts=[{"knowledge_base": kb.model_dump(mode="json")}],
            )
        except Exception as e:
            logger.error(f"更新知识库失败: {e}", exc_info=True)
            return ToolResult(
                content=f"更新知识库失败: {str(e)}",
                is_error=True,
            )


_create_knowledge_base_tool: Optional[CreateKnowledgeBase] = None
_upload_documents_to_knowledge_base_tool: Optional[UploadDocumentsToKnowledgeBase] = None
_delete_documents_from_knowledge_base_tool: Optional[DeleteDocumentsFromKnowledgeBase] = None
_delete_knowledge_base_tool: Optional[DeleteKnowledgeBase] = None
_list_knowledge_base_documents_tool: Optional[ListKnowledgeBaseDocuments] = None
_update_knowledge_base_tool: Optional[UpdateKnowledgeBase] = None


def get_create_knowledge_base_tool() -> CreateKnowledgeBase:
    """获取 CreateKnowledgeBase 单例"""
    global _create_knowledge_base_tool
    if _create_knowledge_base_tool is None:
        _create_knowledge_base_tool = CreateKnowledgeBase()
    return _create_knowledge_base_tool


def get_upload_documents_to_knowledge_base_tool() -> UploadDocumentsToKnowledgeBase:
    """获取 UploadDocumentsToKnowledgeBase 单例"""
    global _upload_documents_to_knowledge_base_tool
    if _upload_documents_to_knowledge_base_tool is None:
        _upload_documents_to_knowledge_base_tool = UploadDocumentsToKnowledgeBase()
    return _upload_documents_to_knowledge_base_tool


def get_delete_documents_from_knowledge_base_tool() -> DeleteDocumentsFromKnowledgeBase:
    """获取 DeleteDocumentsFromKnowledgeBase 单例"""
    global _delete_documents_from_knowledge_base_tool
    if _delete_documents_from_knowledge_base_tool is None:
        _delete_documents_from_knowledge_base_tool = DeleteDocumentsFromKnowledgeBase()
    return _delete_documents_from_knowledge_base_tool


def get_delete_knowledge_base_tool() -> DeleteKnowledgeBase:
    """获取 DeleteKnowledgeBase 单例"""
    global _delete_knowledge_base_tool
    if _delete_knowledge_base_tool is None:
        _delete_knowledge_base_tool = DeleteKnowledgeBase()
    return _delete_knowledge_base_tool


def get_list_knowledge_base_documents_tool() -> ListKnowledgeBaseDocuments:
    """获取 ListKnowledgeBaseDocuments 单例"""
    global _list_knowledge_base_documents_tool
    if _list_knowledge_base_documents_tool is None:
        _list_knowledge_base_documents_tool = ListKnowledgeBaseDocuments()
    return _list_knowledge_base_documents_tool


def get_update_knowledge_base_tool() -> UpdateKnowledgeBase:
    """获取 UpdateKnowledgeBase 单例"""
    global _update_knowledge_base_tool
    if _update_knowledge_base_tool is None:
        _update_knowledge_base_tool = UpdateKnowledgeBase()
    return _update_knowledge_base_tool

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CanvasNode(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: Literal["text", "file", "link", "group"] = "text"
    x: float = 0
    y: float = 0
    width: float = 250
    height: float = 120
    text: str | None = Field(default=None, description="文本节点内容")
    file: str | None = Field(default=None, description="file 节点引用的文件路径")
    subpath: str | None = Field(default=None, description="file 节点引用的内部位置")
    url: str | None = Field(default=None, description="link 节点 URL")
    label: str | None = Field(default=None, description="group 节点标签")
    color: str | None = Field(default=None, description="节点颜色 (1-6 或 CSS 色值)")
    background: str | None = Field(default=None, description="节点背景图片")
    backgroundStyle: Literal["cover", "ratio", "repeat"] | None = Field(default=None)
    custom: dict[str, Any] | None = Field(
        default=None,
        description="JSON Canvas 扩展字段。AIASys 透传但不解释该字段。",
    )


class CanvasEdge(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    fromNode: str
    fromSide: Literal["top", "right", "bottom", "left"] | None = Field(default=None)
    fromEnd: Literal["none", "arrow"] | None = Field(default=None)
    toNode: str
    toSide: Literal["top", "right", "bottom", "left"] | None = Field(default=None)
    toEnd: Literal["none", "arrow"] | None = Field(default="arrow")
    color: str | None = Field(default=None)
    label: str | None = Field(default=None)
    custom: dict[str, Any] | None = Field(
        default=None,
        description="JSON Canvas 扩展字段。AIASys 透传但不解释该字段。",
    )


class CanvasFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    nodes: list[CanvasNode] = Field(default_factory=list)
    edges: list[CanvasEdge] = Field(default_factory=list)


class CanvasReadResponse(BaseModel):
    workspace_id: str
    relative_path: str
    canvas: CanvasFile
    debounce_ms: int = Field(default=800, description="前端自动保存防抖间隔（毫秒）")


class CanvasWriteRequest(BaseModel):
    canvas: CanvasFile


class CanvasNodeCreateRequest(BaseModel):
    node: CanvasNode


class CanvasNodeUpdateRequest(BaseModel):
    node: CanvasNode


class CanvasEdgeCreateRequest(BaseModel):
    edge: CanvasEdge


class CanvasEdgeUpdateRequest(BaseModel):
    edge: CanvasEdge


class CanvasBatchOperation(BaseModel):
    type: Literal[
        "add_node",
        "update_node",
        "remove_node",
        "add_edge",
        "update_edge",
        "remove_edge",
    ]
    node: CanvasNode | None = None
    edge: CanvasEdge | None = None
    node_id: str | None = None
    edge_id: str | None = None


class CanvasBatchRequest(BaseModel):
    operations: list[CanvasBatchOperation]

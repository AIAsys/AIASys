"""实体模型"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Entity:
    """知识图谱实体"""

    name: str  # 实体名称
    entity_type: str  # 实体类型
    description: str  # 实体描述
    source_id: str = ""  # 来源文档ID
    entity_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    embedding: Optional[list] = None  # 向量嵌入
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "entity_type": self.entity_type,
            "description": self.description,
            "source_id": self.source_id,
            "embedding": self.embedding,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Entity":
        return cls(
            entity_id=data.get("entity_id", str(uuid.uuid4())),
            name=data["name"],
            entity_type=data["entity_type"],
            description=data["description"],
            source_id=data.get("source_id", ""),
            embedding=data.get("embedding"),
            metadata=data.get("metadata", {}),
        )

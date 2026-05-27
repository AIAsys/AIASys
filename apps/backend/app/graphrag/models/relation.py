"""关系模型"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Relation:
    """知识图谱关系"""

    source_entity: str  # 源实体名称
    target_entity: str  # 目标实体名称
    description: str  # 关系描述
    strength: float = 1.0  # 关系强度 (1-10)
    source_id: str = ""  # 来源文档ID
    relation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    embedding: Optional[list] = None  # 向量嵌入
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "source_entity": self.source_entity,
            "target_entity": self.target_entity,
            "description": self.description,
            "strength": self.strength,
            "source_id": self.source_id,
            "embedding": self.embedding,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Relation":
        return cls(
            relation_id=data.get("relation_id", str(uuid.uuid4())),
            source_entity=data["source_entity"],
            target_entity=data["target_entity"],
            description=data["description"],
            strength=data.get("strength", 1.0),
            source_id=data.get("source_id", ""),
            embedding=data.get("embedding"),
            metadata=data.get("metadata", {}),
        )

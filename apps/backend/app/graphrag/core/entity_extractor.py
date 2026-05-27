"""
实体关系抽取器
使用 LLM 从文本中抽取实体和关系
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..models.entity import Entity
from ..models.relation import Relation
from ..prompts.extraction import (
    COMPLETION_DELIMITER,
    CONTINUE_PROMPT,
    DEFAULT_ENTITY_TYPES,
    GRAPH_EXTRACTION_PROMPT,
    LOOP_PROMPT,
    RECORD_DELIMITER,
    TUPLE_DELIMITER,
)
from ..utils.cache import get_cache_manager


@dataclass
class ExtractionResult:
    """抽取结果"""

    entities: List[Entity]
    relations: List[Relation]
    token_count: int


class EntityExtractor:
    """实体关系抽取器"""

    def __init__(
        self,
        llm_client,
        entity_types: Optional[List[str]] = None,
        max_gleanings: int = 3,
        language: str = "Chinese",
    ):
        self.llm_client = llm_client
        self.entity_types = entity_types or DEFAULT_ENTITY_TYPES
        self.max_gleanings = max_gleanings
        self.language = language
        self.cache = get_cache_manager()

    @staticmethod
    def _normalize_text(value: str) -> str:
        """清理 LLM 结果里常见的包裹引号。"""
        normalized = value.strip()
        if not normalized:
            return ""

        quote_pairs = [
            ('"', '"'),
            ("'", "'"),
            ("`", "`"),
            ("“", "”"),
            ("‘", "’"),
        ]

        changed = True
        while changed and normalized:
            changed = False
            for start, end in quote_pairs:
                if (
                    normalized.startswith(start)
                    and normalized.endswith(end)
                    and len(normalized) >= len(start) + len(end)
                ):
                    candidate = normalized[len(start) : len(normalized) - len(end)].strip()
                    if candidate == normalized:
                        continue
                    normalized = candidate
                    changed = True
                    break

        return normalized

    async def extract(self, text: str, doc_id: str = "") -> ExtractionResult:
        """
        从文本中抽取实体和关系

        Args:
            text: 输入文本
            doc_id: 文档ID（用于溯源）

        Returns:
            ExtractionResult 包含实体和关系列表
        """
        # 检查缓存
        cache_key = f"{doc_id}:{hash(text)}"
        cached = self.cache.get(f"extraction:{cache_key}")
        if cached:
            entities = [Entity.from_dict(e) for e in cached["entities"]]
            relations = [Relation.from_dict(r) for r in cached["relations"]]
            return ExtractionResult(entities, relations, cached.get("token_count", 0))

        # 构建 Prompt
        prompt = GRAPH_EXTRACTION_PROMPT.format(
            entity_types=",".join(self.entity_types),
            input_text=text,
            tuple_delimiter=TUPLE_DELIMITER,
            record_delimiter=RECORD_DELIMITER,
            completion_delimiter=COMPLETION_DELIMITER,
        )

        # 调用 LLM 进行抽取
        results = ""
        history = []
        token_count = 0

        # 第一次抽取
        response = await self._call_llm(prompt)
        results += response
        token_count += len(prompt) + len(response)
        history.append({"role": "user", "content": CONTINUE_PROMPT})

        # 多轮抽取（gleaning）
        for i in range(self.max_gleanings):
            # 继续抽取
            history.append({"role": "user", "content": CONTINUE_PROMPT})
            response = await self._call_llm_with_history(prompt, history)
            results += response
            token_count += len(response)

            if i >= self.max_gleanings - 1:
                break

            # 检查是否还有更多实体
            history.append({"role": "assistant", "content": response})
            history.append({"role": "user", "content": LOOP_PROMPT})

            continuation = await self._call_llm_with_history(prompt, history)
            token_count += len(continuation)

            if continuation.strip().upper() != "Y":
                break

            history.append({"role": "assistant", "content": "Y"})

        # 解析结果
        entities, relations = self._parse_extraction_results(results, doc_id)

        # 缓存结果
        self.cache.set(
            f"extraction:{cache_key}",
            {
                "entities": [e.to_dict() for e in entities],
                "relations": [r.to_dict() for r in relations],
                "token_count": token_count,
            },
        )

        return ExtractionResult(entities, relations, token_count)

    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM"""
        # 检查缓存
        cached = self.cache.get_llm_cache("graphrag", prompt, [])
        if cached:
            return cached

        # 调用 LLM（这里需要适配你的 LLM 客户端）
        response = await self.llm_client.achat(prompt)

        # 缓存结果
        self.cache.set_llm_cache("graphrag", prompt, [], response)

        return response

    async def _call_llm_with_history(
        self, system_prompt: str, history: List[Dict[str, str]]
    ) -> str:
        """带历史记录的 LLM 调用"""
        # 构建完整对话
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)

        # 这里简化处理，实际应根据你的 LLM 客户端调整
        response = await self.llm_client.achat_messages(messages)

        return response

    def _parse_extraction_results(
        self, results: str, doc_id: str
    ) -> Tuple[List[Entity], List[Relation]]:
        """
        解析抽取结果

        Args:
            results: LLM 返回的原始文本
            doc_id: 文档ID

        Returns:
            (实体列表, 关系列表)
        """
        entities = []
        relations = []
        entity_names = set()  # 用于去重

        # 分割记录（使用 re.escape 转义正则特殊字符）
        records = re.split(
            rf"{re.escape(RECORD_DELIMITER)}|{re.escape(COMPLETION_DELIMITER)}", results
        )

        for record in records:
            record = record.strip()
            if not record:
                continue

            # 提取括号内的内容
            match = re.search(r"\((.*)\)", record, re.DOTALL)
            if not match:
                continue

            content = match.group(1)
            parts = content.split(TUPLE_DELIMITER)

            if len(parts) < 2:
                continue

            record_type = parts[0].strip("\"'")

            if record_type == "entity" and len(parts) >= 4:
                # 解析实体
                name = self._normalize_text(parts[1])
                entity_type = self._normalize_text(parts[2])
                description = self._normalize_text(parts[3])

                # 去重检查
                if name.lower() not in entity_names:
                    entity_names.add(name.lower())
                    entities.append(
                        Entity(
                            name=name,
                            entity_type=entity_type,
                            description=description,
                            source_id=doc_id,
                        )
                    )

            elif record_type == "relationship" and len(parts) >= 5:
                # 解析关系
                source = self._normalize_text(parts[1])
                target = self._normalize_text(parts[2])
                description = self._normalize_text(parts[3])
                try:
                    strength = float(parts[4].strip())
                except ValueError:
                    strength = 5.0

                relations.append(
                    Relation(
                        source_entity=source,
                        target_entity=target,
                        description=description,
                        strength=strength,
                        source_id=doc_id,
                    )
                )

        return entities, relations

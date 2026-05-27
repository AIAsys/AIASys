"""
实体消歧
合并相似/重复的实体
"""

import logging
from collections import defaultdict
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)

# 尝试导入 editdistance，如果没有则使用备选方案
try:
    import editdistance

    EDITDISTANCE_AVAILABLE = True
except ImportError:
    EDITDISTANCE_AVAILABLE = False
    logger.warning("editdistance not available, using fallback similarity")


def _levenshtein_distance(s1: str, s2: str) -> int:
    """计算 Levenshtein 编辑距离（备选实现）"""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # 计算插入、删除、替换的成本
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1.lower() != c2.lower())
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


from ..models.entity import Entity


class EntityResolver:
    """实体消歧器 - 合并相似实体"""

    def __init__(self, llm_client=None):
        self.llm = llm_client
        self._similarity_threshold = 0.8

    def is_similar(self, name1: str, name2: str) -> bool:
        """
        判断两个实体名称是否相似
        """
        # 完全匹配
        if name1.lower() == name2.lower():
            return True

        # 检查数字差异（如 John 1 vs John 2 应被视为不同）
        if self._has_digit_diff(name1, name2):
            return False

        # 英文使用编辑距离
        if self._is_english(name1) and self._is_english(name2):
            max_len = max(len(name1), len(name2))
            if max_len == 0:
                return False
            if EDITDISTANCE_AVAILABLE:
                dist = editdistance.eval(name1.lower(), name2.lower())
            else:
                dist = _levenshtein_distance(name1.lower(), name2.lower())
            return dist <= min(len(name1), len(name2)) // 2

        # 中文/混合使用字符集相似度
        set1, set2 = set(name1), set(name2)
        max_len = max(len(set1), len(set2))
        if max_len < 4:
            return len(set1 & set2) > 1

        return len(set1 & set2) / max_len >= self._similarity_threshold

    def _has_digit_diff(self, a: str, b: str) -> bool:
        """检查差异中是否包含数字"""

        def get_2grams(s):
            return {s[i : i + 2] for i in range(len(s) - 1)}

        diff = get_2grams(a) ^ get_2grams(b)
        return any(any(c.isdigit() for c in pair) for pair in diff)

    def _is_english(self, s: str) -> bool:
        """检查字符串是否为英文"""
        return all(c.isascii() and (c.isalpha() or c.isspace()) for c in s if c.isalpha())

    def find_candidates(self, entities: List[Entity]) -> Dict[str, List[Tuple[Entity, Entity]]]:
        """
        按类型分组，找出相似的实体对

        Returns:
            Dict[entity_type, List[(entity1, entity2)]]
        """
        # 按类型分组
        type_groups: Dict[str, List[Entity]] = defaultdict(list)
        for e in entities:
            type_groups[e.entity_type].append(e)

        # 在每个类型内找出相似对
        candidates = {}
        for entity_type, group in type_groups.items():
            pairs = []
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    if self.is_similar(group[i].name, group[j].name):
                        pairs.append((group[i], group[j]))
            if pairs:
                candidates[entity_type] = pairs

        return candidates

    async def resolve_with_llm(
        self, candidates: List[Tuple[Entity, Entity]], entity_type: str
    ) -> Set[Tuple[str, str]]:
        """
        使用 LLM 判断实体对是否是同一个实体

        Returns:
            Set of (name1, name2) that should be merged
        """
        if not self.llm or not candidates:
            return set()

        # 构建 Prompt
        questions = []
        for i, (e1, e2) in enumerate(candidates[:10]):  # 限制批量大小
            questions.append(
                f"Question {i + 1}: Is '{e1.name}' (description: {e1.description[:50]}) "
                f"and '{e2.name}' (description: {e2.description[:50]}) the same {entity_type}?"
            )

        prompt = f"""You are an expert in entity resolution. Determine if the following entity pairs refer to the same real-world entity.

{chr(10).join(questions)}

Answer in the format:
For Question i, Yes/No, entity A and entity B are the same/different {entity_type}.

Be conservative - only merge if you are confident they are the same entity."""

        try:
            response = await self.llm.chat(prompt)
            return self._parse_resolution_response(response, candidates)
        except Exception as e:
            logger.error("LLM resolution failed: %s", e)
            return set()

    def _parse_resolution_response(
        self, response: str, candidates: List[Tuple[Entity, Entity]]
    ) -> Set[Tuple[str, str]]:
        """解析 LLM 响应，提取应合并的实体对"""
        to_merge = set()

        lines = response.strip().split("\n")
        for line in lines:
            line = line.strip().lower()
            # 查找 "yes" 的回答
            if "question" in line and "yes" in line:
                try:
                    # 提取问题编号
                    import re

                    match = re.search(r"question\s*(\d+)", line)
                    if match:
                        idx = int(match.group(1)) - 1
                        if 0 <= idx < len(candidates):
                            e1, e2 = candidates[idx]
                            to_merge.add((e1.name, e2.name))
                except Exception:
                    continue

        return to_merge

    async def resolve(self, entities: List[Entity]) -> Dict[str, str]:
        """
        执行实体消歧

        Returns:
            Dict[old_name, canonical_name] - 实体名称映射关系
        """
        if len(entities) < 2:
            return {}

        # 1. 找出候选对
        candidates = self.find_candidates(entities)

        # 2. 使用 LLM 确认（如果有）
        merge_map: Dict[str, str] = {}

        for entity_type, pairs in candidates.items():
            if not self.llm:
                # 无 LLM 时，直接合并相似实体
                for e1, e2 in pairs:
                    # 选择更长的名称作为标准名
                    canonical = e1.name if len(e1.name) >= len(e2.name) else e2.name
                    merge_map[e1.name] = canonical
                    merge_map[e2.name] = canonical
            else:
                # 使用 LLM 确认
                to_merge = await self.resolve_with_llm(pairs, entity_type)
                for name1, name2 in to_merge:
                    # 选择更长的名称作为标准名
                    canonical = name1 if len(name1) >= len(name2) else name2
                    merge_map[name1] = canonical
                    merge_map[name2] = canonical

        return merge_map

    def merge_entities(self, entities: List[Entity], merge_map: Dict[str, str]) -> List[Entity]:
        """
        根据映射合并实体

        Args:
            entities: 原始实体列表
            merge_map: 名称映射 {old_name: canonical_name}

        Returns:
            合并后的实体列表
        """
        # 按标准名分组
        groups: Dict[str, List[Entity]] = defaultdict(list)

        for e in entities:
            canonical = merge_map.get(e.name, e.name)
            groups[canonical].append(e)

        # 合并每组实体
        merged = []
        for canonical_name, group in groups.items():
            if len(group) == 1:
                merged.append(group[0])
            else:
                # 合并多个实体
                merged_entity = Entity(
                    name=canonical_name,
                    entity_type=group[0].entity_type,
                    description=" | ".join(set(e.description for e in group if e.description)),
                    source_id=group[0].source_id,
                    metadata={"merged_from": [e.name for e in group], "original_count": len(group)},
                )
                merged.append(merged_entity)

        return merged

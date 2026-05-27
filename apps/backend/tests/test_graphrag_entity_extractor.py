"""GraphRAG 实体关系抽取测试。"""

import pytest

from app.graphrag.core.entity_extractor import EntityExtractor


class MockLLMClient:
    async def achat(self, prompt: str) -> str:
        return '''("entity"<|>"人工智能"<|>"technology"<|>"人工智能是计算机科学的一个分支，致力于创建能够执行通常需要人类智能的任务的系统")##
("entity"<|>"机器学习"<|>"technology"<|>"机器学习是人工智能的一个子集，专注于让计算机从数据中学习")##
("relationship"<|>"人工智能"<|>"机器学习"<|>"机器学习是人工智能的一个子集"<|>9)<|COMPLETE|>'''

    async def achat_messages(self, messages: list) -> str:
        return "N"


def test_parse_extraction_results():
    extractor = EntityExtractor(llm_client=None)

    results = '''("entity"<|>"人工智能"<|>"technology"<|>"AI描述")##
("entity"<|>"机器学习"<|>"technology"<|>"ML描述")##
("relationship"<|>"人工智能"<|>"机器学习"<|>"关系描述"<|>8)<|COMPLETE|>'''

    entities, relations = extractor._parse_extraction_results(results, "doc1")

    assert len(entities) == 2
    assert entities[0].name == "人工智能"
    assert entities[0].entity_type == "technology"

    assert len(relations) == 1
    assert relations[0].source_entity == "人工智能"
    assert relations[0].target_entity == "机器学习"
    assert relations[0].strength == 8.0


@pytest.mark.asyncio
async def test_extract():
    mock_llm = MockLLMClient()
    extractor = EntityExtractor(llm_client=mock_llm)

    result = await extractor.extract("人工智能和机器学习的关系", "doc1")

    assert len(result.entities) == 2
    assert len(result.relations) == 1
    assert result.token_count > 0

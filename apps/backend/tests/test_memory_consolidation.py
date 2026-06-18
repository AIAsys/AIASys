"""Memory consolidation 逻辑测试。"""

from pathlib import Path

import pytest

from app.services.memory.pipeline import (
    MemoryPipelineService,
    _build_consolidation_prompt,
    _parse_consolidation_response,
)
from app.services.memory.state_runtime import Stage1OutputRecord


@pytest.fixture
def service_with_layout(tmp_path: Path, monkeypatch):
    import app.core.config as config_module
    import app.services.memory.pipeline as pipeline_module

    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(
        pipeline_module,
        "get_user_global_memory_dir",
        config_module.get_user_global_memory_dir,
    )

    from app.services.memory.state_runtime import MemoryStateRuntime

    runtime = MemoryStateRuntime(tmp_path / "state.db")
    service = MemoryPipelineService(runtime=runtime)
    return service, tmp_path


class TestParseConsolidationResponse:
    def test_extracts_memory_and_summary(self):
        text = "<MEMORY>\n# New Memory\nContent.\n</MEMORY>\n\n<SUMMARY>\nNew summary.\n</SUMMARY>"
        memory, summary = _parse_consolidation_response(text)
        assert memory == "# New Memory\nContent."
        assert summary == "New summary."

    def test_returns_none_on_noop(self):
        memory, summary = _parse_consolidation_response("<NOOP></NOOP>")
        assert memory is None
        assert summary is None

    def test_returns_none_on_empty(self):
        memory, summary = _parse_consolidation_response("")
        assert memory is None
        assert summary is None

    def test_extracts_without_extra_whitespace(self):
        text = "<MEMORY>  padded  </MEMORY>"
        memory, _summary = _parse_consolidation_response(text)
        assert memory == "padded"


class TestBuildConsolidationPrompt:
    def test_includes_all_sections(self):
        records = [
            Stage1OutputRecord(
                id="r1",
                user_id="u",
                session_id="s1",
                workspace_id=None,
                source_path="p",
                raw_memory="raw",
                rollout_summary="summary",
                rollout_slug="2026-05-20-s1",
                metadata={},
                created_at=100,
                consolidated_at=None,
            )
        ]
        prompt = _build_consolidation_prompt(
            current_memory="# Current",
            current_summary="# Summary",
            raw_memories="# Raw",
            rollout_texts=["# Rollout"],
            records=records,
        )
        assert "<MEMORY>" in prompt
        assert "<SUMMARY>" in prompt
        assert "Current" in prompt
        assert "2026-05-20-s1" in prompt

    def test_truncates_long_inputs(self):
        long_text = "x" * 100000
        prompt = _build_consolidation_prompt(
            current_memory=long_text,
            current_summary=long_text,
            raw_memories=long_text,
            rollout_texts=[long_text],
            records=[],
            max_input_chars=24000,
        )
        assert len(prompt) < 35000


@pytest.mark.asyncio
async def test_run_stage2_consolidation_triggers_consolidation_on_capacity(
    service_with_layout, monkeypatch
):
    service, tmp_path = service_with_layout
    import app.services.memory.pipeline as pipeline_module

    # 写入一个大的 MEMORY.md，触发 consolidation
    memory_dir = tmp_path / "local_default" / "global_workspace" / ".aiasys" / ".memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text("x" * int(8500), encoding="utf-8")
    (memory_dir / "memory_summary.md").write_text("", encoding="utf-8")
    (memory_dir / "raw_memories.md").write_text("# Raw\n", encoding="utf-8")
    (memory_dir / "rollout_summaries").mkdir(parents=True, exist_ok=True)

    # Mock LLM client
    class FakeChunk:
        class delta:
            content = "<MEMORY>\n# Consolidated\n</MEMORY>\n\n<SUMMARY>\nSummary\n</SUMMARY>"

    class FakeClient:
        async def chat_stream(self, *args, **kwargs):
            yield FakeChunk()

        async def aclose(self):
            pass

    monkeypatch.setattr(pipeline_module, "_create_memory_llm_client", lambda user_id: FakeClient())

    service.record_stage1_output(
        user_id="local_default",
        session_id="session-a",
        workspace_id=None,
        source_path="p",
        raw_memory="raw content",
        rollout_summary="summary",
        rollout_slug="slug-a",
        now=100,
    )

    count = await service.run_stage2_consolidation(user_id="local_default")
    assert count == 1

    memory_text = (memory_dir / "MEMORY.md").read_text(encoding="utf-8")
    assert "# Consolidated" in memory_text

    summary_text = (memory_dir / "memory_summary.md").read_text(encoding="utf-8")
    assert "Summary" in summary_text


@pytest.mark.asyncio
async def test_run_stage2_skips_consolidation_when_healthy(service_with_layout):
    service, tmp_path = service_with_layout

    memory_dir = tmp_path / "local_default" / "global_workspace" / ".aiasys" / ".memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text("# Small", encoding="utf-8")
    (memory_dir / "memory_summary.md").write_text("", encoding="utf-8")
    (memory_dir / "raw_memories.md").write_text("# Raw\n", encoding="utf-8")
    (memory_dir / "rollout_summaries").mkdir(parents=True, exist_ok=True)

    service.record_stage1_output(
        user_id="local_default",
        session_id="session-a",
        workspace_id=None,
        source_path="p",
        raw_memory="raw",
        rollout_summary="summary",
        rollout_slug="slug-a",
        now=100,
    )

    count = await service.run_stage2_consolidation(user_id="local_default")
    assert count == 1

    # 未触发 consolidation，MEMORY.md 应保持追加后的内容
    memory_text = (memory_dir / "MEMORY.md").read_text(encoding="utf-8")
    assert "Stage 2 appended memories" in memory_text


@pytest.mark.asyncio
async def test_run_stage2_noop_consolidation(service_with_layout, monkeypatch):
    service, tmp_path = service_with_layout
    import app.services.memory.pipeline as pipeline_module

    memory_dir = tmp_path / "local_default" / "global_workspace" / ".aiasys" / ".memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text("x" * int(8500), encoding="utf-8")
    (memory_dir / "memory_summary.md").write_text("", encoding="utf-8")
    (memory_dir / "raw_memories.md").write_text("# Raw\n", encoding="utf-8")
    (memory_dir / "rollout_summaries").mkdir(parents=True, exist_ok=True)

    class FakeChunk:
        class delta:
            content = "<NOOP></NOOP>"

    class FakeClient:
        async def chat_stream(self, *args, **kwargs):
            yield FakeChunk()

        async def aclose(self):
            pass

    monkeypatch.setattr(pipeline_module, "_create_memory_llm_client", lambda user_id: FakeClient())

    service.record_stage1_output(
        user_id="local_default",
        session_id="session-a",
        workspace_id=None,
        source_path="p",
        raw_memory="raw",
        rollout_summary="summary",
        rollout_slug="slug-a",
        now=100,
    )

    count = await service.run_stage2_consolidation(user_id="local_default")
    assert count == 1

    # NOOP 时不应改写 MEMORY.md，保持追加后的内容
    memory_text = (memory_dir / "MEMORY.md").read_text(encoding="utf-8")
    assert "Stage 2 appended memories" in memory_text

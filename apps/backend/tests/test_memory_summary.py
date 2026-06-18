"""Memory summary 维护测试。"""

from pathlib import Path

import pytest

from app.services.memory.pipeline import MemoryPipelineService


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


@pytest.mark.asyncio
async def test_summary_updated_after_consolidation(service_with_layout, monkeypatch):
    service, tmp_path = service_with_layout
    import app.services.memory.pipeline as pipeline_module

    memory_dir = tmp_path / "local_default" / "global_workspace" / ".aiasys" / ".memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text("x" * int(8500), encoding="utf-8")
    (memory_dir / "memory_summary.md").write_text("# Old Summary\n", encoding="utf-8")
    (memory_dir / "raw_memories.md").write_text("# Raw\n", encoding="utf-8")
    (memory_dir / "rollout_summaries").mkdir(parents=True, exist_ok=True)

    class FakeChunk:
        class delta:
            content = (
                "<MEMORY>\n# New Memory\n</MEMORY>\n\n"
                "<SUMMARY>\n# Updated Summary\nNew content.\n</SUMMARY>"
            )

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

    await service.run_stage2_consolidation(user_id="local_default")

    summary_text = (memory_dir / "memory_summary.md").read_text(encoding="utf-8")
    assert "Updated Summary" in summary_text
    assert "New content" in summary_text


@pytest.mark.asyncio
async def test_summary_truncated_when_too_long(service_with_layout, monkeypatch):
    service, tmp_path = service_with_layout
    import app.services.memory.pipeline as pipeline_module
    from app.services.memory.constants import MAX_SUMMARY_SIZE

    memory_dir = tmp_path / "local_default" / "global_workspace" / ".aiasys" / ".memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text("x" * int(8500), encoding="utf-8")
    (memory_dir / "memory_summary.md").write_text("", encoding="utf-8")
    (memory_dir / "raw_memories.md").write_text("# Raw\n", encoding="utf-8")
    (memory_dir / "rollout_summaries").mkdir(parents=True, exist_ok=True)

    long_summary = "s" * (MAX_SUMMARY_SIZE + 1000)

    class FakeChunk:
        class delta:
            content = f"<MEMORY>\n# Mem\n</MEMORY>\n\n<SUMMARY>\n{long_summary}\n</SUMMARY>"

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

    await service.run_stage2_consolidation(user_id="local_default")

    summary_text = (memory_dir / "memory_summary.md").read_text(encoding="utf-8")
    assert len(summary_text) <= MAX_SUMMARY_SIZE + 50  # 允许截断标记的额外长度

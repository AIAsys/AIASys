from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.tracking import subagent_tracking_service as tracking_module


def _write_subagent_meta(
    root: Path,
    *,
    user_id: str,
    session_id: str,
    agent_id: str,
    subagent_type: str = "reviewer",
    description: str = "审查补丁",
    last_task_id: str = "task-1",
) -> Path:
    subagent_dir = root / user_id / session_id / ".aiasys" / "session" / "subagents" / agent_id
    subagent_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "agent_id": agent_id,
        "subagent_type": subagent_type,
        "status": "running_foreground",
        "description": description,
        "created_at": 1710000000.0,
        "updated_at": 1710000030.0,
        "last_task_id": last_task_id,
        "launch_spec": {
            "agent_id": agent_id,
            "subagent_type": subagent_type,
            "model_override": None,
            "effective_model": "kimi-test",
            "created_at": 1710000000.0,
        },
    }
    (subagent_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False),
        encoding="utf-8",
    )
    (subagent_dir / "wire.jsonl").write_text("", encoding="utf-8")
    (subagent_dir / "context.jsonl").write_text("", encoding="utf-8")
    work_dir = subagent_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "report.md").write_text("# report", encoding="utf-8")
    return subagent_dir


@pytest.mark.asyncio
async def test_tracking_service_projects_ownership_into_execution_tree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user_id = "63c0c2b2-7c6b-4d6f-8e25-111111111111"
    session_id = "session-owner-1"
    _write_subagent_meta(
        tmp_path,
        user_id=user_id,
        session_id=session_id,
        agent_id="agent-1",
    )
    monkeypatch.setattr(tracking_module, "WORKSPACE_DIR", tmp_path)

    service = tracking_module.SubAgentTrackingService()
    tree = service.get_execution_tree(
        user_id=user_id,
        session_id=session_id,
        host_events=[
            {"type": "step_begin", "step_n": 3},
            {"type": "tool_call", "tool_call_id": "task-1"},
        ],
    )

    assert len(tree.subagent_calls) == 1
    call = tree.subagent_calls[0]
    subagent = call["subagent"]
    assert call["tool_call_id"] == "task-1"
    assert call["parent_tool_call_id"] == "task-1"
    assert subagent["id"] == "agent-1"
    assert subagent["agent_id"] == "agent-1"
    assert subagent["subagent_type"] == "reviewer"
    assert subagent["host_session_id"] == session_id
    assert subagent["ownership"] == {
        "host_session_id": session_id,
        "parent_tool_call_id": "task-1",
        "agent_id": "agent-1",
        "subagent_type": "reviewer",
    }
    assert subagent["node_role"] == "collaboration_node"
    assert subagent["hosting_controller"] is False
    assert call["step_number"] == 3
    assert subagent["name"] == "审查补丁"


@pytest.mark.asyncio
async def test_tracking_service_projects_ownership_into_detail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user_id = "63c0c2b2-7c6b-4d6f-8e25-222222222222"
    session_id = "session-owner-2"
    _write_subagent_meta(
        tmp_path,
        user_id=user_id,
        session_id=session_id,
        agent_id="agent-2",
        subagent_type="coder",
        description="实现接口",
        last_task_id="task-9",
    )
    monkeypatch.setattr(tracking_module, "WORKSPACE_DIR", tmp_path)

    service = tracking_module.SubAgentTrackingService()
    detail = service.get_subagent_detail(user_id, session_id, "agent-2")

    assert detail is not None
    assert detail.id == "agent-2"
    assert detail.name == "实现接口"
    assert detail.description == "实现接口"
    assert detail.duration_ms == 30000
    assert detail.ownership is not None
    assert detail.ownership.host_session_id == session_id
    assert detail.ownership.parent_tool_call_id == "task-9"
    assert detail.ownership.agent_id == "agent-2"
    assert detail.ownership.subagent_type == "coder"
    assert len(detail.output_files) == 1


@pytest.mark.asyncio
async def test_tracking_service_reads_plain_context_jsonl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user_id = "63c0c2b2-7c6b-4d6f-8e25-333333333333"
    session_id = "session-owner-3"
    subagent_dir = _write_subagent_meta(
        tmp_path,
        user_id=user_id,
        session_id=session_id,
        agent_id="agent-3",
        subagent_type="worker",
        description="执行任务",
        last_task_id="task-ctx",
    )
    context_lines = [
        {"role": "user", "content": "请检查当前 notebook 输出"},
        {"role": "assistant", "content": "收到，我先回看 notebook 输出。"},
        {"role": "tool", "tool_call_id": "tool-1", "content": "工具输出"},
    ]
    (subagent_dir / "context.jsonl").write_text(
        "\n".join(json.dumps(line, ensure_ascii=False) for line in context_lines) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tracking_module, "WORKSPACE_DIR", tmp_path)

    service = tracking_module.SubAgentTrackingService()
    detail = service.get_subagent_detail(user_id, session_id, "agent-3")

    assert detail is not None
    assert detail.context == context_lines


@pytest.mark.asyncio
async def test_tracking_service_avoids_fake_step_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user_id = "63c0c2b2-7c6b-4d6f-8e25-444444444444"
    session_id = "session-owner-4"
    subagent_dir = _write_subagent_meta(
        tmp_path,
        user_id=user_id,
        session_id=session_id,
        agent_id="agent-4",
        subagent_type="worker",
        description="无步骤记录",
        last_task_id="task-no-step",
    )
    (subagent_dir / "wire.jsonl").write_text(
        json.dumps({"type": "metadata", "protocol_version": "1.0"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tracking_module, "WORKSPACE_DIR", tmp_path)

    service = tracking_module.SubAgentTrackingService()
    summaries = service.list_subagents(user_id, session_id)

    assert len(summaries) == 1
    assert summaries[0].progress["current_step"] == 0
    assert summaries[0].progress["total_steps"] == 0


@pytest.mark.asyncio
async def test_tracking_service_falls_back_to_dispatch_order_for_zero_step(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user_id = "63c0c2b2-7c6b-4d6f-8e25-555555555555"
    session_id = "session-owner-5"
    _write_subagent_meta(
        tmp_path,
        user_id=user_id,
        session_id=session_id,
        agent_id="agent-5",
        last_task_id="task-zero-step",
    )
    monkeypatch.setattr(tracking_module, "WORKSPACE_DIR", tmp_path)

    service = tracking_module.SubAgentTrackingService()
    tree = service.get_execution_tree(
        user_id=user_id,
        session_id=session_id,
        host_events=[
            {"type": "step_begin", "step_n": 0},
            {"type": "tool_call", "tool_call_id": "task-zero-step"},
        ],
    )

    assert len(tree.subagent_calls) == 1
    call = tree.subagent_calls[0]
    assert call["step_number"] == 1
    assert call["subagent"]["triggered_by_step"] == 1

"""SessionBudgetMixin 锁与异步调用集成测试。

覆盖真实 asyncio.Lock 路径，防止同步 `with self._metadata_lock` 类 bug 回归。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.session import SessionBudget, SessionMetadata
from app.services.agent.runtime_backends.aiasys.session_budget import (
    SessionBudgetMixin,
)


def _write_metadata(work_dir: Path, meta: SessionMetadata) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "metadata.json").write_text(
        meta.model_dump_json(indent=2),
        encoding="utf-8",
    )


def _read_metadata(work_dir: Path) -> SessionMetadata:
    data = json.loads((work_dir / "metadata.json").read_text(encoding="utf-8"))
    return SessionMetadata(**data)


class _FakeBudgetSession(SessionBudgetMixin):
    def __init__(self, work_dir: Path, budget: SessionBudget | None) -> None:
        self._spec = SimpleNamespace(work_dir=str(work_dir))
        self.session_id = "test-session"
        self._metadata_lock = asyncio.Lock()
        self.budget = budget
        self._estimated_token_count = 0
        self._pending_token_estimate = 0


def _build_session(work_dir: Path, budget: SessionBudget | None) -> _FakeBudgetSession:
    return _FakeBudgetSession(work_dir, budget)


@pytest.mark.asyncio
async def test_save_budget_with_real_asyncio_lock(tmp_path: Path) -> None:
    """_save_budget 在真实 asyncio.Lock 下应正常写 metadata。"""
    budget = SessionBudget(token_budget=1000, tokens_used=100, status="active")
    meta = SessionMetadata.model_construct(session_id="test-session", budget=budget)
    _write_metadata(tmp_path, meta)

    session = _build_session(tmp_path, budget)
    await SessionBudgetMixin._save_budget(session)

    updated = _read_metadata(tmp_path)
    assert updated.budget is not None
    assert updated.budget.tokens_used == 100
    assert updated.budget.status == "active"


@pytest.mark.asyncio
async def test_check_session_budget_with_real_asyncio_lock(tmp_path: Path) -> None:
    """_check_session_budget 在真实 asyncio.Lock 下应正确累加 token。"""
    budget = SessionBudget(token_budget=1000, tokens_used=100, status="active")
    meta = SessionMetadata.model_construct(session_id="test-session", budget=budget)
    _write_metadata(tmp_path, meta)

    session = _build_session(tmp_path, budget)
    await SessionBudgetMixin._check_session_budget(session, 50, 20)

    updated = _read_metadata(tmp_path)
    assert updated.budget is not None
    assert updated.budget.tokens_used == 170
    assert updated.budget.context_tokens == 50
    assert updated.budget.status == "active"


@pytest.mark.asyncio
async def test_is_session_budget_blocked_not_exhausted(tmp_path: Path) -> None:
    """预算未耗尽时返回 False，且不修改状态。"""
    budget = SessionBudget(token_budget=1000, tokens_used=100, status="active")
    meta = SessionMetadata.model_construct(session_id="test-session", budget=budget)
    _write_metadata(tmp_path, meta)

    session = _build_session(tmp_path, budget)
    blocked = await SessionBudgetMixin._is_session_budget_blocked(session)

    assert blocked is False
    updated = _read_metadata(tmp_path)
    assert updated.budget is not None
    assert updated.budget.status == "active"


@pytest.mark.asyncio
async def test_is_session_budget_blocked_sets_limited(tmp_path: Path) -> None:
    """预算耗尽时应置为 budget_limited 并返回 True。"""
    budget = SessionBudget(token_budget=100, tokens_used=100, status="active")
    meta = SessionMetadata.model_construct(session_id="test-session", budget=budget)
    _write_metadata(tmp_path, meta)

    session = _build_session(tmp_path, budget)
    blocked = await SessionBudgetMixin._is_session_budget_blocked(session)

    assert blocked is True
    assert session.budget.status == "budget_limited"
    updated = _read_metadata(tmp_path)
    assert updated.budget is not None
    assert updated.budget.status == "budget_limited"


@pytest.mark.asyncio
async def test_save_context_tokens_to_metadata_with_real_lock(tmp_path: Path) -> None:
    """_save_context_tokens_to_metadata 在真实 asyncio.Lock 下应正确写入。"""
    budget = SessionBudget(token_budget=1000, context_tokens=10, status="active")
    meta = SessionMetadata.model_construct(session_id="test-session", budget=budget)
    _write_metadata(tmp_path, meta)

    session = _build_session(tmp_path, budget)
    session._estimated_token_count = 888
    await SessionBudgetMixin._save_context_tokens_to_metadata(session)

    updated = _read_metadata(tmp_path)
    assert updated.budget is not None
    assert updated.budget.context_tokens == 888



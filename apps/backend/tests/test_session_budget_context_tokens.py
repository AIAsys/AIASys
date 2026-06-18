"""测试 _save_context_tokens_to_metadata 独立写入路径。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.models.session import SessionBudget, SessionMetadata


def _build_meta(budget: SessionBudget | None = None) -> SessionMetadata:
    """构造最小合法 SessionMetadata，绕过 pydantic validator。"""
    return SessionMetadata.model_construct(
        session_id="test-session",
        budget=budget,
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


def _call_save_context_tokens(work_dir: Path, estimated: int) -> None:
    """直接调用 _save_context_tokens_to_metadata 静态方法。"""
    from app.services.agent.runtime_backends.aiasys.session_budget import (
        SessionBudgetMixin,
    )

    session = MagicMock()
    session._spec = MagicMock()
    session._spec.work_dir = str(work_dir)
    session._estimated_token_count = estimated
    session.budget = None
    session._metadata_lock = MagicMock()

    SessionBudgetMixin._save_context_tokens_to_metadata(session)


def test_save_context_tokens_when_budget_is_none(tmp_path: Path) -> None:
    """预算未开启时，不创建 budget 对象，避免污染初始化恢复路径。"""
    meta = _build_meta(budget=None)
    _write_metadata(tmp_path, meta)

    _call_save_context_tokens(tmp_path, estimated=12345)

    updated = _read_metadata(tmp_path)
    # budget 为 None 时不创建对象，保持原始状态
    assert updated.budget is None


def test_save_context_tokens_when_budget_exists(tmp_path: Path) -> None:
    """预算已开启时，只更新 context_tokens，不影响其他字段。"""
    meta = _build_meta(
        budget=SessionBudget(
            token_budget=100000,
            tokens_used=5000,
            context_tokens=200,
            status="active",
        )
    )
    _write_metadata(tmp_path, meta)

    _call_save_context_tokens(tmp_path, estimated=88888)

    updated = _read_metadata(tmp_path)
    assert updated.budget is not None
    assert updated.budget.context_tokens == 88888
    assert updated.budget.tokens_used == 5000
    assert updated.budget.token_budget == 100000
    assert updated.budget.status == "active"


def test_save_context_tokens_skips_when_estimated_is_zero(tmp_path: Path) -> None:
    """_estimated_token_count 为 0 时不写入，避免覆盖已有精确值。"""
    meta = _build_meta(budget=SessionBudget(context_tokens=99999))
    _write_metadata(tmp_path, meta)

    _call_save_context_tokens(tmp_path, estimated=0)

    updated = _read_metadata(tmp_path)
    assert updated.budget is not None
    assert updated.budget.context_tokens == 99999


def test_save_context_tokens_noop_when_no_metadata(tmp_path: Path) -> None:
    """metadata.json 不存在时不报错。"""
    from app.services.agent.runtime_backends.aiasys.session_budget import (
        SessionBudgetMixin,
    )

    session = MagicMock()
    session._spec = MagicMock()
    session._spec.work_dir = str(tmp_path)
    session._estimated_token_count = 12345
    session.budget = None
    session._metadata_lock = MagicMock()

    SessionBudgetMixin._save_context_tokens_to_metadata(session)
    assert not (tmp_path / "metadata.json").exists()

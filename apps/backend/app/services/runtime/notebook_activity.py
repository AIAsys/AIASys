"""
Notebook workbench 运行锁。

用于协调用户直接发起的 notebook 执行与编辑锁语义。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

_NOTEBOOK_SESSION_LOCKS: dict[str, asyncio.Lock] = {}
_NOTEBOOK_LOCKS: dict[str, asyncio.Lock] = {}


def _build_session_key(user_id: str, session_id: str) -> str:
    return f"{user_id}/{session_id}"


def _build_notebook_key(user_id: str, notebook_path: str) -> str:
    return f"{user_id}/{Path(notebook_path).as_posix()}"


def get_notebook_session_lock(user_id: str, session_id: str) -> asyncio.Lock:
    """按 session 级获取 notebook 执行锁。"""
    key = _build_session_key(user_id, session_id)
    lock = _NOTEBOOK_SESSION_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _NOTEBOOK_SESSION_LOCKS[key] = lock
    return lock


def get_notebook_lock(user_id: str, notebook_path: str) -> asyncio.Lock:
    """按 notebook 级获取执行锁。同一 notebook 的并发执行串行化。"""
    key = _build_notebook_key(user_id, notebook_path)
    lock = _NOTEBOOK_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _NOTEBOOK_LOCKS[key] = lock
    return lock


def is_notebook_session_busy(user_id: str, session_id: str) -> bool:
    return get_notebook_session_lock(user_id, session_id).locked()

"""
内置终端 WebSocket API

提供 /ws/terminal/{user_id}/{session_id} 端点，支持双向实时通信：
- Client → Server: spawn / attach / input / resize / kill / reduce_grace_time
- Server → Client: spawned / attached / output / exited / error

WebSocket 连接断开不会终止 PTY 进程。PTY 进程在 PtyManager 中独立存活，
前端重连时通过 attach 恢复。PTY 进程只在 shell 退出、显式 kill 或后端服务关闭时终止。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.terminal.pty_manager import (
    PtyManager,
    PtyUnsupportedError,
    get_pty_manager,
)
from app.services.workspace_registry import get_workspace_registry_service

logger = logging.getLogger(__name__)


def _log_task_exception(task: asyncio.Task) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        exc = task.exception()
        if exc is not None:
            logger.error("后台任务异常: %s", exc, exc_info=True)


router = APIRouter(tags=["terminal"])


async def _get_session_cwd(user_id: str, session_id: str) -> str | None:
    """根据 user_id 和 session_id 解析工作目录"""
    try:
        registry = get_workspace_registry_service()
        workspace_id = registry.find_workspace_id_by_session_id(user_id, session_id)
        if workspace_id:
            return str(registry.get_workspace_root(user_id, workspace_id))
        # fallback: session 目录
        return str(registry.get_session_dir(user_id, session_id))
    except Exception as exc:
        logger.warning(
            "获取终端工作目录失败: user_id=%s session_id=%s %s", user_id, session_id, exc
        )
        return None


def _make_session_key(user_id: str, session_id: str, terminal_id: str) -> str:
    """生成用于 PtyManager detach/attach 的 session_key"""
    return f"{user_id}:{session_id}:{terminal_id}"


@router.websocket("/ws/terminal/{user_id}/{session_id}")
async def terminal_websocket(websocket: WebSocket, user_id: str, session_id: str):
    """终端 WebSocket 连接"""
    await websocket.accept()
    logger.info("终端 WebSocket 连接: user_id=%s session_id=%s", user_id, session_id)

    pty_manager = get_pty_manager()
    # 此连接内活跃的 terminal_id 集合
    active_terminals: dict[str, Any] = {}
    # 是否已断开
    disconnected = False

    def make_exit_handler(tid: str):
        def handler(exit_code: int) -> None:
            if disconnected:
                return
            _t = asyncio.create_task(_send_exit(tid, exit_code))
            _t.add_done_callback(_log_task_exception)
            active_terminals.pop(tid, None)

        return handler

    async def _send_exit(terminal_id: str, exit_code: int) -> None:
        if disconnected:
            return
        try:
            await websocket.send_json(
                {
                    "type": "exited",
                    "terminal_id": terminal_id,
                    "exit_code": exit_code,
                }
            )
        except Exception as exc:
            logger.debug("发送终端退出事件失败: %s", exc)

    # 输出批量缓冲：收集同一 terminal 的输出，每 16ms flush 一次
    _output_buffers: dict[str, list[bytes]] = {}
    _flush_tasks: dict[str, asyncio.Task | None] = {}

    async def _flush_output_buffer(tid: str) -> None:
        """将缓冲区中的输出合并后一次性发送"""
        if disconnected:
            _output_buffers.pop(tid, None)
            _flush_tasks.pop(tid, None)
            return
        chunks = _output_buffers.pop(tid, [])
        _flush_tasks.pop(tid, None)
        if not chunks:
            return
        try:
            merged = b"".join(chunks)
            text = merged.decode("utf-8", errors="replace")
            await websocket.send_json(
                {"type": "output", "terminal_id": tid, "data": text}
            )
        except Exception as exc:
            logger.debug("发送终端输出失败: %s", exc)

    def make_output_handler(tid: str):
        def handler(data: bytes) -> None:
            if disconnected:
                return
            if tid not in _output_buffers:
                _output_buffers[tid] = []
            _output_buffers[tid].append(data)
            # 如果该 terminal 还没有排期的 flush，延迟 16ms 后批量发送
            if tid not in _flush_tasks or _flush_tasks[tid] is None or _flush_tasks[tid].done():
                async def _delayed_flush() -> None:
                    await asyncio.sleep(0.016)  # ~60fps 批量窗口
                    await _flush_output_buffer(tid)
                _t = asyncio.create_task(_delayed_flush())
                _t.add_done_callback(_log_task_exception)
                _flush_tasks[tid] = _t

        return handler

    async def cleanup_connection() -> None:
        """清理此连接：flush 剩余输出，取消回调绑定"""
        nonlocal disconnected
        disconnected = True
        # flush 所有剩余缓冲区
        for tid in list(_output_buffers.keys()):
            await _flush_output_buffer(tid)
        _output_buffers.clear()
        _flush_tasks.clear()
        for terminal_id in list(active_terminals.keys()):
            session_key = _make_session_key(user_id, session_id, terminal_id)
            try:
                await pty_manager.detach(terminal_id, session_key)
            except Exception as exc:
                logger.debug("PTY detach 失败: terminal_id=%s %s", terminal_id, exc)
        active_terminals.clear()

    try:
        while True:
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "terminal_id": "",
                        "message": "Invalid JSON",
                    }
                )
                continue

            msg_type = payload.get("type")
            terminal_id = payload.get("terminal_id", "")

            if msg_type == "spawn":
                if not terminal_id:
                    terminal_id = f"term-{uuid.uuid4().hex[:8]}"

                rows = int(payload.get("rows", 24))
                cols = int(payload.get("cols", 80))
                cwd = payload.get("cwd") or await _get_session_cwd(user_id, session_id)

                # 检查是否已有同名会话（可能是重连后前端重新 spawn）
                existing = pty_manager.get_session(terminal_id)
                if existing and not existing._closed:
                    # 已有活跃会话，走 attach 逻辑
                    session_key = _make_session_key(user_id, session_id, terminal_id)
                    session = await pty_manager.attach(
                        session_key=session_key,
                        on_output=make_output_handler(terminal_id),
                        on_exit=make_exit_handler(terminal_id),
                    )
                    if session:
                        active_terminals[terminal_id] = session
                        await websocket.send_json(
                            {
                                "type": "attached",
                                "terminal_id": terminal_id,
                                "pid": session.pid,
                            }
                        )
                        continue

                # 如果该 terminal_id 在本地映射中存在但 PTY 已死，先清理
                if terminal_id in active_terminals:
                    await pty_manager.kill(terminal_id)
                    active_terminals.pop(terminal_id, None)

                session_key = _make_session_key(user_id, session_id, terminal_id)

                try:
                    session = await pty_manager.spawn(
                        terminal_id=terminal_id,
                        rows=rows,
                        cols=cols,
                        cwd=cwd,
                        on_output=make_output_handler(terminal_id),
                        on_exit=make_exit_handler(terminal_id),
                        session_key=session_key,
                    )
                    active_terminals[terminal_id] = session
                    await websocket.send_json(
                        {
                            "type": "spawned",
                            "terminal_id": terminal_id,
                            "pid": session.pid,
                        }
                    )
                except PtyUnsupportedError as exc:
                    logger.warning("PTY 当前平台不可用: terminal_id=%s %s", terminal_id, exc)
                    await websocket.send_json(
                        {
                            "type": "error",
                            "terminal_id": terminal_id,
                            "message": str(exc),
                        }
                    )
                except Exception as exc:
                    logger.exception("PTY spawn 失败: terminal_id=%s", terminal_id)
                    await websocket.send_json(
                        {
                            "type": "error",
                            "terminal_id": terminal_id,
                            "message": f"spawn failed: {exc}",
                        }
                    )

            elif msg_type == "attach":
                if not terminal_id:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "terminal_id": "",
                            "message": "attach requires terminal_id",
                        }
                    )
                    continue

                session_key = _make_session_key(user_id, session_id, terminal_id)
                session = await pty_manager.attach(
                    session_key=session_key,
                    on_output=make_output_handler(terminal_id),
                    on_exit=make_exit_handler(terminal_id),
                )
                if session is None:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "terminal_id": terminal_id,
                            "message": "终端会话已过期，请重新连接",
                        }
                    )
                else:
                    active_terminals[terminal_id] = session
                    await websocket.send_json(
                        {
                            "type": "attached",
                            "terminal_id": terminal_id,
                            "pid": session.pid,
                        }
                    )

            elif msg_type == "reduce_grace_time":
                # no-op：不做超时清理，PTY 进程持续存活直到显式 kill 或后端关闭
                pass

            elif msg_type == "input":
                if not terminal_id:
                    continue
                data = payload.get("data", "")
                ok = await pty_manager.write(terminal_id, data)
                if not ok:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "terminal_id": terminal_id,
                            "message": "terminal not found",
                        }
                    )

            elif msg_type == "resize":
                if not terminal_id:
                    continue
                rows = int(payload.get("rows", 24))
                cols = int(payload.get("cols", 80))
                ok = pty_manager.resize(terminal_id, rows, cols)
                if not ok:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "terminal_id": terminal_id,
                            "message": "terminal not found",
                        }
                    )

            elif msg_type == "kill":
                if not terminal_id:
                    continue
                await pty_manager.kill(terminal_id)
                active_terminals.pop(terminal_id, None)
                await websocket.send_json(
                    {
                        "type": "killed",
                        "terminal_id": terminal_id,
                    }
                )

            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "terminal_id": terminal_id,
                        "message": f"unknown message type: {msg_type}",
                    }
                )

    except WebSocketDisconnect:
        logger.info("终端 WebSocket 断开: user_id=%s session_id=%s", user_id, session_id)
    except Exception as exc:
        logger.exception("终端 WebSocket 异常: user_id=%s session_id=%s", user_id, session_id)
    finally:
        await cleanup_connection()
        logger.info(
            "终端 WebSocket 清理完成: user_id=%s session_id=%s active_terms=%d",
            user_id,
            session_id,
            len(active_terminals),
        )

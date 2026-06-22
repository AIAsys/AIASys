"""ACP Client runtime session — 通过 ACP 协议调用外部 Agent 预设。

设计参考 Hermes Agent 的 copilot_acp_client.py，适配到 AIASys AgentRuntimeSession 协议。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import subprocess
import threading
import time
from collections import deque
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from app.core.encoding_utils import smart_decode
from app.core.subprocess_utils import subprocess_kwargs
from app.services.agent.runtime_backends.base import (
    AgentRuntimeEvent,
    RuntimeSessionCreateSpec,
)

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 900.0


def _build_mcp_servers_payload(mcp_configs: list | None) -> dict[str, Any]:
    """把 AIASys runtime 的 MCPConfig 列表合并成 ACP `session/new` 需要的字典。"""
    merged: dict[str, Any] = {}
    if not isinstance(mcp_configs, list):
        return merged

    for block in mcp_configs:
        if not isinstance(block, dict):
            continue
        raw_servers = block.get("mcpServers") or block.get("mcp_servers")
        if not isinstance(raw_servers, dict):
            continue
        for server_name, server_config in raw_servers.items():
            normalized_name = str(server_name or "").strip()
            if not normalized_name or not isinstance(server_config, dict):
                continue
            merged[normalized_name] = dict(server_config)

    return merged


def _jsonrpc_error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": code, "message": message},
    }


def _ensure_path_within_cwd(path_text: str, cwd: str) -> Path:
    candidate = Path(path_text)
    if not candidate.is_absolute():
        raise PermissionError("ACP file-system paths must be absolute.")
    resolved = candidate.resolve()
    root = Path(cwd).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError(f"Path '{resolved}' is outside the session cwd '{root}'.") from exc
    return resolved


class AcpClientRuntimeSession:
    """通过 ACP 协议驱动外部 Agent 的 runtime session。"""

    def __init__(
        self,
        spec: RuntimeSessionCreateSpec,
        acp_command: str,
        acp_args: list[str],
    ) -> None:
        self._spec = spec
        self._acp_command = acp_command
        self._acp_args = list(acp_args)
        self._acp_cwd = str(Path(str(spec.work_dir)).resolve())
        self.session_id = spec.session_id
        self.mcp_configs = spec.mcp_configs
        # _run_prompt_sync 在线程池中运行，跨线程取消通知需要用线程安全的 Event。
        self._cancel_event = threading.Event()
        self._closed = False
        self._active_process: subprocess.Popen[bytes] | None = None
        self._active_process_lock = threading.Lock()

    def cancel(self) -> None:
        self._cancel_event.set()
        proc: subprocess.Popen[bytes] | None
        with self._active_process_lock:
            proc = self._active_process
        if proc is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 没有运行中的事件循环，直接同步清理。
            self._close_process()
        else:
            # cancel() 是协议中的同步方法，从异步上下文调用时不能阻塞事件循环。
            loop.run_in_executor(None, self._close_process)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # close() 是异步方法，把同步的进程清理逻辑交给线程池执行。
        await asyncio.to_thread(self._close_process)

    async def __aenter__(self) -> "AcpClientRuntimeSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def prompt(
        self,
        user_input: str | list[dict[str, Any]],
        *,
        merge_wire_messages: bool = False,
    ) -> AsyncGenerator[AgentRuntimeEvent, None]:
        del merge_wire_messages
        if self._closed:
            raise RuntimeError("Runtime session is already closed")

        text = (
            user_input
            if isinstance(user_input, str)
            else json.dumps(user_input, ensure_ascii=False)
        )

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                self._run_prompt_sync,
                text,
            )
        except Exception as exc:
            logger.exception("ACP prompt failed")
            yield AgentRuntimeEvent(kind="content", content_type="text", text=f"ACP error: {exc}")
            return

        response_text, reasoning_text = result
        if reasoning_text:
            yield AgentRuntimeEvent(kind="content", content_type="think", think=reasoning_text)
        if response_text:
            yield AgentRuntimeEvent(kind="content", content_type="text", text=response_text)

    # ---- sync ACP driver (runs in thread pool) --------------------------------

    def _run_prompt_sync(self, prompt_text: str) -> tuple[str, str]:
        try:
            proc = subprocess.Popen(
                [self._acp_command] + self._acp_args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
                cwd=self._acp_cwd,
                **subprocess_kwargs(),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Could not start ACP command '{self._acp_command}'. "
                "Make sure the agent CLI is installed and on PATH."
            ) from exc

        if proc.stdin is None or proc.stdout is None:
            proc.kill()
            raise RuntimeError("ACP process did not expose stdin/stdout pipes.")

        self._cancel_event.clear()
        with self._active_process_lock:
            self._active_process = proc

        inbox: queue.Queue[dict[str, Any]] = queue.Queue()
        stderr_tail: deque[str] = deque(maxlen=40)

        def _stdout_reader() -> None:
            for line in proc.stdout:
                try:
                    inbox.put(json.loads(smart_decode(line)))
                except Exception:
                    inbox.put({"raw": smart_decode(line).rstrip("\n")})

        def _stderr_reader() -> None:
            if proc.stderr is None:
                return
            for line in proc.stderr:
                stderr_tail.append(smart_decode(line).rstrip("\n"))

        out_thread = threading.Thread(target=_stdout_reader, daemon=True)
        err_thread = threading.Thread(target=_stderr_reader, daemon=True)
        out_thread.start()
        err_thread.start()

        next_id = 0

        def _request(
            method: str,
            params: dict[str, Any],
            *,
            text_parts: list[str] | None = None,
            reasoning_parts: list[str] | None = None,
        ) -> Any:
            nonlocal next_id
            next_id += 1
            request_id = next_id
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
            proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
            proc.stdin.flush()

            deadline = time.time() + _DEFAULT_TIMEOUT_SECONDS
            while time.time() < deadline:
                if self._cancel_event.is_set():
                    raise asyncio.CancelledError()
                if proc.poll() is not None:
                    break
                try:
                    msg = inbox.get(timeout=0.1)
                except queue.Empty:
                    continue

                if self._handle_server_message(
                    msg,
                    process=proc,
                    cwd=self._acp_cwd,
                    text_parts=text_parts,
                    reasoning_parts=reasoning_parts,
                ):
                    continue

                if msg.get("id") != request_id:
                    continue
                if "error" in msg:
                    err = msg.get("error") or {}
                    raise RuntimeError(f"ACP {method} failed: {err.get('message') or err}")
                return msg.get("result")

            stderr_text = "\n".join(stderr_tail).strip()
            if proc.poll() is not None and stderr_text:
                raise RuntimeError(f"ACP process exited early: {stderr_text}")
            raise TimeoutError(f"Timed out waiting for ACP response to {method}.")

        try:
            mcp_servers = _build_mcp_servers_payload(self.mcp_configs)
            _request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {"fs": {"readTextFile": True, "writeTextFile": True}},
                    "clientInfo": {
                        "name": "aiasys-agent",
                        "title": "AIASys Agent",
                        "version": "0.1.0",
                    },
                },
            )
            session = (
                _request(
                    "session/new",
                    {
                        "cwd": self._acp_cwd,
                        "mcpServers": mcp_servers or [],
                    },
                )
                or {}
            )
            session_id = str(session.get("sessionId") or "").strip()
            if not session_id:
                raise RuntimeError("ACP did not return a sessionId.")

            text_parts: list[str] = []
            reasoning_parts: list[str] = []
            _request(
                "session/prompt",
                {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": prompt_text}],
                },
                text_parts=text_parts,
                reasoning_parts=reasoning_parts,
            )
            return "".join(text_parts), "".join(reasoning_parts)
        finally:
            self._close_process()

    def _close_process(self) -> None:
        proc: subprocess.Popen[bytes] | None
        with self._active_process_lock:
            proc = self._active_process
            self._active_process = None
        if proc is None:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                    capture_output=True,
                    **subprocess_kwargs(),
                )
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:
            pass

    def _handle_server_message(
        self,
        msg: dict[str, Any],
        *,
        process: subprocess.Popen[bytes],
        cwd: str,
        text_parts: list[str] | None,
        reasoning_parts: list[str] | None,
    ) -> bool:
        method = msg.get("method")
        if not isinstance(method, str):
            return False

        if method == "session/update":
            params = msg.get("params") or {}
            update = params.get("update") or {}
            kind = str(update.get("sessionUpdate") or "").strip()
            content = update.get("content") or {}
            chunk_text = ""
            if isinstance(content, dict):
                chunk_text = str(content.get("text") or "")
            if kind == "agent_message_chunk" and chunk_text and text_parts is not None:
                text_parts.append(chunk_text)
            elif kind == "agent_thought_chunk" and chunk_text and reasoning_parts is not None:
                reasoning_parts.append(chunk_text)
            return True

        if process.stdin is None:
            return True

        message_id = msg.get("id")
        params = msg.get("params") or {}

        if method == "session/request_permission":
            response = {
                "jsonrpc": "2.0",
                "id": message_id,
                "result": {"outcome": {"outcome": "allow_once"}},
            }
        elif method == "fs/read_text_file":
            try:
                path = _ensure_path_within_cwd(str(params.get("path") or ""), cwd)
                content = path.read_text(encoding="utf-8") if path.exists() else ""
                line = params.get("line")
                limit = params.get("limit")
                if isinstance(line, int) and line > 1:
                    lines = content.splitlines(keepends=True)
                    start = line - 1
                    end = start + limit if isinstance(limit, int) and limit > 0 else None
                    content = "".join(lines[start:end])
                response = {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {"content": content},
                }
            except Exception as exc:
                response = _jsonrpc_error(message_id, -32602, str(exc))
        elif method == "fs/write_text_file":
            try:
                path = _ensure_path_within_cwd(str(params.get("path") or ""), cwd)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(params.get("content") or ""), encoding="utf-8")
                response = {"jsonrpc": "2.0", "id": message_id, "result": None}
            except Exception as exc:
                response = _jsonrpc_error(message_id, -32602, str(exc))
        else:
            response = _jsonrpc_error(
                message_id,
                -32601,
                f"ACP client method '{method}' is not supported by AIASys yet.",
            )

        process.stdin.write((json.dumps(response) + "\n").encode("utf-8"))
        process.stdin.flush()
        return True

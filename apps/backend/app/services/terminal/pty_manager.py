"""
内置终端 PTY 管理器

通过 PTY (伪终端) 提供交互式 Shell，支持 stdin/stdout/stderr 全双工通信。
每个终端会话对应一个独立的 PTY 子进程。
支持 detach/attach：WebSocket 断开后保留会话，允许重连恢复。
不做超时清理——PTY 进程只在 shell 退出、显式 kill 或后端关闭时终止。

跨平台支持：
- POSIX (Linux/macOS): 标准 openpty + fork/exec
- Windows: pywinpty (ConPTY/WinPTY 后端)
"""

from __future__ import annotations

import asyncio
import logging
import os
import struct
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

IS_POSIX = os.name == "posix"
IS_WINDOWS = os.name == "nt"

if IS_POSIX:
    import fcntl
    import pty
    import termios
else:
    fcntl = None
    pty = None
    termios = None

# Windows: 延迟导入 pywinpty，Linux 上不加载
_WINPTY_AVAILABLE = False
_WinPtyProcess: Any = None

if IS_WINDOWS:
    try:
        from winpty import PtyProcess as _WinPtyProcess

        _WINPTY_AVAILABLE = True
        logger.info("pywinpty 已加载，Windows PTY 可用")
    except ImportError:
        logger.warning("pywinpty 未安装，Windows PTY 不可用。运行: pip install pywinpty")


class PtyUnsupportedError(RuntimeError):
    """当前平台不支持内置 PTY 终端。"""


@dataclass
class PtySession:
    """单个 PTY 会话的状态"""

    terminal_id: str
    pid: int
    master_fd: int | None = None  # POSIX only
    read_task: asyncio.Task | None = None
    cols: int = 80
    rows: int = 24
    _closed: bool = False
    has_interaction: bool = False
    session_key: str = ""
    _on_output: Callable[[bytes], None] | None = None
    _on_exit: Callable[[int], None] | None = None
    # detach 期间缓冲输出，attach 时一次性发送
    _pending_output: list[bytes] | None = None
    # Windows only: pywinpty 进程对象
    _winpty_proc: Any | None = None

    def close(self) -> None:
        """关闭会话，终止进程并清理资源"""
        if self._closed:
            return
        self._closed = True

        if self.read_task and not self.read_task.done():
            self.read_task.cancel()

        if self._winpty_proc is not None:
            # Windows path
            try:
                self._winpty_proc.close()
            except Exception:
                pass
            return

        # POSIX path
        try:
            os.kill(self.pid, 9)
        except (ProcessLookupError, PermissionError, OSError):
            pass

        try:
            if self.master_fd is not None:
                os.close(self.master_fd)
        except OSError:
            pass


class PtyManager:
    """管理所有活跃的 PTY 终端会话"""

    def __init__(self) -> None:
        self._sessions: dict[str, PtySession] = {}
        self._session_index: dict[str, PtySession] = {}
        self._lock = asyncio.Lock()
        self._is_windows = IS_WINDOWS

    def _find_windows_shell(self) -> str:
        """查找 Windows 上可用的 shell，优先 PowerShell。"""
        candidates = [
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            r"C:\Windows\System32\cmd.exe",
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        return "powershell.exe"  # 依赖 PATH

    async def spawn(
        self,
        terminal_id: str,
        rows: int,
        cols: int,
        cwd: str | None = None,
        shell: str = "/bin/bash",
        on_output: Callable[[bytes], None] | None = None,
        on_exit: Callable[[int], None] | None = None,
        session_key: str = "",
    ) -> PtySession:
        """创建一个新的 PTY 会话并启动 shell"""
        if self._is_windows:
            return await self._spawn_windows(
                terminal_id, rows, cols, cwd, shell, on_output, on_exit, session_key
            )
        return await self._spawn_posix(
            terminal_id, rows, cols, cwd, shell, on_output, on_exit, session_key
        )

    async def _spawn_posix(
        self,
        terminal_id: str,
        rows: int,
        cols: int,
        cwd: str | None,
        shell: str,
        on_output: Callable[[bytes], None] | None,
        on_exit: Callable[[int], None] | None,
        session_key: str,
    ) -> PtySession:
        """POSIX 平台 spawn 实现（openpty + fork/exec）"""
        if not IS_POSIX:
            raise PtyUnsupportedError("当前平台不支持 POSIX PTY 终端。")

        async with self._lock:
            if terminal_id in self._sessions:
                existing = self._sessions[terminal_id]
                existing.close()
                del self._sessions[terminal_id]
                if existing.session_key:
                    self._session_index.pop(existing.session_key, None)

        master_fd: int | None = None
        slave_fd: int | None = None
        try:
            if pty is None:
                raise PtyUnsupportedError("当前平台缺少 PTY 模块。")

            master_fd, slave_fd = pty.openpty()

            self._setwinsize(master_fd, rows, cols)

            pid = os.fork()
            if pid == 0:
                os.setsid()
                os.close(master_fd)
                os.dup2(slave_fd, 0)
                os.dup2(slave_fd, 1)
                os.dup2(slave_fd, 2)
                if slave_fd > 2:
                    os.close(slave_fd)

                env = os.environ.copy()
                env["TERM"] = "xterm-256color"
                for key, value in env.items():
                    os.environ[key] = value

                if cwd:
                    try:
                        os.chdir(cwd)
                    except OSError:
                        pass

                os.execv(shell, [shell, "-i"])
                os._exit(1)

            os.close(slave_fd)
            slave_fd = None
            os.set_blocking(master_fd, False)

            session = PtySession(
                terminal_id=terminal_id,
                pid=pid,
                master_fd=master_fd,
                cols=cols,
                rows=rows,
                session_key=session_key,
                _on_output=on_output,
                _on_exit=on_exit,
            )
        except Exception:
            if slave_fd is not None:
                try:
                    os.close(slave_fd)
                except OSError:
                    pass
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except OSError:
                    pass
            raise

        session.read_task = asyncio.create_task(
            self._read_loop_posix(session),
            name=f"pty-read-{terminal_id}",
        )

        session.has_interaction = True

        async with self._lock:
            self._sessions[terminal_id] = session
            if session_key:
                self._session_index[session_key] = session

        logger.info(
            "PTY 启动 (POSIX): terminal_id=%s pid=%d cols=%d rows=%d cwd=%s",
            terminal_id,
            pid,
            cols,
            rows,
            cwd,
        )
        return session

    async def _spawn_windows(
        self,
        terminal_id: str,
        rows: int,
        cols: int,
        cwd: str | None,
        shell: str,
        on_output: Callable[[bytes], None] | None,
        on_exit: Callable[[int], None] | None,
        session_key: str,
    ) -> PtySession:
        """Windows 平台 spawn 实现（pywinpty）"""
        if not _WINPTY_AVAILABLE or _WinPtyProcess is None:
            raise PtyUnsupportedError(
                "Windows 上需要安装 pywinpty 才能使用内置终端。运行: pip install pywinpty"
            )

        async with self._lock:
            if terminal_id in self._sessions:
                existing = self._sessions[terminal_id]
                existing.close()
                del self._sessions[terminal_id]
                if existing.session_key:
                    self._session_index.pop(existing.session_key, None)

        # 未指定或默认 /bin/bash 时，自动查找 Windows shell
        if not shell or shell == "/bin/bash":
            shell = self._find_windows_shell()

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"

        # pywinpty 的 PtyProcess.spawn 在后台线程中启动进程
        loop = asyncio.get_event_loop()
        proc = await loop.run_in_executor(
            None,
            lambda: _WinPtyProcess.spawn(
                shell,
                cwd=cwd or os.getcwd(),
                dimensions=(cols, rows),
                env=env,
            ),
        )

        session = PtySession(
            terminal_id=terminal_id,
            pid=proc.pid,
            master_fd=None,
            cols=cols,
            rows=rows,
            session_key=session_key,
            _on_output=on_output,
            _on_exit=on_exit,
            _winpty_proc=proc,
        )

        session.read_task = asyncio.create_task(
            self._read_loop_windows(session),
            name=f"pty-read-{terminal_id}",
        )

        session.has_interaction = True

        async with self._lock:
            self._sessions[terminal_id] = session
            if session_key:
                self._session_index[session_key] = session

        logger.info(
            "PTY 启动 (Windows): terminal_id=%s pid=%d cols=%d rows=%d cwd=%s shell=%s",
            terminal_id,
            proc.pid,
            cols,
            rows,
            cwd,
            shell,
        )
        return session

    async def write(self, terminal_id: str, data: str) -> bool:
        """向指定终端写入输入数据"""
        session = self._sessions.get(terminal_id)
        if session is None or session._closed:
            return False

        try:
            encoded = data.encode("utf-8")
            if session._winpty_proc is not None:
                # Windows path: pywinpty 的 write 接受 str
                session._winpty_proc.write(data)
            else:
                # POSIX path
                if session.master_fd is None:
                    return False
                os.write(session.master_fd, encoded)
            session.has_interaction = True
            return True
        except OSError as exc:
            logger.warning("PTY 写入失败: terminal_id=%s %s", terminal_id, exc)
            return False

    def resize(self, terminal_id: str, rows: int, cols: int) -> bool:
        """调整终端窗口大小"""
        session = self._sessions.get(terminal_id)
        if session is None or session._closed:
            return False
        try:
            if session._winpty_proc is not None:
                # Windows path: pywinpty 3.0.3+ 使用 setwinsize
                session._winpty_proc.setwinsize(cols, rows)
            else:
                # POSIX path
                if session.master_fd is None:
                    return False
                self._setwinsize(session.master_fd, rows, cols)
            session.rows = rows
            session.cols = cols
            return True
        except OSError as exc:
            logger.warning("PTY resize 失败: terminal_id=%s %s", terminal_id, exc)
            return False

    async def detach(self, terminal_id: str, session_key: str) -> None:
        """分离终端会话：保留进程，输出暂存到 buffer。

        read_task 继续运行，输出收集到 _pending_output buffer。
        attach 时一次性 flush buffer 再绑定新回调。
        """
        async with self._lock:
            session = self._sessions.get(terminal_id)
            if session is None or session._closed:
                return
            session.session_key = session_key
            self._session_index[session_key] = session
            # 启动缓冲模式：不取消 read_task，改为 buffer 输出
            session._pending_output = []

        logger.info("PTY 分离: terminal_id=%s session_key=%s", terminal_id, session_key)

    async def attach(
        self,
        session_key: str,
        on_output: Callable[[bytes], None] | None = None,
        on_exit: Callable[[int], None] | None = None,
    ) -> PtySession | None:
        """附加到已分离的终端会话，flush buffer 并重新绑定回调"""
        async with self._lock:
            session = self._session_index.get(session_key)
            if session is None or session._closed:
                return None

        # flush detach 期间缓冲的输出
        pending = session._pending_output
        session._pending_output = None
        if pending and on_output:
            for chunk in pending:
                on_output(chunk)

        if on_output is not None:
            session._on_output = on_output
        if on_exit is not None:
            session._on_exit = on_exit

        # read_task 在 detach 时未取消，检查是否需要重启
        if session.read_task is None or session.read_task.done():
            if IS_WINDOWS:
                session.read_task = asyncio.create_task(
                    self._read_loop_windows(session),
                    name=f"pty-read-{session.terminal_id}",
                )
            else:
                session.read_task = asyncio.create_task(
                    self._read_loop_posix(session),
                    name=f"pty-read-{session.terminal_id}",
                )

        logger.info("PTY attach: terminal_id=%s pid=%d", session.terminal_id, session.pid)
        return session

    async def kill(self, terminal_id: str) -> bool:
        """终止指定终端会话"""
        async with self._lock:
            session = self._sessions.pop(terminal_id, None)
            if session and session.session_key:
                self._session_index.pop(session.session_key, None)
        if session is None:
            return False
        session.close()
        logger.info("PTY 终止: terminal_id=%s", terminal_id)
        return True

    async def kill_all(self) -> None:
        """终止所有终端会话（用于服务关闭）"""
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._session_index.clear()
        for session in sessions:
            session.close()
        logger.info("PTY 全部终止: count=%d", len(sessions))

    def list_sessions(self) -> list[str]:
        """列出所有活跃的终端 ID"""
        return list(self._sessions.keys())

    def get_session(self, terminal_id: str) -> PtySession | None:
        """获取指定终端会话"""
        return self._sessions.get(terminal_id)

    @staticmethod
    def _setwinsize(fd: int, rows: int, cols: int) -> None:
        if fcntl is None or termios is None:
            raise PtyUnsupportedError("当前平台缺少 PTY 窗口调整能力。")
        size = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, size)

    @staticmethod
    async def _read_loop_posix(session: PtySession) -> None:
        """后台读取循环：从 PTY master fd 读取输出（POSIX）"""
        import select as _select

        loop = asyncio.get_event_loop()
        master_fd = session.master_fd
        if master_fd is None:
            return
        buf_size = 4096

        try:
            while not session._closed:
                try:
                    readable, _, _ = await loop.run_in_executor(
                        None, _select.select, [master_fd], [], [], 0.1
                    )
                    if not readable:
                        await asyncio.sleep(0)
                        continue

                    data = os.read(master_fd, buf_size)
                    if not data:
                        break
                    if session._pending_output is not None:
                        # detach 期间：缓冲输出
                        session._pending_output.append(data)
                    elif session._on_output:
                        session._on_output(data)
                except asyncio.CancelledError:
                    raise
                except OSError as exc:
                    logger.debug("PTY 读取异常: terminal_id=%s %s", session.terminal_id, exc)
                    break
        except asyncio.CancelledError:
            logger.debug("PTY 读取循环被取消: terminal_id=%s", session.terminal_id)
            return

        exit_code = 0
        try:
            _, status = os.waitpid(session.pid, os.WNOHANG)
            if status != 0:
                exit_code = (
                    os.waitstatus_to_exitcode(status)
                    if hasattr(os, "waitstatus_to_exitcode")
                    else 1
                )
        except (ChildProcessError, OSError):
            exit_code = 1

        if session._on_exit and not session._closed:
            try:
                session._on_exit(exit_code)
            except Exception:
                pass

        logger.debug(
            "PTY 读取循环结束 (POSIX): terminal_id=%s exit_code=%d", session.terminal_id, exit_code
        )

    @staticmethod
    async def _read_loop_windows(session: PtySession) -> None:
        """后台读取循环：从 pywinpty 进程读取输出（Windows）"""
        if session._winpty_proc is None:
            return

        proc = session._winpty_proc
        loop = asyncio.get_event_loop()

        try:
            while not session._closed and proc.isalive():
                try:
                    # pywinpty 的 read() 是阻塞的，放到线程池中执行
                    chunk = await loop.run_in_executor(None, proc.read)
                    if not chunk:
                        await asyncio.sleep(0.01)
                        continue

                    # pywinpty v3.0.0+ 返回 str，之前版本可能返回 bytes
                    if isinstance(chunk, str):
                        data = chunk.encode("utf-8", errors="replace")
                    else:
                        data = chunk

                    if session._pending_output is not None:
                        session._pending_output.append(data)
                    elif session._on_output:
                        session._on_output(data)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.debug(
                        "PTY 读取异常 (Windows): terminal_id=%s %s", session.terminal_id, exc
                    )
                    break
        except asyncio.CancelledError:
            logger.debug("PTY 读取循环被取消 (Windows): terminal_id=%s", session.terminal_id)
            return

        exit_code = 0
        try:
            # pywinpty 没有直接提供 exit_code，用 0/1 简化处理
            if not proc.isalive():
                exit_code = 1
        except Exception:
            exit_code = 1

        if session._on_exit and not session._closed:
            try:
                session._on_exit(exit_code)
            except Exception:
                pass

        logger.debug(
            "PTY 读取循环结束 (Windows): terminal_id=%s exit_code=%d",
            session.terminal_id,
            exit_code,
        )


_pty_manager: PtyManager | None = None


def get_pty_manager() -> PtyManager:
    global _pty_manager
    if _pty_manager is None:
        _pty_manager = PtyManager()
    return _pty_manager

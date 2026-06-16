"""跨平台 Shell 执行器。

为 Shell 工具、Monitor 工具、RunCode 等提供统一的子进程创建、输出收集、
超时控制和进程清理能力。把平台差异（POSIX vs Windows、bash vs PowerShell vs cmd、
WSL 路径转换、进程树清理）集中在此模块处理，避免散落在各工具中。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.encoding_utils import smart_decode

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 300
SIGTERM_GRACE_SECONDS = 5
IO_DRAIN_TIMEOUT_SECONDS = 2


@dataclass
class ShellResult:
    """Shell 执行结果。"""

    stdout: str
    stderr: str
    exit_code: int
    output: str = field(init=False)

    def __post_init__(self) -> None:
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append("[stderr]")
            parts.append(self.stderr)
        self.output = "\n".join(parts)


@dataclass
class ShellOptions:
    """Shell 执行选项。"""

    cwd: str | Path | None = None
    env: dict[str, str] | None = None
    timeout: int = DEFAULT_TIMEOUT
    stdin: int = subprocess.DEVNULL
    stdout: Any = subprocess.PIPE
    stderr: Any = subprocess.PIPE
    windows_hide: bool = True


class ShellExecutor:
    """跨平台 Shell 执行器。

    设计原则：
    1. 上层只传命令字符串，执行器负责解释器选择、路径转换、环境合并。
    2. POSIX 优先用 bash/sh；Windows 优先用 Git Bash，其次 WSL，再其次 PowerShell/Cmd。
    3. 超时后执行两阶段 kill：SIGTERM -> grace -> SIGKILL；Windows 用 taskkill /T。
    4. 子进程默认关闭 stdin，避免交互式命令挂起。
    """

    def __init__(self) -> None:
        self._is_windows = os.name == "nt"
        self._git_bash_path: str | None = None
        self._wsl_path: str | None = None

    # -----------------------------------------------------------------------
    # 解释器探测
    # -----------------------------------------------------------------------

    def detect_interpreter(self, interpreter: str = "auto") -> tuple[str, list[str], str]:
        """返回 (shell_path, args_prefix, shell_family)。

        shell_family 用于上层判断是 posix/powershell/cmd/wsl，以便做命令适配。
        """
        result: tuple[str, list[str], str] | None = None

        if interpreter == "bash":
            path = self._find_bash()
            if path:
                result = (path, ["-c"], "posix")
            elif self._is_windows:
                wsl = self._find_wsl_bash()
                if wsl:
                    result = (wsl, ["bash", "-c"], "wsl")
            if result is None:
                raise RuntimeError("系统未找到 bash 或 WSL，无法使用 interpreter='bash'")

        elif interpreter == "powershell":
            if not self._is_windows:
                raise RuntimeError("interpreter='powershell' 仅在 Windows 上可用")
            path = shutil.which("pwsh") or shutil.which("powershell")
            if not path:
                raise RuntimeError("系统未找到 PowerShell（powershell 或 pwsh）")
            result = (path, ["-NoProfile", "-Command"], "powershell")

        elif interpreter == "cmd":
            if not self._is_windows:
                raise RuntimeError("interpreter='cmd' 仅在 Windows 上可用")
            path = shutil.which("cmd") or "cmd.exe"
            result = (path, ["/c"], "cmd")

        elif interpreter != "auto":
            raise ValueError(
                f"不支持的 interpreter: {interpreter}，可选值: auto、bash、cmd、powershell"
            )

        if result is None:
            # auto
            if self._is_windows:
                bash = self._find_git_bash()
                if bash:
                    result = (bash, ["-c"], "posix")
                else:
                    wsl = self._find_wsl_bash()
                    if wsl:
                        result = (wsl, ["bash", "-c"], "wsl")
                    else:
                        ps = shutil.which("pwsh") or shutil.which("powershell")
                        if ps:
                            result = (ps, ["-NoProfile", "-Command"], "powershell")
                        else:
                            result = (shutil.which("cmd") or "cmd.exe", ["/c"], "cmd")
            else:
                bash = shutil.which("bash")
                if bash:
                    result = (bash, ["-c"], "posix")
                else:
                    sh = shutil.which("sh") or "/bin/sh"
                    result = (sh, ["-c"], "posix")

        shell_path, shell_args, shell_family = result
        logger.info(
            "ShellExecutor 解释器探测: interpreter=%s path=%s family=%s",
            interpreter,
            shell_path,
            shell_family,
        )
        return result

    def _find_bash(self) -> str | None:
        return shutil.which("bash")

    def _find_git_bash(self) -> str | None:
        """在 Windows 上查找 Git Bash。

        优先从 git.exe 推断安装位置，再检查固定候选路径和 KIMI_SHELL_PATH 风格覆盖。
        """
        if self._git_bash_path is not None:
            return self._git_bash_path

        # 允许环境变量覆盖（与 Kimi Code 的 KIMI_SHELL_PATH 语义一致）
        override = os.environ.get(
            "AIASYS_SHELL_PATH", os.environ.get("KIMI_SHELL_PATH", "")
        ).strip()
        if override and Path(override).exists():
            self._git_bash_path = override
            return override

        bash = self._find_bash()
        if bash:
            # 简单判断：如果 bash 在 Git 目录下就接受
            lower = bash.lower()
            if "git" in lower and ("bin\\bash.exe" in lower or "usr\\bin\\bash.exe" in lower):
                self._git_bash_path = bash
                return bash

        # 从 git.exe 推断
        git_exe = shutil.which("git")
        if git_exe:
            git_dir = Path(git_exe).parent
            candidates = [
                git_dir.parent / "bin" / "bash.exe",
                git_dir.parent / "usr" / "bin" / "bash.exe",
            ]
            for cand in candidates:
                if cand.exists():
                    self._git_bash_path = str(cand)
                    return self._git_bash_path

            # 通过 git --exec-path 推断（Kimi Code 策略）
            try:
                exec_path = subprocess.check_output(
                    [git_exe, "--exec-path"],
                    text=True,
                    timeout=5,
                    stderr=subprocess.DEVNULL,
                ).strip()
                # exec_path 类似 C:\Program Files\Git\mingw64\libexec\git-core
                parts = Path(exec_path).parts
                for i, part in enumerate(parts):
                    if part.lower() in ("mingw32", "mingw64"):
                        root = Path(*parts[:i])
                        candidates = [
                            root / "bin" / "bash.exe",
                            root / "usr" / "bin" / "bash.exe",
                        ]
                        for cand in candidates:
                            if cand.exists():
                                self._git_bash_path = str(cand)
                                return self._git_bash_path
                        break
            except Exception:
                pass

        # 固定候选路径
        candidates = [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
        ]
        localappdata = os.environ.get("LOCALAPPDATA", "")
        if localappdata:
            candidates.append(rf"{localappdata}\Programs\Git\bin\bash.exe")
            candidates.append(rf"{localappdata}\Programs\Git\usr\bin\bash.exe")

        for cand in candidates:
            if Path(cand).exists():
                self._git_bash_path = cand
                return cand

        return None

    def _find_wsl_bash(self) -> str | None:
        """在 Windows 上查找可用的 WSL bash。

        返回 wsl.exe 路径，调用时通过 `wsl.exe bash -c <command>` 执行。
        """
        if self._wsl_path is not None:
            return self._wsl_path

        wsl_exe = shutil.which("wsl") or shutil.which("wsl.exe")
        if not wsl_exe:
            self._wsl_path = ""
            return None

        try:
            # 快速验证 WSL 是否可用（不启动完整发行版）
            subprocess.run(
                [wsl_exe, "--list", "--quiet"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=True,
            )
            self._wsl_path = wsl_exe
            return wsl_exe
        except Exception:
            self._wsl_path = ""
            return None

    # -----------------------------------------------------------------------
    # 路径转换
    # -----------------------------------------------------------------------

    @staticmethod
    def win_path_to_posix(path: str) -> str:
        r"""把 Windows 绝对路径转成 Git Bash 可接受的 POSIX 风格。

        C:\foo\bar -> /c/foo/bar
        C:/foo/bar -> /c/foo/bar
        \\server\share -> /server/share（MSYS 风格不一定完美，先保留）
        """
        if path.startswith("\\\\"):
            return path.replace("\\", "/")
        match = re.match(r"^([A-Za-z]):([/\\]|$)(.*)$", path)
        if match:
            drive = match.group(1).lower()
            rest = match.group(3).replace("\\", "/")
            if rest and not rest.startswith("/"):
                rest = "/" + rest
            return f"/{drive}{rest}"
        return path.replace("\\", "/")

    @staticmethod
    def win_path_to_wsl(path: str) -> str | None:
        """Windows 绝对路径 -> WSL 挂载路径。"""
        match = re.match(r"^([A-Za-z]):[/\\](.*)$", path)
        if not match:
            return None
        drive = match.group(1).lower()
        rest = match.group(2).replace("\\", "/")
        return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"

    @staticmethod
    def is_wsl() -> bool:
        """当前是否在 WSL 环境。"""
        if os.name != "posix":
            return False
        try:
            with open("/proc/version", "r", encoding="utf-8") as f:
                return "microsoft" in f.read().lower()
        except Exception:
            return False

    @staticmethod
    def rewrite_windows_null_redirect(command: str) -> str:
        r"""把 Windows 风格的 NUL 重定向改写成 POSIX 的 /dev/null。

        例如 `echo x >NUL 2>&1` -> `echo x > /dev/null 2>&1`。
        Git Bash 和 WSL bash 都能识别 /dev/null，但不认 Windows 的 NUL。
        """
        return re.sub(r"(\d?&?>+\s*)[Nn][Uu][Ll](?=\s|$|[|&;)\n])", r"\1/dev/null", command)

    # -----------------------------------------------------------------------
    # 命令执行
    # -----------------------------------------------------------------------

    async def spawn(
        self,
        command: str,
        options: ShellOptions | None = None,
        interpreter: str = "auto",
    ) -> asyncio.subprocess.Process:
        """创建子进程并返回 Process 对象，供调用方自行读取流。"""
        options = options or ShellOptions()
        shell_path, shell_args, shell_family = self.detect_interpreter(interpreter)

        cwd = options.cwd
        if cwd is not None:
            cwd = str(cwd)
            if self._is_windows and shell_family == "posix":
                cwd = self.win_path_to_posix(cwd)
            elif shell_family == "wsl":
                wsl_cwd = self.win_path_to_wsl(cwd)
                if wsl_cwd:
                    cwd = wsl_cwd
            elif self.is_wsl():
                wsl_cwd = self.win_path_to_wsl(cwd)
                if wsl_cwd:
                    cwd = wsl_cwd

        if self._is_windows and shell_family in ("posix", "wsl"):
            command = self.rewrite_windows_null_redirect(command)

        argv = [shell_path, *shell_args, command]
        env = self._build_env(options.env, shell_family)

        logger.debug("ShellExecutor.spawn argv=%s cwd=%s family=%s", argv, cwd, shell_family)

        spawn_kwargs: dict[str, Any] = {
            "stdin": options.stdin,
            "stdout": options.stdout,
            "stderr": options.stderr,
            "cwd": cwd,
            "env": env,
        }
        if self._is_windows:
            spawn_kwargs.update(self._windows_startup_info())
        else:
            # POSIX 上新建会话/进程组，避免 killpg 误伤父进程
            spawn_kwargs["start_new_session"] = True

        return await asyncio.create_subprocess_exec(*argv, **spawn_kwargs)

    async def execute(
        self,
        command: str,
        options: ShellOptions | None = None,
        interpreter: str = "auto",
    ) -> ShellResult:
        """执行命令并等待完成。"""
        options = options or ShellOptions()
        proc = await self.spawn(command, options=options, interpreter=interpreter)

        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                proc.communicate(), timeout=options.timeout
            )
        except asyncio.TimeoutError:
            await self.kill_process_tree(proc)
            raise TimeoutError(f"命令执行超时（{options.timeout}秒），已终止")
        except Exception:
            await self.kill_process_tree(proc)
            raise

        stdout = smart_decode(stdout_data) if stdout_data else ""
        stderr = smart_decode(stderr_data) if stderr_data else ""
        exit_code = proc.returncode if proc.returncode is not None else -1
        return ShellResult(stdout=stdout, stderr=stderr, exit_code=exit_code)

    def _build_env(self, override: dict[str, str] | None, shell_family: str) -> dict[str, str]:
        """构建子进程环境变量。"""
        env = dict(os.environ)
        # 非交互化
        env["NO_COLOR"] = "1"
        env["TERM"] = "dumb"
        env["GIT_TERMINAL_PROMPT"] = env.get("GIT_TERMINAL_PROMPT", "0")
        if self._is_windows:
            env.setdefault("PYTHONIOENCODING", "utf-8")
            env.setdefault("LC_ALL", "C.UTF-8")
            env.setdefault("LANG", "C.UTF-8")
        if override:
            env.update(override)
        return env

    def _windows_startup_info(self) -> dict[str, Any]:
        """Windows 下隐藏子进程窗口的参数。"""
        if not self._is_windows:
            return {}
        # Python 3.10+ 支持 startupinfo 参数；asyncio 会透传给 subprocess.Popen
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            return {"startupinfo": startupinfo}
        except Exception:
            return {}

    # -----------------------------------------------------------------------
    # 进程清理
    # -----------------------------------------------------------------------

    async def kill_process_tree(self, proc: asyncio.subprocess.Process) -> None:
        """终止进程及其子进程。"""
        pid = proc.pid
        if pid is None or pid <= 0:
            return

        if self._is_windows:
            await self._kill_windows_process_tree(pid)
        else:
            await self._kill_posix_process_tree(pid)

        # 确保 asyncio 的 proc 也被回收；如果孙进程持有 stdout/stderr fd 导致 wait 挂起，
        # 加一个 drain timeout 避免无限阻塞。
        try:
            if proc.returncode is None:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=IO_DRAIN_TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    logger.warning("进程 wait 在 kill 后仍超时，放弃回收")
        except Exception:
            pass

    async def _kill_windows_process_tree(self, pid: int) -> None:
        """Windows 用 taskkill /T 终止进程树。"""
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/T",
                "/PID",
                str(pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(killer.wait(), timeout=SIGTERM_GRACE_SECONDS)
            except asyncio.TimeoutError:
                killer.kill()
                try:
                    await killer.wait()
                except Exception:
                    pass
        except Exception as e:
            logger.warning("taskkill /T 失败: %s", e)

        # 如果 taskkill 不生效，强制 /F
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/T",
                "/F",
                "/PID",
                str(pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(killer.wait(), timeout=5)
        except Exception:
            pass

    async def _kill_posix_process_tree(self, pid: int) -> None:
        """POSIX 向进程组发 SIGTERM，grace 后 SIGKILL。"""
        import signal

        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except ProcessLookupError:
            return
        except Exception as e:
            logger.warning("killpg SIGTERM 失败: %s", e)

        # grace 等待
        for _ in range(SIGTERM_GRACE_SECONDS * 10):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            await asyncio.sleep(0.1)

        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.warning("killpg SIGKILL 失败: %s", e)


# 全局默认执行器实例
_default_executor: ShellExecutor | None = None


def get_shell_executor() -> ShellExecutor:
    """获取全局默认 ShellExecutor。"""
    global _default_executor
    if _default_executor is None:
        _default_executor = ShellExecutor()
    return _default_executor

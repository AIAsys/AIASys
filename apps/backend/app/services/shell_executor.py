"""跨平台 Shell 执行器。

为 Shell 工具、Monitor 工具、RunCode 等提供统一的子进程创建、输出收集、
超时控制和进程清理能力。把平台差异（POSIX vs Windows、bash vs PowerShell、
WSL 路径转换、进程树清理）集中在此模块处理，避免散落在各工具中。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR
from app.core.encoding_utils import smart_decode
from app.core.subprocess_utils import subprocess_kwargs

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
    2. POSIX 优先用 bash/sh；Windows 优先用 Git Bash，其次 WSL，再其次 PowerShell（cmd.exe 已禁用）。
    3. 超时后执行两阶段 kill：SIGTERM -> grace -> SIGKILL；Windows 用 taskkill /T。
    4. 子进程默认关闭 stdin，避免交互式命令挂起。
    """

    def __init__(self) -> None:
        self._is_windows = os.name == "nt"
        self._git_bash_path: str | None = None
        self._wsl_path: str | None = None
        self._busybox_path: str | None = None

    # -----------------------------------------------------------------------
    # 解释器探测
    # -----------------------------------------------------------------------

    @staticmethod
    def _normalize_interpreter_alias(name: str) -> str:
        """把常见别名/缩写映射到标准 interpreter 名。"""
        aliases = {
            "sh": "bash",
            "zsh": "bash",
            "ash": "busybox",
            "wsl2": "wsl",
            "pwsh": "powershell",
            "ps": "powershell",
            "ps1": "powershell",
        }
        return aliases.get(name.lower(), name)

    @staticmethod
    def _is_wsl_bash_path(path: str) -> bool:
        """判断给定路径是否为 Windows 内置 WSL bash 启动器。"""
        if os.name != "nt" or not path:
            return False
        lower = path.lower()
        return "windows\\system32\\bash" in lower or "windows\\syswow64\\bash" in lower

    @staticmethod
    def _detect_family_from_name(name: str) -> str | None:
        """根据可执行文件名或路径猜测 shell family。"""
        lower = name.lower()
        if "wsl" in lower:
            return "wsl"
        if lower.endswith("bash.exe") or lower.endswith("bash") or lower.endswith("sh"):
            # busybox 也包含 sh，但前面已特判
            # Windows 内置 WSL bash 按 wsl family 处理
            if ShellExecutor._is_wsl_bash_path(name):
                return "wsl"
            return "posix"
        if "busybox" in lower:
            return "busybox"
        if "powershell" in lower or lower.endswith("pwsh") or lower.endswith("pwsh.exe"):
            return "powershell"
        return None

    def _resolve_custom_interpreter(self, interpreter: str) -> tuple[str, list[str], str] | None:
        """如果传入的是可执行文件路径，则直接解析使用。"""
        candidate = Path(interpreter).expanduser()
        if not candidate.exists():
            # 也尝试在 PATH 中查找相对名/短名
            found = shutil.which(interpreter)
            if found:
                candidate = Path(found)
            else:
                return None

        path = str(candidate)
        family = self._detect_family_from_name(path) or "custom"

        if family == "powershell":
            return (path, ["-NoProfile", "-Command"], family)
        if family == "wsl":
            return (path, ["bash", "-c"], family)
        if family == "busybox":
            return (path, ["sh", "-c"], family)
        # 默认按 POSIX shell 处理
        return (path, ["-c"], family)

    def detect_interpreter(self, interpreter: str = "auto") -> tuple[str, list[str], str]:
        """返回 (shell_path, args_prefix, shell_family)。

        shell_family 用于上层判断是 posix/powershell/wsl，以便做命令适配。
        支持关键字（auto/bash/wsl/busybox/powershell）、常见别名（pwsh/sh/ash）
        以及可执行文件绝对/相对路径。
        """
        result: tuple[str, list[str], str] | None = None
        original = interpreter
        interpreter = self._normalize_interpreter_alias(interpreter)
        name = interpreter.lower()

        if name == "bash":
            path = self._find_bash()
            if path:
                result = (path, ["-c"], "posix")
            elif self._is_windows:
                wsl = self._find_wsl_bash()
                if wsl:
                    result = (wsl, ["bash", "-c"], "wsl")
            if result is None:
                raise RuntimeError("系统未找到 bash 或 WSL，无法使用 interpreter='bash'")

        elif name == "wsl":
            if not self._is_windows:
                raise RuntimeError("interpreter='wsl' 仅在 Windows 上可用")
            wsl = self._find_wsl_bash()
            if not wsl:
                raise RuntimeError("系统未找到 WSL，无法使用 interpreter='wsl'")
            result = (wsl, ["bash", "-c"], "wsl")

        elif name == "busybox":
            busybox = self._find_busybox()
            if not busybox:
                raise RuntimeError("系统未找到 busybox-w32，无法使用 interpreter='busybox'")
            result = (busybox, ["sh", "-c"], "busybox")

        elif name == "powershell":
            if not self._is_windows:
                raise RuntimeError("interpreter='powershell' 仅在 Windows 上可用")
            path = shutil.which("pwsh") or shutil.which("powershell")
            if not path:
                raise RuntimeError("系统未找到 PowerShell（powershell 或 pwsh）")
            result = (path, ["-NoProfile", "-Command"], "powershell")

        elif name == "cmd":
            # cmd.exe 已彻底移除，不接受 cmd 作为解释器。
            # 如果模型传入 cmd，直接降级到 powershell，不执行任何 cmd.exe 调用。
            if not self._is_windows:
                raise RuntimeError("interpreter='cmd' 仅在 Windows 上可用")
            ps = shutil.which("pwsh") or shutil.which("powershell")
            if ps:
                logger.warning("interpreter='cmd' 已移除，自动使用 powershell。")
                result = (ps, ["-NoProfile", "-Command"], "powershell")
            else:
                raise RuntimeError(
                    "interpreter='cmd' 已移除，且系统未找到 PowerShell。"
                    "请安装 PowerShell 或使用 auto/bash/wsl/busybox。"
                )

        elif name != "auto":
            # 尝试作为路径/短名解析
            custom = self._resolve_custom_interpreter(original)
            if custom is None:
                raise ValueError(
                    f"不支持的 interpreter: {original}，"
                    "可选值: auto、bash、wsl、busybox、powershell，"
                    "或传入可执行文件路径"
                )
            result = custom

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
                        busybox = self._find_busybox()
                        if busybox:
                            result = (busybox, ["sh", "-c"], "busybox")
                        else:
                            ps = shutil.which("pwsh") or shutil.which("powershell")
                            if ps:
                                result = (ps, ["-NoProfile", "-Command"], "powershell")
                            else:
                                # Windows 上不使用 cmd.exe。
                                raise RuntimeError(
                                    "Windows 上未找到可用的 shell 解释器。请安装 Git for Windows、WSL、"
                                    "busybox-w32，或确认 PowerShell 已在系统 PATH 中。"
                                )
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

    @staticmethod
    def _find_git_bash_registry() -> str | None:
        """通过 Windows 注册表查找 Git for Windows 安装路径。"""
        if os.name != "nt":
            return None
        try:
            import winreg

            # Git for Windows 在注册表中可能的位置
            keys = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\GitForWindows"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\GitForWindows"),
                (
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Git_is1",
                ),
                (
                    winreg.HKEY_CURRENT_USER,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Git_is1",
                ),
            ]
            for hive, key in keys:
                try:
                    with winreg.OpenKey(hive, key) as reg:
                        install_path, _ = winreg.QueryValueEx(reg, "InstallPath")
                        if install_path:
                            for sub in ("bin", r"usr\bin"):
                                candidate = Path(install_path) / sub / "bash.exe"
                                if candidate.exists():
                                    return str(candidate)
                except OSError:
                    continue
        except Exception:
            pass
        return None

    def _find_bash(self) -> str | None:
        r"""查找非 WSL 的 bash（如 Git Bash、MSYS2 bash）。

        Windows 上 `C:\Windows\System32\bash.exe` 是 WSL 启动器，会被识别为
        wsl family，因此这里不直接返回它。
        """
        path = shutil.which("bash")
        if path and self._is_wsl_bash_path(path):
            return None
        return path

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
                exec_path_bytes = subprocess.check_output(
                    [git_exe, "--exec-path"],
                    timeout=5,
                    stderr=subprocess.DEVNULL,
                    **subprocess_kwargs(),
                )
                exec_path = smart_decode(exec_path_bytes).strip()
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

        # 注册表兜底（处理 git 不在 PATH 但正常安装的情况）
        registry_bash = self._find_git_bash_registry()
        if registry_bash:
            self._git_bash_path = registry_bash
            return registry_bash

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

    def find_git_bash(self) -> str | None:
        """公开接口：查找 Git Bash 路径。"""
        return self._find_git_bash()

    def find_wsl_bash(self) -> str | None:
        """公开接口：查找可用 WSL 路径。"""
        return self._find_wsl_bash()

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
                **subprocess_kwargs(),
            )
            self._wsl_path = wsl_exe
            return wsl_exe
        except Exception:
            self._wsl_path = ""
            return None

    def _find_busybox(self) -> str | None:
        """查找 busybox-w32 可执行文件（优先用户数据目录，再 PATH）。"""
        if self._busybox_path is not None:
            return self._busybox_path if self._busybox_path else None

        default = Path(DATA_DIR) / "tools" / "busybox-w32" / "busybox.exe"
        if default.exists():
            self._busybox_path = str(default)
            return self._busybox_path

        path = shutil.which("busybox") or shutil.which("busybox.exe")
        if path:
            self._busybox_path = path
            return path

        self._busybox_path = ""
        return None

    def find_busybox(self) -> str | None:
        """公开接口：查找 busybox-w32 路径。"""
        return self._find_busybox()

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

        # Windows 上 create_subprocess_exec 最终调用 CreateProcessW，cwd 必须是
        # 原生 Windows 路径。对于 WSL shell，Windows 路径传给 CreateProcessW，
        # 命令前加 cd 切换到 WSL 挂载路径，确保 bash 内部工作目录正确。
        host_cwd: str | None = None
        cwd = options.cwd
        if cwd is not None:
            cwd = str(cwd)
            if shell_family == "wsl":
                # WSL: wsl.exe 是 Windows 可执行文件，host_cwd 用 Windows 原生路径。
                # bash 内部需要 WSL 挂载路径，通过命令前加 cd 显式切换。
                wsl_cwd = self.win_path_to_wsl(cwd)
                if wsl_cwd:
                    command = f"cd {shlex.quote(wsl_cwd)} && {command}"
                host_cwd = cwd
            elif self._is_windows and shell_family == "busybox":
                # busybox-w32 接受 C:/foo/bar 风格，保留驱动器字母
                host_cwd = cwd.replace("\\", "/")
            elif self._is_windows and shell_family == "posix":
                # Git Bash: bash.exe 是 Windows 可执行文件，直接用 Windows 原生路径。
                # 转成 /c/foo/bar 会导致 CreateProcessW 报 WinError 267。
                host_cwd = cwd
            elif self.is_wsl():
                # 后端运行在 WSL 中，cwd 可能是 Windows 路径，转成 WSL 挂载路径
                wsl_cwd = self.win_path_to_wsl(cwd)
                host_cwd = wsl_cwd or cwd
            else:
                # 原生 Linux/macOS，路径直接可用
                host_cwd = cwd

        if self._is_windows and shell_family in ("posix", "wsl", "busybox"):
            command = self.rewrite_windows_null_redirect(command)

        argv = [shell_path, *shell_args, command]
        env = self._build_env(options.env, shell_family)

        logger.debug(
            "ShellExecutor.spawn argv=%s cwd=%s family=%s",
            argv,
            host_cwd,
            shell_family,
        )

        spawn_kwargs: dict[str, Any] = {
            "stdin": options.stdin,
            "stdout": options.stdout,
            "stderr": options.stderr,
            "cwd": host_cwd,
            "env": env,
        }
        if self._is_windows:
            spawn_kwargs.update(self._windows_startup_info())
        else:
            # POSIX 上新建会话/进程组，避免 killpg 误伤父进程
            spawn_kwargs["start_new_session"] = True

        proc = await asyncio.create_subprocess_exec(*argv, **spawn_kwargs)
        return proc

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
            # LC_ALL/LANG 仅对 POSIX shell 有意义；对 cmd 设置反而会在 WSL
            # 或中文环境下造成 stderr 乱码。
            if shell_family in ("posix", "wsl", "busybox"):
                env.setdefault("LC_ALL", "C.UTF-8")
                env.setdefault("LANG", "C.UTF-8")
            # WSL 默认使用 ANSI 代码页输出，设置 UTF-8 可减少中文/路径乱码
            env.setdefault("WSL_UTF8", "1")
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

"""Windows / POSIX shell 环境检测与增强建议。

为「环境增强」面板和 Agent system prompt 提供统一的检测数据，
不集中处理下载/安装逻辑（那部分由前端引导用户到官方源）。
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.core.config import DATA_DIR, RUNTIME_ROOT
from app.core.encoding_utils import smart_decode
from app.core.subprocess_utils import subprocess_kwargs
from app.core.uv_utils import find_uv_binary, get_uv_version
from app.services.shell_executor import ShellExecutor, get_shell_executor
from app.utils.path_utils import as_system_path

logger = logging.getLogger(__name__)

# 可选组件默认下载到用户数据目录，避免污染系统 PATH
_OPTIONAL_TOOLS_DIR = Path(DATA_DIR) / "tools"

# 检测报告 TTL（秒）：避免每次打开面板都重新跑 subprocess/version 检测
_REPORT_CACHE_TTL = 30


class _ReportCache:
    """线程安全的简单 TTL 缓存（后端为单进程，无需锁）。"""

    def __init__(self, ttl: float) -> None:
        self._ttl = ttl
        self._cached: ShellEnvironmentReport | None = None
        self._at = 0.0

    def get(self) -> ShellEnvironmentReport | None:
        if self._cached and (time.monotonic() - self._at) < self._ttl:
            return self._cached
        return None

    def set(self, report: ShellEnvironmentReport) -> None:
        self._cached = report
        self._at = time.monotonic()

    def clear(self) -> None:
        self._cached = None
        self._at = 0.0


_report_cache = _ReportCache(_REPORT_CACHE_TTL)

# 各组件官方下载/项目主页（无镜像时直接使用）
DOWNLOAD_URLS = {
    "git_for_windows": "https://git-scm.com/download/win",
    "busybox_w32": "https://frippery.org/files/busybox/busybox.exe",
    "fnm": "https://github.com/Schniz/fnm",
    "uv": "https://github.com/astral-sh/uv",
    "git": "https://git-scm.com/downloads",
}


@dataclass
class ShellComponentInfo:
    """单个环境组件的状态。"""

    id: str
    name: str
    installed: bool
    path: str | None = None
    version: str | None = None
    description: str = ""
    download_url: str = ""
    license: str = ""
    bundled: bool = False
    optional: bool = False


@dataclass
class ShellEnvironmentReport:
    """完整环境检测报告。"""

    platform: str
    is_windows: bool
    recommended_family: str
    components: list[ShellComponentInfo] = field(default_factory=list)
    guidance: str = ""


def _vendor_platform_dir() -> str:
    """根据当前平台返回 vendor 下的子目录名。"""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows" or os.name == "nt":
        return "windows-x64" if machine in ("amd64", "x86_64") else "win-x64"
    if system == "darwin":
        return "darwin-arm64" if machine in ("arm64", "aarch64") else "darwin-x64"
    return "linux-x64" if machine in ("amd64", "x86_64") else "linux-arm64"


def _find_bundled_fnm() -> str | None:
    """扫描 vendor 目录查找内置 fnm。"""
    candidates = [
        Path(RUNTIME_ROOT) / "vendor" / "node" / _vendor_platform_dir() / "fnm.exe",
        Path(RUNTIME_ROOT) / "vendor" / "node" / _vendor_platform_dir() / "fnm",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _busybox_default_path() -> Path:
    return _OPTIONAL_TOOLS_DIR / "busybox-w32" / "busybox.exe"


def _find_busybox() -> str | None:
    """查找 busybox-w32 可执行文件（优先用户工具目录，再 PATH）。"""
    default = _busybox_default_path()
    if default.exists():
        return str(default)
    path = shutil.which("busybox") or shutil.which("busybox.exe")
    return path if path else None


def _get_version(argv: list[str], pattern: str | None = None, timeout: int = 5) -> str | None:
    """运行命令取第一行输出作为版本信息。"""
    try:
        output = smart_decode(
            subprocess.check_output(
                argv,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                **subprocess_kwargs(),
            )
        ).strip()
        if not output:
            return None
        first = output.splitlines()[0].strip()
        if pattern and pattern.lower() not in first.lower():
            return first
        return first
    except Exception as exc:
        logger.debug("获取版本失败 %s: %s", argv, exc)
        return None


def _detect_git_bash(executor: ShellExecutor) -> ShellComponentInfo:
    path = executor.find_git_bash()
    version = None
    if path:
        version = _get_version([path, "--version"])
    return ShellComponentInfo(
        id="git_bash",
        name="Git Bash",
        installed=bool(path),
        path=path,
        version=version,
        description="Windows 上最完整的 POSIX shell 环境，推荐优先安装。",
        download_url=DOWNLOAD_URLS["git_for_windows"],
        license="GPL-2.0",
        optional=True,
    )


def _detect_wsl(executor: ShellExecutor) -> ShellComponentInfo:
    path = executor.find_wsl_bash()
    version = None
    if path:
        version = _get_version([path, "--version"])
    return ShellComponentInfo(
        id="wsl",
        name="WSL",
        installed=bool(path),
        path=path,
        version=version,
        description="Windows Subsystem for Linux，可在 Windows 上运行原生 Linux 命令。",
        download_url="https://learn.microsoft.com/windows/wsl/install",
        license="GPL-2.0 / 各发行版许可",
        optional=True,
    )


def _detect_busybox() -> ShellComponentInfo:
    path = _find_busybox()
    version = None
    if path:
        version = _get_version([path, "--help"])
    return ShellComponentInfo(
        id="busybox_w32",
        name="busybox-w32",
        installed=bool(path),
        path=path,
        version=version,
        description="轻量级 ash shell fallback（约 1MB），适合临时执行简单 POSIX 命令。",
        download_url=DOWNLOAD_URLS["busybox_w32"],
        license="GPL-2.0",
        optional=True,
    )


def _detect_git() -> ShellComponentInfo:
    path = shutil.which("git")
    version = _get_version([path, "--version"]) if path else None
    return ShellComponentInfo(
        id="git",
        name="Git",
        installed=bool(path),
        path=path,
        version=version,
        description="版本控制工具；Windows 上通常与 Git Bash 一起安装。",
        download_url=DOWNLOAD_URLS["git"],
        license="GPL-2.0",
        optional=True,
    )


def _detect_fnm() -> ShellComponentInfo:
    # 桌面端打包时会通过环境变量注入内置 fnm 路径；探测不到时扫描 vendor 目录
    path = os.environ.get("AIASYS_BUNDLED_FNM_PATH") or shutil.which("fnm") or _find_bundled_fnm()
    version = _get_version([path, "--version"]) if path else None
    return ShellComponentInfo(
        id="fnm",
        name="fnm",
        installed=bool(path),
        path=path,
        version=version,
        description="Fast Node Manager，桌面端已随安装包内置。",
        download_url=DOWNLOAD_URLS["fnm"],
        license="GPL-3.0",
        bundled=True,
        optional=False,
    )


def _detect_uv() -> ShellComponentInfo:
    path = find_uv_binary()
    version = get_uv_version(path) if path else None
    return ShellComponentInfo(
        id="uv",
        name="uv",
        installed=bool(path),
        path=path,
        version=version,
        description="Python 包管理器，桌面端已随安装包内置。",
        download_url=DOWNLOAD_URLS["uv"],
        license="Apache-2.0 OR MIT",
        bundled=True,
        optional=False,
    )


def detect_shell_environment(force: bool = False) -> ShellEnvironmentReport:
    """检测当前系统可用的 shell 环境，返回给前端和 Agent prompt 使用。

    默认缓存 30 秒，避免每次打开面板都重新跑版本检测；
    安装新组件后可传 force=True 立即刷新。
    """
    if not force:
        cached = _report_cache.get()
        if cached is not None:
            return cached

    executor = get_shell_executor()
    is_windows = os.name == "nt"
    plat = platform.system().lower()

    components: list[ShellComponentInfo] = []

    if is_windows:
        components.append(_detect_git_bash(executor))
        components.append(_detect_wsl(executor))
        components.append(_detect_busybox())
        components.append(_detect_git())
        components.append(_detect_fnm())
        components.append(_detect_uv())
    else:
        # POSIX 下只需要关心基础 shell 和 uv/fnm
        bash_path = shutil.which("bash")
        components.append(
            ShellComponentInfo(
                id="bash",
                name="Bash",
                installed=bool(bash_path),
                path=bash_path,
                version=_get_version([bash_path, "--version"]) if bash_path else None,
                description="POSIX 标准 shell。",
                download_url="",
                license="GPL-3.0",
                optional=False,
            )
        )
        components.append(_detect_fnm())
        components.append(_detect_uv())

    recommended_family = _recommend_family(is_windows, components)
    guidance = _build_guidance(is_windows, recommended_family, components)

    report = ShellEnvironmentReport(
        platform=plat,
        is_windows=is_windows,
        recommended_family=recommended_family,
        components=components,
        guidance=guidance,
    )
    _report_cache.set(report)
    return report


def _recommend_family(is_windows: bool, components: list[ShellComponentInfo]) -> str:
    if not is_windows:
        return "posix"

    by_id = {c.id: c for c in components}
    if by_id.get("git_bash") and by_id["git_bash"].installed:
        return "posix"
    if by_id.get("wsl") and by_id["wsl"].installed:
        return "wsl"
    if by_id.get("busybox_w32") and by_id["busybox_w32"].installed:
        return "busybox"
    if shutil.which("pwsh") or shutil.which("powershell"):
        return "powershell"
    # cmd.exe 已禁用，即使无 POSIX shell 也按 powershell 上报，
    # ShellExecutor 会将 cmd 请求降级到 powershell
    return "powershell"


def _build_guidance(is_windows: bool, family: str, components: list[ShellComponentInfo]) -> str:
    by_id = {c.id: c for c in components}
    if family == "posix":
        if is_windows:
            return "当前使用 Git Bash，可直接执行标准 POSIX 命令。"
        return "当前使用标准 POSIX shell，可直接执行 bash/sh 命令。"
    if family == "wsl":
        return "当前使用 WSL；访问 Windows 路径时请注意 /mnt/c/ 挂载转换。"
    if family == "busybox":
        return "当前使用 busybox-w32（ash），仅支持基础 POSIX 命令，避免使用 GNU bash 扩展。"
    if family == "powershell":
        # cmd.exe 已移除，powershell 是 Windows 上的最终回退
        git_bash = by_id.get("git_bash")
        busybox = by_id.get("busybox_w32")
        parts = ["未检测到 POSIX shell，当前回退到 PowerShell；请使用 cmdlet/PS 语法。"]
        if git_bash and not git_bash.installed:
            parts.append("建议安装 Git Bash 以获得完整的 POSIX 支持。")
        if busybox and not busybox.installed:
            parts.append("或下载 busybox-w32 作为轻量 fallback。")
        return " ".join(parts)
    return ""


def get_busybox_default_install_path() -> Path:
    """返回 busybox-w32 建议安装路径（用户数据目录下的 tools/busybox-w32）。"""
    return _busybox_default_path()


async def install_busybox_w32() -> tuple[bool, str]:
    """从官方源下载 busybox-w32 单文件到用户数据目录的工具区。

    返回 (success, message_or_path)。
    """
    url = DOWNLOAD_URLS["busybox_w32"]
    target = _busybox_default_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        target.write_bytes(response.content)

    if os.name != "nt":
        target.chmod(0o755)

    # 安装成功后立即刷新缓存，让面板下次读取时能看到 busybox 已安装
    _report_cache.clear()
    return True, str(target)


async def install_busybox_w32_streamed():
    """流式下载 busybox-w32，yield 进度字典。

    yields dicts: {"type": "progress", "downloaded": N, "total": M}
                  {"type": "done", "path": "..."}
                  {"type": "error", "message": "..."}
    """
    url = DOWNLOAD_URLS["busybox_w32"]
    target = _busybox_default_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                with open(as_system_path(str(target)), "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        yield {
                            "type": "progress",
                            "downloaded": downloaded,
                            "total": total,
                        }

        if os.name != "nt":
            target.chmod(0o755)

        _report_cache.clear()
        yield {"type": "done", "path": str(target)}
    except Exception as exc:
        yield {"type": "error", "message": str(exc)}

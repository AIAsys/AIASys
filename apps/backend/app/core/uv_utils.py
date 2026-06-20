"""uv 工具函数：查找、安装、版本检测。

从 system.py 提取，供 service 层和 API 层复用。
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

from app.core.subprocess_utils import subprocess_kwargs

# 只允许 HTTPS URL 中的安全字符，拒绝可能破坏 shell 单引号包裹的字符
# 拒绝: 单引号(')、双引号(")、反引号(`)、反斜杠(\)、控制字符、空白字符
_SAFE_URL_RE = re.compile(
    r"^https://[a-zA-Z0-9._~:/?#\[\]@!$&()*+,;=%-]+$"
)


def _validate_installer_url(url: str) -> None:
    """验证 installer mirror URL 不含 shell 注入风险字符。"""
    if not _SAFE_URL_RE.match(url):
        raise ValueError(
            f"Installer mirror URL 包含不允许的字符: {url!r}"
        )


def _vendor_platform_dir() -> str:
    """根据当前平台返回 vendor 下的子目录名。"""
    import platform
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows" or os.name == "nt":
        return "windows-x64" if machine in ("amd64", "x86_64") else "win-x64"
    if system == "darwin":
        return "darwin-arm64" if machine in ("arm64", "aarch64") else "darwin-x64"
    return "linux-x64" if machine in ("amd64", "x86_64") else "linux-arm64"


def _find_vendor_uv() -> str | None:
    """扫描 RUNTIME_ROOT/vendor/uv/<platform>/ 目录查找内置 uv。"""
    from app.core.config import RUNTIME_ROOT
    candidates = [
        RUNTIME_ROOT / "vendor" / "uv" / _vendor_platform_dir() / "uv.exe",
        RUNTIME_ROOT / "vendor" / "uv" / _vendor_platform_dir() / "uv",
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


def find_uv_binary() -> str | None:
    """在 PATH 和常见安装位置中查找 uv 可执行文件。

    检测优先级：
    1. 系统 PATH 中的 uv（用户自己安装的，版本更新、已配置镜像）
    2. ~/.cargo/bin/uv、~/.local/bin/uv
    3. AIASYS_BUNDLED_UV_PATH 环境变量（桌面版 Electron 注入的内置 uv）
    4. RUNTIME_ROOT/vendor/uv/<platform>/uv（打包内置后备）
    """
    uv = shutil.which("uv")
    if uv:
        return uv

    home = Path.home()
    candidates: list[Path] = [
        home / ".cargo" / "bin" / "uv",
        home / ".local" / "bin" / "uv",
    ]
    if os.name == "nt":
        candidates.append(home / ".cargo" / "bin" / "uv.exe")

    for p in candidates:
        if p.is_file():
            return str(p)

    bundled = os.environ.get("AIASYS_BUNDLED_UV_PATH")
    if bundled and Path(bundled).is_file():
        return bundled

    return _find_vendor_uv()


def get_uv_version(path: str) -> str | None:
    try:
        completed = subprocess.run(
            [path, "--version"],
            capture_output=True,
            timeout=10,
            check=False,
            **subprocess_kwargs(),
        )
        if completed.returncode == 0:
            from app.core.encoding_utils import smart_decode
            raw = smart_decode(completed.stdout).strip() if completed.stdout else ""
            match = re.search(r"uv\s+(\d+\.\d+\.\d+)", raw)
            if match:
                return match.group(1)
            return raw or None
    except Exception:
        pass
    return None


def is_desktop_mode() -> bool:
    """判断当前是否在桌面版（Electron）环境下运行。"""
    return os.environ.get("AIASYS_DESKTOP_MODE") == "1"


def install_uv(
    installer_mirror: str | None = None,
) -> tuple[bool, str | None, str | None, str]:
    """尝试安装 uv，返回 (是否成功, 路径, 版本, 消息)。

    Args:
        installer_mirror: uv 安装脚本镜像基 URL。非空时替换 astral.sh 下载源，
                          例如 "https://gh.chjina.com/https://github.com/astral-sh"。
    """
    install_sh_url = "https://astral.sh/uv/install.sh"
    install_ps1_url = "https://astral.sh/uv/install.ps1"

    if installer_mirror:
        base = installer_mirror.rstrip("/")
        _validate_installer_url(base)
        # 如果镜像 URL 是 gh-proxy 风格（含完整 GitHub URL path），直接拼接
        if "astral-sh" in base:
            install_sh_url = f"{base}/uv/install.sh"
            install_ps1_url = f"{base}/uv/install.ps1"
        else:
            install_sh_url = f"{base}/uv/install.sh"
            install_ps1_url = f"{base}/uv/install.ps1"
        # 验证拼接后的完整 URL
        _validate_installer_url(install_sh_url)
        _validate_installer_url(install_ps1_url)

    if os.name == "nt":
        command = [
            "powershell",
            "-ExecutionPolicy",
            "ByPass",
            "-c",
            f"irm '{install_ps1_url}' | iex",
        ]
    else:
        command = ["sh", "-c", f"curl -LsSf '{install_sh_url}' | sh"]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=180,
            check=False,
            **subprocess_kwargs(),
        )
    except Exception as exc:
        return False, None, None, f"安装命令执行失败: {exc}"

    from app.core.encoding_utils import smart_decode
    stdout = smart_decode(completed.stdout).strip() if completed.stdout else ""
    stderr = smart_decode(completed.stderr).strip() if completed.stderr else ""

    if completed.returncode != 0:
        detail = stderr or stdout or f"退出码 {completed.returncode}"
        return False, None, None, f"安装失败: {detail}"

    # 安装完成后尝试查找
    path = find_uv_binary()
    version = get_uv_version(path) if path else None
    if path:
        return True, path, version, f"Python 包管理器安装成功 ({version or path})"
    return False, None, None, "安装脚本已执行，但未能找到 uv。可能需要刷新环境变量后重试。"

"""uv 工具函数：查找、安装、版本检测。

从 system.py 提取，供 service 层和 API 层复用。
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _bundled_uv_path() -> Path | None:
    """查找 AIASys 内置的 uv 二进制。

    桌面版打包时会把对应平台的 uv 放到后端 tools/uv 目录，并写入
    AIASYS_BUNDLED_UV_PATH 环境变量。优先使用该版本，避免运行时去网络下载。
    """
    bundled = os.environ.get("AIASYS_BUNDLED_UV_PATH")
    if bundled:
        p = Path(bundled)
        if p.is_file():
            return p

    # 兜底：从当前 Python 解释器所在目录向上查找 tools/uv
    # 覆盖开发模式（venv/bin/python3 与 tools/uv 同级）和打包模式
    try:
        python_dir = Path(sys.executable).resolve().parent
    except Exception:
        return None

    for base in [python_dir, python_dir.parent, python_dir.parent.parent]:
        candidate = base / "tools" / "uv"
        if os.name == "nt":
            candidate = candidate.with_suffix(".exe")
        if candidate.is_file():
            return candidate

    return None


def find_uv_binary() -> str | None:
    """在 PATH、常见安装位置和 AIASys 内置目录中查找 uv 可执行文件。"""
    bundled = _bundled_uv_path()
    if bundled is not None:
        return str(bundled)

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
    return None


def get_uv_version(path: str) -> str | None:
    try:
        completed = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if completed.returncode == 0:
            raw = (completed.stdout or "").strip()
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
        # 如果镜像 URL 是 gh-proxy 风格（含完整 GitHub URL path），直接拼接
        if "astral-sh" in base:
            install_sh_url = f"{base}/uv/install.sh"
            install_ps1_url = f"{base}/uv/install.ps1"
        else:
            install_sh_url = f"{base}/uv/install.sh"
            install_ps1_url = f"{base}/uv/install.ps1"

    if os.name == "nt":
        command = [
            "powershell",
            "-ExecutionPolicy",
            "ByPass",
            "-c",
            f"irm {install_ps1_url} | iex",
        ]
    else:
        command = ["sh", "-c", f"curl -LsSf {install_sh_url} | sh"]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except Exception as exc:
        return False, None, None, f"安装命令执行失败: {exc}"

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    if completed.returncode != 0:
        detail = stderr or stdout or f"退出码 {completed.returncode}"
        return False, None, None, f"安装失败: {detail}"

    # 安装完成后尝试查找
    path = find_uv_binary()
    version = get_uv_version(path) if path else None
    if path:
        return True, path, version, f"Python 包管理器安装成功 ({version or path})"
    return False, None, None, "安装脚本已执行，但未能找到 uv。可能需要刷新环境变量后重试。"

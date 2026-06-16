"""
Vendor 二进制依赖管理。

用于本地开发场景：直接 uvicorn 启动 backend 时，自动检查并补齐
uv / fnm / sqlite-vec 等 vendor 二进制。

桌面版打包时由 apps/desktop/scripts/prepare-runtime.cjs 负责下载；
此处为纯后端开发提供一致的自动兜底能力。
"""

from __future__ import annotations

import logging
import platform
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_platform_slug() -> str | None:
    """将 Python 的 platform 信息映射到项目内部使用的 platform slug。"""
    system = platform.system()
    machine = platform.machine()

    if system == "Darwin":
        if machine == "arm64":
            return "darwin-arm64"
        if machine in ("x86_64", "AMD64"):
            return "darwin-x64"
    elif system == "Linux":
        if machine == "arm64":
            return "linux-arm64"
        if machine in ("x86_64", "AMD64"):
            return "linux-x64"
    elif system == "Windows":
        if machine in ("x86_64", "AMD64", "x64"):
            return "win-x64"

    return None


def _repo_root() -> Path:
    """仓库根目录。"""
    # app/core/vendor_binaries.py -> app/core -> app -> backend -> apps -> AIASys
    return Path(__file__).resolve().parents[4]


def _binary_paths(platform_slug: str) -> dict[str, Path]:
    """返回当前平台下需要检查的 vendor 二进制路径。"""
    repo = _repo_root()
    return {
        "uv": repo / "apps" / "backend" / "vendor" / "uv" / platform_slug / "uv",
        "fnm": repo / "apps" / "backend" / "vendor" / "node" / platform_slug / "fnm",
        "sqlite-vec": repo
        / "apps"
        / "backend"
        / "vendor"
        / "sqlite-vec"
        / _sqlite_vec_subdir(platform_slug)
        / _sqlite_vec_filename(platform_slug),
    }


def _sqlite_vec_subdir(platform_slug: str) -> str:
    mapping = {
        "linux-x64": "linux-x86_64",
        "linux-arm64": "linux-x86_64",
        "darwin-x64": "macos-x86_64",
        "darwin-arm64": "macos-aarch64",
        "win-x64": "windows-x86_64",
    }
    return mapping.get(platform_slug, "")


def _sqlite_vec_filename(platform_slug: str) -> str:
    mapping = {
        "linux-x64": "vec0.so",
        "linux-arm64": "vec0.so",
        "darwin-x64": "vec0.dylib",
        "darwin-arm64": "vec0.dylib",
        "win-x64": "vec0.dll",
    }
    return mapping.get(platform_slug, "")


def _missing_binaries(platform_slug: str) -> list[str]:
    """返回缺失的 vendor 二进制名称列表。"""
    paths = _binary_paths(platform_slug)
    return [name for name, path in paths.items() if not path.exists()]


def ensure_vendor_binaries() -> None:
    """
    检查并补齐当前平台所需的 vendor 二进制。

    如果全部存在则直接返回；如果存在缺失，调用下载脚本统一下载。
    下载失败时记录警告，不阻塞服务启动（部分功能可能不可用）。
    """
    platform_slug = _get_platform_slug()
    if platform_slug is None:
        logger.warning(
            "无法识别当前平台 (%s %s)，跳过 vendor 二进制检查",
            platform.system(),
            platform.machine(),
        )
        return

    missing = _missing_binaries(platform_slug)
    if not missing:
        logger.debug("vendor 二进制已齐全: %s", platform_slug)
        return

    logger.info(
        "检测到 vendor 二进制缺失: %s，尝试自动下载 (%s)",
        ", ".join(missing),
        platform_slug,
    )

    script = _repo_root() / "apps" / "backend" / "scripts" / "download_vendor_binaries.py"
    try:
        result = subprocess.run(
            ["python3", str(script)],
            cwd=_repo_root(),
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            logger.warning(
                "vendor 二进制自动下载失败 (exit %s):\n%s",
                result.returncode,
                result.stderr or result.stdout,
            )
            return

        # 下载后再检查一次
        still_missing = _missing_binaries(platform_slug)
        if still_missing:
            logger.warning(
                "下载脚本执行后仍缺失: %s",
                ", ".join(still_missing),
            )
        else:
            logger.info("vendor 二进制自动下载完成")
    except Exception as e:
        logger.warning("vendor 二进制自动下载异常: %s", e)

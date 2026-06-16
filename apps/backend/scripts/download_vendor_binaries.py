#!/usr/bin/env python3
"""
下载 AIASys backend 所需的 vendor 二进制依赖。

用于本地开发场景（直接 uvicorn 启动 backend，不经过 desktop 的 prepare-runtime）。
会按需下载：
  - uv          -> vendor/uv/<platform>/
  - fnm         -> vendor/node/<platform>/
  - sqlite-vec  -> vendor/sqlite-vec/<platform>/

这些二进制原本由 apps/desktop/scripts/prepare-runtime.cjs 在打包桌面版时下载。
本脚本让纯后端开发也能自动补齐它们。
"""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path


def get_platform_slug() -> str:
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

    raise RuntimeError(f"不支持的平台: {system} {machine}")


def run_node_download_script(script_name: str, platform_slug: str, repo_root: Path) -> None:
    """调用 desktop/scripts 下对应的 node 下载脚本。"""
    script_path = repo_root / "apps" / "desktop" / "scripts" / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"下载脚本不存在: {script_path}")

    cmd = ["node", str(script_path), platform_slug]
    print(f"[vendor] 执行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True)
    if result.returncode != 0:
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        raise RuntimeError(f"{script_name} 执行失败 (exit {result.returncode})")
    print(result.stdout, end="")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    platform_slug = get_platform_slug()

    print(f"[vendor] 平台: {platform_slug}")
    print(f"[vendor] 仓库根目录: {repo_root}")

    scripts = [
        "download-uv-binary.cjs",
        "download-fnm-binary.cjs",
        "download-sqlite-vec-binary.cjs",
    ]

    for script in scripts:
        try:
            run_node_download_script(script, platform_slug, repo_root)
        except Exception as e:
            print(f"[vendor] 失败: {e}", file=sys.stderr)
            return 1

    print("[vendor] 全部 vendor 二进制准备完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())

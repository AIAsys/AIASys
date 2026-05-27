"""
sqlite-vec 扩展加载封装

根据当前操作系统和架构自动选择正确的预编译二进制文件。
"""

import platform
import sqlite3
from pathlib import Path
from typing import Optional

VENDOR_DIR = Path(__file__).resolve().parents[2] / "vendor" / "sqlite-vec"


_EXTENSION_NAMES = {
    ("Linux", "x86_64"): ("linux-x86_64", "vec0.so"),
    ("Linux", "AMD64"): ("linux-x86_64", "vec0.so"),
    ("Darwin", "x86_64"): ("macos-x86_64", "vec0.dylib"),
    ("Darwin", "arm64"): ("macos-aarch64", "vec0.dylib"),
    ("Darwin", "aarch64"): ("macos-aarch64", "vec0.dylib"),
    ("Windows", "x86_64"): ("windows-x86_64", "vec0.dll"),
    ("Windows", "AMD64"): ("windows-x86_64", "vec0.dll"),
}


def _get_extension_path() -> Optional[Path]:
    system = platform.system()
    machine = platform.machine()
    key = (system, machine)
    if key not in _EXTENSION_NAMES:
        return None
    subdir, filename = _EXTENSION_NAMES[key]
    path = VENDOR_DIR / subdir / filename
    if path.exists():
        return path
    return None


def load_vec_extension(conn: sqlite3.Connection) -> None:
    """在 sqlite3 连接上加载 sqlite-vec 扩展。"""
    ext_path = _get_extension_path()
    if ext_path is None:
        system = platform.system()
        machine = platform.machine()
        raise RuntimeError(
            f"sqlite-vec 扩展不支持当前平台: {system} {machine}. "
            f"支持的组合: {list(_EXTENSION_NAMES.keys())}"
        )
    conn.enable_load_extension(True)
    conn.load_extension(str(ext_path))
    conn.enable_load_extension(False)


def ensure_vec_extension(db_path: Path) -> sqlite3.Connection:
    """打开 SQLite 数据库并加载 sqlite-vec 扩展。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    load_vec_extension(conn)
    return conn

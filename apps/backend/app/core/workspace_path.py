"""
WorkspacePath —— Agent 工作区路径抽象。

AIASys 以"工作区"为一等对象；本类为 Agent runtime 层提供统一的工作区路径表示，
底层基于 pathlib.PurePosixPath，保持跨平台一致。

当前系统固定走本地执行链路，因此与本地 ``pathlib.Path`` 的互转无需额外防护。
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any


class WorkspacePath:
    """
    Agent 工作区路径的最小抽象。

    仅覆盖后端实际使用的接口；所有实际文件 I/O 仍由调用方通过
    ``pathlib.Path`` 或 ``aiofiles`` 完成。
    """

    def __init__(self, *args: str) -> None:
        self._path: PurePosixPath = PurePosixPath(*args)

    # ------------------------------------------------------------------
    # 构造/转换
    # ------------------------------------------------------------------
    @classmethod
    def from_local_path(cls, path: Path) -> WorkspacePath:
        """从本地 ``Path`` 创建 ``WorkspacePath``。"""
        return cls(str(path))

    def to_local_path(self) -> Path:
        """转换为本地 ``Path``。"""
        return Path(str(self._path))

    # ------------------------------------------------------------------
    # 比较与哈希
    # ------------------------------------------------------------------
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, WorkspacePath):
            return NotImplemented
        return self._path == other._path

    def __lt__(self, other: WorkspacePath) -> bool:
        return self._path < other._path

    def __le__(self, other: WorkspacePath) -> bool:
        return self._path <= other._path

    def __gt__(self, other: WorkspacePath) -> bool:
        return self._path > other._path

    def __ge__(self, other: WorkspacePath) -> bool:
        return self._path >= other._path

    def __hash__(self) -> int:
        return hash(self._path)

    # ------------------------------------------------------------------
    # 字符串表示
    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return f"WorkspacePath({repr(str(self._path))})"

    def __str__(self) -> str:
        return str(self._path)

    def __fspath__(self) -> str:
        return str(self._path)

    # ------------------------------------------------------------------
    # 路径拼接
    # ------------------------------------------------------------------
    def __truediv__(self, other: str | WorkspacePath) -> WorkspacePath:
        p = other._path if isinstance(other, WorkspacePath) else other
        ret = WorkspacePath()
        ret._path = self._path / p
        return ret

    def joinpath(self, *other: str) -> WorkspacePath:
        ret = WorkspacePath()
        ret._path = self._path.joinpath(*other)
        return ret

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------
    @property
    def name(self) -> str:
        """返回路径的最终组件（文件名）。"""
        return self._path.name

    @property
    def parent(self) -> WorkspacePath:
        """返回父目录。"""
        return WorkspacePath(str(self._path.parent))

    @property
    def parts(self) -> tuple[str, ...]:
        """返回路径各组成部分。"""
        return self._path.parts

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def is_absolute(self) -> bool:
        return self._path.is_absolute()

    def relative_to(self, other: WorkspacePath) -> WorkspacePath:
        """返回从 *other* 到当前路径的相对路径。"""
        relative_path = self._path.relative_to(other._path)
        return WorkspacePath(str(relative_path))

    def canonical(self) -> WorkspacePath:
        """
        规范化路径：绝对化并解析 ``.`` 和 ``..``，但不解析符号链接。
        """
        abs_path = self if self.is_absolute() else WorkspacePath.cwd() / str(self._path)
        normalized = WorkspacePath(str(abs_path._path))
        return normalized

    # ------------------------------------------------------------------
    # 类方法
    # ------------------------------------------------------------------
    @classmethod
    def home(cls) -> WorkspacePath:
        return cls.from_local_path(Path.home())

    @classmethod
    def cwd(cls) -> WorkspacePath:
        return cls.from_local_path(Path.cwd())

    # ------------------------------------------------------------------
    # 扩展
    # ------------------------------------------------------------------
    def expanduser(self) -> WorkspacePath:
        """将首部的 ``~`` 展开为用户主目录。"""
        parts = self._path.parts
        if not parts or parts[0] != "~":
            return self
        home = WorkspacePath.home()
        if len(parts) == 1:
            return home
        return home.joinpath(*parts[1:])

"""Utility functions for Claw platform adapters.

Extracted from vendored hermes_agent/utils.py.
"""

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Union

from app.utils.path_utils import as_system_path


def _preserve_file_mode(path: Path) -> "int | None":
    """Capture the permission bits of *path* if it exists, else None."""
    try:
        system_path = Path(as_system_path(str(path)))
        return stat.S_IMODE(system_path.stat().st_mode) if system_path.exists() else None
    except OSError:
        return None


def _restore_file_mode(path: "str | Path", mode: "int | None") -> None:
    """Re-apply *mode* to *path* after an atomic replace."""
    if mode is None:
        return
    try:
        os.chmod(as_system_path(str(path)), mode)
    except OSError:
        pass


def atomic_json_write(
    path: Union[str, Path],
    data: Any,
    *,
    indent: int = 2,
    **dump_kwargs: Any,
) -> None:
    """Write JSON data to a file atomically.

    Uses temp file + fsync + os.replace to ensure the target file is never
    left in a partially-written state.
    """
    path = Path(path)
    Path(as_system_path(str(path.parent))).mkdir(parents=True, exist_ok=True)

    original_mode = _preserve_file_mode(path)

    fd, tmp_path = tempfile.mkstemp(
        dir=as_system_path(str(path.parent)),
        prefix=f".{path.stem}_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=indent,
                ensure_ascii=False,
                **dump_kwargs,
            )
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, as_system_path(str(path)))
        _restore_file_mode(as_system_path(str(path)), original_mode)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

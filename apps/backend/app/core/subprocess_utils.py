"""Cross-platform subprocess utilities.

Provides a helper to hide console windows on Windows when spawning
subprocesses. Non-Windows platforms are a no-op.
"""

import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    if os.name == "nt":
        from subprocess import STARTUPINFO  # noqa: F811


def _windows_startupinfo() -> Any:
    """Return a STARTUPINFO that hides the console window on Windows."""
    if os.name != "nt":
        return None
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return si
    except Exception:
        return None


def subprocess_kwargs() -> dict:
    """Return kwargs dict to hide console windows on Windows.

    Usage:
        subprocess.run(["cmd"], **subprocess_kwargs(), capture_output=True)
    """
    kwargs: dict = {}
    if os.name == "nt":
        si = _windows_startupinfo()
        if si is not None:
            kwargs["startupinfo"] = si
    return kwargs
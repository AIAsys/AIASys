"""Constants and path helpers for Claw platform adapters.

Extracted from vendored hermes_agent/hermes_constants.py.
"""

import os
from pathlib import Path


def _get_hermes_default_home() -> Path:
    """Return the platform-appropriate default Hermes home directory."""
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "hermes"
    return Path.home() / ".hermes"


def get_hermes_home() -> Path:
    """Return the Hermes home directory (default: platform-appropriate).

    Reads HERMES_HOME env var, falls back to %APPDATA%/hermes on Windows
    or ~/.hermes on other platforms.
    """
    return Path(os.getenv("HERMES_HOME", _get_hermes_default_home()))


def get_hermes_dir(new_subpath: str, old_name: str) -> Path:
    """Resolve a Hermes subdirectory with backward compatibility.

    Args:
        new_subpath: Preferred path relative to HERMES_HOME (e.g. "cache/images").
        old_name: Legacy path relative to HERMES_HOME (e.g. "image_cache").

    Returns:
        Absolute Path — old location if it exists on disk, otherwise the new one.
    """
    home = get_hermes_home()
    old_path = home / old_name
    if old_path.exists():
        return old_path
    return home / new_subpath

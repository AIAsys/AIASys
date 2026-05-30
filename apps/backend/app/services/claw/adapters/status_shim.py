"""Scoped lock helpers for Claw platform adapters.

Extracted from vendored hermes_agent/gateway/status.py.
Provides the lock functions used by FeishuAdapter.
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_LOCKS_DIRNAME = "gateway-locks"
_IS_WINDOWS = sys.platform == "win32"


def _get_default_state_home() -> Path:
    if os.name == "nt":
        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata:
            return Path(localappdata)
    return Path.home() / ".local" / "state"


def _get_lock_dir() -> Path:
    override = os.getenv("HERMES_GATEWAY_LOCK_DIR")
    if override:
        return Path(override)
    state_home = Path(os.getenv("XDG_STATE_HOME", _get_default_state_home()))
    return state_home / "hermes" / _LOCKS_DIRNAME


def _scope_hash(identity: str) -> str:
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _get_scope_lock_path(scope: str, identity: str) -> Path:
    return _get_lock_dir() / f"{scope}-{_scope_hash(identity)}.lock"


def _get_process_start_time(pid: int) -> Optional[int]:
    import platform

    if platform.system() != "Linux":
        return None
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        return int(stat_path.read_text().split()[21])
    except (FileNotFoundError, IndexError, PermissionError, ValueError, OSError):
        return None


def _build_pid_record() -> dict:
    return {
        "pid": os.getpid(),
        "kind": "hermes-gateway",
        "argv": list(sys.argv),
        "start_time": _get_process_start_time(os.getpid()),
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json_file(path: Path) -> Optional[dict[str, Any]]:
    if not path.exists():
        return None
    try:
        raw = path.read_text().strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def acquire_scoped_lock(
    scope: str, identity: str, metadata: Optional[dict[str, Any]] = None
) -> tuple[bool, Optional[dict[str, Any]]]:
    """Acquire a machine-local lock keyed by scope + identity."""
    lock_path = _get_scope_lock_path(scope, identity)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        **_build_pid_record(),
        "scope": scope,
        "identity_hash": _scope_hash(identity),
        "metadata": metadata or {},
        "updated_at": _utc_now_iso(),
    }

    existing = _read_json_file(lock_path)
    if existing is None and lock_path.exists():
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
    if existing:
        try:
            existing_pid = int(existing["pid"])
        except (KeyError, TypeError, ValueError):
            existing_pid = None

        if existing_pid == os.getpid() and existing.get("start_time") == record.get("start_time"):
            _write_json_file(lock_path, record)
            return True, existing

        stale = existing_pid is None
        if not stale:
            try:
                os.kill(existing_pid, 0)
            except (ProcessLookupError, PermissionError):
                stale = True
            else:
                current_start = _get_process_start_time(existing_pid)
                if (
                    existing.get("start_time") is not None
                    and current_start is not None
                    and current_start != existing.get("start_time")
                ):
                    stale = True
                if not stale:
                    try:
                        if sys.platform == "linux":
                            _proc_status = Path(f"/proc/{existing_pid}/status")
                            if _proc_status.exists():
                                for _line in _proc_status.read_text().splitlines():
                                    if _line.startswith("State:"):
                                        _state = _line.split()[1]
                                        if _state in ("T", "t"):
                                            stale = True
                                        break
                    except (OSError, PermissionError):
                        pass
        if stale:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass
        else:
            return False, existing

    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False, _read_json_file(lock_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle)
    except Exception:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return True, None


def release_scoped_lock(scope: str, identity: str) -> None:
    """Release a previously-acquired scope lock when owned by this process."""
    lock_path = _get_scope_lock_path(scope, identity)
    existing = _read_json_file(lock_path)
    if not existing:
        return
    if existing.get("pid") != os.getpid():
        return
    if existing.get("start_time") != _get_process_start_time(os.getpid()):
        return
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass


# write_runtime_status stub — not used by AIASys but referenced by base.py
_UNSET = object()


def write_runtime_status(**kwargs: Any) -> None:
    """No-op stub. AIASys does not use Hermes gateway runtime status."""
    pass

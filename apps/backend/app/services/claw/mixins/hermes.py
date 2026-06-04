"""Claw vendored Hermes runtime import mixin."""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from typing import Iterator

from app.core.config import BASE_DIR


class ClawHermesMixin:
    def _get_repo_root(self) -> Path:
        return BASE_DIR.parent.parent

    def _get_hermes_runtime_root(self) -> Path:
        runtime_root = (
            self._get_repo_root() / "apps" / "backend" / "app" / "vendors" / "hermes_agent"
        )
        if not runtime_root.exists():
            raise RuntimeError(f"未找到 Claw 内置通信运行时目录: {runtime_root}")
        return runtime_root

    @contextlib.contextmanager
    def _hermes_import_scope(self, user_id: str) -> Iterator[None]:
        previous_home = os.environ.get("HERMES_HOME")
        runtime_root = self._get_hermes_runtime_root()
        previous_path = list(sys.path)
        hermes_home = self._get_user_hermes_home(user_id)
        os.environ["HERMES_HOME"] = str(hermes_home)
        if str(runtime_root) not in sys.path:
            sys.path.insert(0, str(runtime_root))
        try:
            yield
        finally:
            if previous_home is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = previous_home
            sys.path[:] = previous_path

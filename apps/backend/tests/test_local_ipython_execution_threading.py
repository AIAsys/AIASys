from pathlib import Path

import pytest

from app.agents.tools.local_ipython_box import (
    LocalIPythonBox,
    LocalIPythonBoxParams,
)
from app.models.runtime_environment import WorkspaceRuntimeEnv
from app.services.history import (
    current_session_id,
    current_session_root,
    current_user_id,
    current_workspace,
)
from app.services.runtime.runtime_execution import RuntimeExecutionPlan


class _FakeClient:
    def execute(self, _code: str) -> str:
        return "msg-1"

    def get_iopub_msg(self, timeout: float | None = None):
        _ = timeout
        return {
            "parent_header": {"msg_id": "msg-1"},
            "msg_type": "status",
            "content": {"execution_state": "idle"},
        }


@pytest.mark.asyncio
async def test_local_ipython_box_offloads_kernel_polling_to_thread(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    logical_workspace_root = tmp_path / "local_default" / "task-alpha"
    session_root = tmp_path / "local_default" / "conversation-alpha"
    logical_workspace_root.mkdir(parents=True, exist_ok=True)
    session_root.mkdir(parents=True, exist_ok=True)

    tokens = {
        "workspace": current_workspace.set(logical_workspace_root),
        "session_root": current_session_root.set(session_root),
        "session_id": current_session_id.set("conversation-alpha"),
        "user_id": current_user_id.set("local_default"),
    }

    called = {"to_thread": False}

    async def fake_to_thread(func, /, *args, **kwargs):
        called["to_thread"] = True
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "app.agents.tools.local_ipython_box.JUPYTER_AVAILABLE",
        True,
    )
    monkeypatch.setattr(
        "app.agents.tools.local_ipython_box.asyncio.to_thread",
        fake_to_thread,
    )
    monkeypatch.setattr(
        LocalIPythonBox,
        "_resolve_runtime_helper_env",
        lambda self: {},
    )
    monkeypatch.setattr(
        LocalIPythonBox,
        "_get_or_create_kernel",
        classmethod(lambda cls, **kwargs: (object(), _FakeClient())),
    )
    monkeypatch.setattr(
        LocalIPythonBox,
        "_init_kernel_env",
        classmethod(lambda cls, client, helper_env=None: None),
    )
    monkeypatch.setattr(
        LocalIPythonBox,
        "_append_execution_record",
        lambda self, **kwargs: None,
    )
    monkeypatch.setattr(
        LocalIPythonBox,
        "_apply_post_execution_policy",
        lambda self, session_id, user_id, notebook_path=None: None,
    )
    monkeypatch.setattr(
        "app.agents.tools.local_ipython_box.resolve_runtime_execution_plan",
        lambda **kwargs: RuntimeExecutionPlan(
            sandbox_mode="local",
            env_id="workspace-default",
            display_name="Workspace UV",
            workspace=logical_workspace_root,
            env=WorkspaceRuntimeEnv(
                env_id="workspace-default",
                kind="uv",
                display_name="Workspace UV",
                material_path=str(logical_workspace_root / "env"),
            ),
        ),
    )

    try:
        tool = LocalIPythonBox()
        result = await tool.invoke(**LocalIPythonBoxParams(code="print('ok')").model_dump())
    finally:
        current_user_id.reset(tokens["user_id"])
        current_session_id.reset(tokens["session_id"])
        current_session_root.reset(tokens["session_root"])
        current_workspace.reset(tokens["workspace"])

    assert called["to_thread"] is True
    assert result.output == "(代码执行成功，无输出)"


@pytest.mark.asyncio
async def test_local_ipython_box_requires_enabled_python_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    logical_workspace_root = tmp_path / "local_default" / "task-plain"
    session_root = tmp_path / "local_default" / "conversation-plain"
    logical_workspace_root.mkdir(parents=True, exist_ok=True)
    session_root.mkdir(parents=True, exist_ok=True)

    tokens = {
        "workspace": current_workspace.set(logical_workspace_root),
        "session_root": current_session_root.set(session_root),
        "session_id": current_session_id.set("conversation-plain"),
        "user_id": current_user_id.set("local_default"),
    }
    called = {"kernel": False}

    monkeypatch.setattr(
        "app.agents.tools.local_ipython_box.JUPYTER_AVAILABLE",
        True,
    )
    monkeypatch.setattr(
        LocalIPythonBox,
        "_get_or_create_kernel",
        classmethod(lambda cls, **kwargs: called.__setitem__("kernel", True)),
    )
    monkeypatch.setattr(
        "app.agents.tools.local_ipython_box.resolve_runtime_execution_plan",
        lambda **kwargs: RuntimeExecutionPlan(
            sandbox_mode="plain_shell",
            env_id=None,
            display_name="未绑定 Python",
            workspace=logical_workspace_root,
            env=None,
        ),
    )

    try:
        tool = LocalIPythonBox()
        result = await tool.invoke(**LocalIPythonBoxParams(code="print('ok')").model_dump())
    finally:
        current_user_id.reset(tokens["user_id"])
        current_session_id.reset(tokens["session_id"])
        current_session_root.reset(tokens["session_root"])
        current_workspace.reset(tokens["workspace"])

    assert result.is_error is True
    assert "未启用 Python 环境" in result.output
    assert called["kernel"] is False

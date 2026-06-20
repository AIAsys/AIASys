"""自动任务 API 路由契约测试。"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import auto_tasks as route_module
from app.models.user import UserInfo
from app.services.auto_tasks import engine as auto_task_engine
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_client(monkeypatch, tmp_path) -> TestClient:
    app = FastAPI()
    app.include_router(route_module.router)
    app.dependency_overrides[route_module.require_auth()] = _build_user
    monkeypatch.setattr(auto_task_engine, "WORKSPACE_DIR", str(tmp_path))
    return TestClient(app)


def _prepare_workspace(
    tmp_path, *, user_id: str = "local_default", workspace_id: str = "ws-auto-task"
) -> WorkspaceRegistryService:
    service = WorkspaceRegistryService(tmp_path)
    service.create_workspace(
        user_id=user_id,
        title="Auto Task Workspace",
        workspace_id=workspace_id,
        initial_conversation_id="conv-1",
    )
    return service


def _patch_registry(monkeypatch, service: WorkspaceRegistryService) -> None:
    """让路由使用的 get_workspace_registry_service 返回指定的 service 实例。"""
    monkeypatch.setattr(route_module, "get_workspace_registry_service", lambda: service)
    monkeypatch.setattr(
        "app.services.auto_tasks.executor.get_workspace_registry_service",
        lambda: service,
    )


_PREFIX = "/auto-tasks"


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


class TestAutoTaskWorkspaceRoutes:
    def test_list_tasks_empty(self, monkeypatch, tmp_path):
        """空工作区返回空任务列表。"""
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_workspace(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.get(f"{_PREFIX}/workspaces/ws-auto-task/tasks")
        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == "ws-auto-task"
        assert data["tasks"] == []

    def test_create_and_get_task(self, monkeypatch, tmp_path):
        """创建任务后能正确读取。"""
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_workspace(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.post(
            f"{_PREFIX}/workspaces/ws-auto-task/tasks",
            json={
                "title": "测试自动任务",
                "prompt": "每天执行一次测试",
                "trigger_type": "interval",
                "trigger_value": "3600",
            },
        )
        assert response.status_code == 200
        task = response.json()
        assert task["title"] == "测试自动任务"
        assert task["prompt"] == "每天执行一次测试"
        assert task["trigger_type"] == "interval"
        assert task["trigger_value"] == "3600"
        assert task["first_run_policy"] == "next_scheduled"
        assert task["status"] == "active"
        task_id = task["task_id"]

        response = client.get(f"{_PREFIX}/workspaces/ws-auto-task/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["task_id"] == task_id

    def test_auto_task_ignores_legacy_budget_stop_field(self, monkeypatch, tmp_path):
        """AutoTask 不再暴露任务级预算停止配置。"""
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_workspace(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.post(
            f"{_PREFIX}/workspaces/ws-auto-task/tasks",
            json={
                "title": "预算字段兼容输入",
                "prompt": "测试旧字段不会成为任务配置",
                "trigger_type": "continuous",
                "trigger_value": "",
                "session_strategy": "bind_session",
                "bind_session_id": "conv-1",
                "stop_on_budget_exhausted": False,
            },
        )

        assert response.status_code == 200
        task = response.json()
        assert "stop_on_budget_exhausted" not in task
        task_id = task["task_id"]

        response = client.put(
            f"{_PREFIX}/workspaces/ws-auto-task/tasks/{task_id}",
            json={"stop_on_budget_exhausted": False, "title": "更新后"},
        )

        assert response.status_code == 200
        task = response.json()
        assert task["title"] == "更新后"
        assert "stop_on_budget_exhausted" not in task

    def test_create_task_missing_prompt(self, monkeypatch, tmp_path):
        """缺少 prompt 时返回 400。"""
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_workspace(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.post(
            f"{_PREFIX}/workspaces/ws-auto-task/tasks",
            json={
                "title": "无 prompt",
                "trigger_type": "interval",
                "trigger_value": "3600",
            },
        )
        assert response.status_code == 422
        assert "prompt" in str(response.json())

    def test_create_task_missing_trigger_value(self, monkeypatch, tmp_path):
        """非 continuous 类型缺少 trigger_value 时返回 400。"""
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_workspace(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.post(
            f"{_PREFIX}/workspaces/ws-auto-task/tasks",
            json={
                "title": "无 trigger_value",
                "prompt": "测试",
                "trigger_type": "interval",
            },
        )
        assert response.status_code == 400
        assert "trigger_value" in response.json()["detail"]

    def test_update_task(self, monkeypatch, tmp_path):
        """更新任务字段后持久化生效。"""
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_workspace(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.post(
            f"{_PREFIX}/workspaces/ws-auto-task/tasks",
            json={
                "title": "旧标题",
                "prompt": "旧指令",
                "trigger_type": "interval",
                "trigger_value": "3600",
            },
        )
        task_id = response.json()["task_id"]

        response = client.put(
            f"{_PREFIX}/workspaces/ws-auto-task/tasks/{task_id}",
            json={
                "title": "新标题",
                "prompt": "新指令",
                "trigger_type": "cron",
                "trigger_value": "0 9 * * *",
            },
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["title"] == "新标题"
        assert updated["prompt"] == "新指令"
        assert updated["trigger_type"] == "cron"
        assert updated["trigger_value"] == "0 9 * * *"

    def test_interval_first_run_policy_controls_next_run(self, monkeypatch, tmp_path):
        """周期任务可以选择立即执行一轮或等待第一个间隔。"""
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_workspace(tmp_path)
        _patch_registry(monkeypatch, service)

        before = datetime.now()
        delayed_response = client.post(
            f"{_PREFIX}/workspaces/ws-auto-task/tasks",
            json={
                "title": "等待间隔",
                "prompt": "等待第一个计划点",
                "trigger_type": "interval",
                "trigger_value": "3600",
                "first_run_policy": "next_scheduled",
            },
        )
        assert delayed_response.status_code == 200
        delayed = delayed_response.json()
        delayed_next_run = _parse_iso(delayed["next_run_at"])
        assert delayed["first_run_policy"] == "next_scheduled"
        assert delayed_next_run >= before + timedelta(seconds=3590)

        immediate_response = client.post(
            f"{_PREFIX}/workspaces/ws-auto-task/tasks",
            json={
                "title": "立即执行一轮",
                "prompt": "先执行一轮",
                "trigger_type": "interval",
                "trigger_value": "3600",
                "first_run_policy": "immediate",
            },
        )
        assert immediate_response.status_code == 200
        immediate = immediate_response.json()
        immediate_next_run = _parse_iso(immediate["next_run_at"])
        assert immediate["first_run_policy"] == "immediate"
        assert immediate_next_run <= datetime.now() + timedelta(seconds=2)

    def test_cron_first_run_policy_controls_next_run(self, monkeypatch, tmp_path):
        """固定时间任务可以选择先跑一轮或等待下一个固定时间。"""
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_workspace(tmp_path)
        _patch_registry(monkeypatch, service)

        immediate_response = client.post(
            f"{_PREFIX}/workspaces/ws-auto-task/tasks",
            json={
                "title": "固定时间立即跑",
                "prompt": "先执行一轮",
                "trigger_type": "cron",
                "trigger_value": "0 9 * * *",
                "first_run_policy": "immediate",
            },
        )
        assert immediate_response.status_code == 200
        immediate = immediate_response.json()
        immediate_next_run = _parse_iso(immediate["next_run_at"])
        assert immediate["first_run_policy"] == "immediate"
        assert immediate_next_run <= datetime.now() + timedelta(seconds=2)

        delayed_response = client.post(
            f"{_PREFIX}/workspaces/ws-auto-task/tasks",
            json={
                "title": "固定时间等待",
                "prompt": "等下一个固定时间",
                "trigger_type": "cron",
                "trigger_value": "0 9 * * *",
                "first_run_policy": "next_scheduled",
            },
        )
        assert delayed_response.status_code == 200
        delayed = delayed_response.json()
        delayed_next_run = _parse_iso(delayed["next_run_at"])
        assert delayed["first_run_policy"] == "next_scheduled"
        assert delayed_next_run > datetime.now()

    def test_continuous_task_forces_immediate_first_run_policy(self, monkeypatch, tmp_path):
        """连续推进不暴露首轮等待语义。"""
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_workspace(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.post(
            f"{_PREFIX}/workspaces/ws-auto-task/tasks",
            json={
                "title": "连续推进",
                "prompt": "持续推进目标",
                "trigger_type": "continuous",
                "trigger_value": "",
                "session_strategy": "bind_session",
                "bind_session_id": "conv-1",
                "first_run_policy": "next_scheduled",
            },
        )

        assert response.status_code == 200
        task = response.json()
        assert task["task_category"] == "continuous"
        assert task["first_run_policy"] == "immediate"
        assert _parse_iso(task["next_run_at"]) <= datetime.now() + timedelta(seconds=2)

    def test_create_task_respects_paused_status(self, monkeypatch, tmp_path):
        """创建时允许先保存为暂停，避免后台立即触发长任务。"""
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_workspace(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.post(
            f"{_PREFIX}/workspaces/ws-auto-task/tasks",
            json={
                "title": "先登记后启动",
                "prompt": "等待人工确认后再执行",
                "trigger_type": "continuous",
                "trigger_value": "",
                "session_strategy": "bind_session",
                "bind_session_id": "conv-1",
                "status": "paused",
            },
        )

        assert response.status_code == 200
        task = response.json()
        assert task["status"] == "paused"
        assert task["next_run_at"] is None

    def test_delete_task(self, monkeypatch, tmp_path):
        """删除任务后列表为空。"""
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_workspace(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.post(
            f"{_PREFIX}/workspaces/ws-auto-task/tasks",
            json={
                "title": "待删除",
                "prompt": "测试",
                "trigger_type": "once",
                "trigger_value": "2026-12-31T23:59:59",
            },
        )
        task_id = response.json()["task_id"]

        response = client.delete(f"{_PREFIX}/workspaces/ws-auto-task/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["deleted"] is True

        response = client.get(f"{_PREFIX}/workspaces/ws-auto-task/tasks")
        assert response.json()["tasks"] == []

    def test_run_task_now_not_found(self, monkeypatch, tmp_path):
        """对不存在的任务执行 run-now 返回 404。"""
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_workspace(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.post(f"{_PREFIX}/workspaces/ws-auto-task/tasks/non-existent/run")
        assert response.status_code == 404

    def test_run_task_now_records_missing_bound_session_as_error(self, monkeypatch, tmp_path):
        """绑定会话缺失时，立即执行不应被记成成功触发。"""
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_workspace(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.post(
            f"{_PREFIX}/workspaces/ws-auto-task/tasks",
            json={
                "title": "缺失会话",
                "prompt": "继续推进目标",
                "trigger_type": "continuous",
                "trigger_value": "",
                "session_strategy": "bind_session",
                "bind_session_id": "missing-session",
                "stop_on_consecutive_errors": 2,
            },
        )
        assert response.status_code == 200
        task_id = response.json()["task_id"]

        response = client.post(f"{_PREFIX}/workspaces/ws-auto-task/tasks/{task_id}/run")
        assert response.status_code == 200
        assert response.json()["result"]["executed"] is False

        response = client.get(f"{_PREFIX}/workspaces/ws-auto-task/tasks/{task_id}")
        task = response.json()
        assert task["fired_count"] == 0
        assert task["consecutive_errors"] == 1
        assert "绑定 Session 不存在" in task["last_error"]
        assert task["last_run_at"] is not None
        assert task["status"] == "active"

        response = client.post(f"{_PREFIX}/workspaces/ws-auto-task/tasks/{task_id}/run")
        assert response.status_code == 200

        response = client.get(f"{_PREFIX}/workspaces/ws-auto-task/tasks/{task_id}")
        task = response.json()
        assert task["fired_count"] == 0
        assert task["consecutive_errors"] == 2
        assert task["status"] == "disabled"

    def test_list_bindable_sessions(self, monkeypatch, tmp_path):
        """列出可绑定 session 返回列表。"""
        client = _build_client(monkeypatch, tmp_path)
        service = _prepare_workspace(tmp_path)
        _patch_registry(monkeypatch, service)

        response = client.get(f"{_PREFIX}/workspaces/ws-auto-task/sessions/bindable")
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data


class TestAutoTaskGlobalRoutes:
    def test_list_all_tasks_empty(self, monkeypatch, tmp_path):
        """全局列表在无任务时返回空。"""
        client = _build_client(monkeypatch, tmp_path)

        response = client.get(f"{_PREFIX}/tasks")
        assert response.status_code == 200
        data = response.json()
        assert data["tasks"] == []

    def test_tasks_summary_empty(self, monkeypatch, tmp_path):
        """全局概览在无任务时返回零值。"""
        client = _build_client(monkeypatch, tmp_path)

        response = client.get(f"{_PREFIX}/tasks/summary")
        assert response.status_code == 200
        data = response.json()
        counts = data["counts"]
        assert counts["total"] == 0
        assert counts["active"] == 0
        assert counts["paused"] == 0
        assert counts["completed"] == 0

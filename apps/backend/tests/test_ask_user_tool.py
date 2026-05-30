"""
AskUser 工具集成测试
"""

import asyncio
from unittest.mock import patch

import pytest
from app.agents.tools.ask_user import (
    AskUserParams,
    AskUserRequest,
    AskUserResponse,
    AskUserStore,
    AskUserType,
    get_ask_user_tool,
    reset_ask_user_tool,
)


@pytest.fixture(autouse=True)
def reset_tool():
    """每个测试前重置工具单例"""
    reset_ask_user_tool()
    yield
    reset_ask_user_tool()


@pytest.fixture
def ask_user_tool():
    """获取 AskUser 工具实例"""
    tool = get_ask_user_tool()
    return tool


@pytest.fixture
def mock_session_context():
    """Mock session_id 和 user_id 上下文"""
    with (
        patch("app.agents.tools.ask_user.tool.current_session_id") as mock_sid,
        patch("app.agents.tools.ask_user.tool.current_user_id") as mock_uid,
    ):
        mock_sid.get.return_value = "test-session"
        mock_uid.get.return_value = "test-user"
        yield


class TestAskUserParams:
    """测试参数模型"""

    def test_select_params(self):
        """单选参数"""
        params = AskUserParams(
            title="选择一个方案",
            message="选择数据库缓存方案？",
            type=AskUserType.SELECT,
            options=[
                {"label": "Redis", "description": "内存缓存"},
                {"label": "无缓存", "description": "直接查询"},
            ],
        )
        assert params.title == "选择一个方案"
        assert len(params.options) == 2
        assert params.type == AskUserType.SELECT

    def test_multi_select_params(self):
        """多选参数"""
        params = AskUserParams(
            title="选择包",
            message="选择要安装的包？",
            type=AskUserType.MULTI_SELECT,
            options=[
                {"label": "pandas"},
                {"label": "numpy"},
            ],
        )
        assert params.type == AskUserType.MULTI_SELECT

    def test_input_params(self):
        """文本输入参数"""
        params = AskUserParams(
            title="文件路径",
            message="输入文件路径？",
            placeholder="/path/to/file",
        )
        assert params.placeholder == "/path/to/file"

    def test_timeout_default(self):
        """默认超时值"""
        params = AskUserParams(title="测试", message="测试?")
        assert params.timeout == 300

    def test_timeout_custom(self):
        """自定义超时值"""
        params = AskUserParams(title="测试", message="测试?", timeout=120)
        assert params.timeout == 120


class TestAskUserTool:
    """测试 AskUser 工具"""

    def test_type_select(self, ask_user_tool):
        """显式指定 select 类型"""
        params = AskUserParams(
            title="测试",
            message="测试?",
            type=AskUserType.SELECT,
            options=[{"label": "A"}, {"label": "B"}],
        )
        assert params.type == AskUserType.SELECT

    def test_type_multi_select(self, ask_user_tool):
        """显式指定 multi_select 类型"""
        params = AskUserParams(
            title="测试",
            message="测试?",
            type=AskUserType.MULTI_SELECT,
            options=[{"label": "A"}, {"label": "B"}],
        )
        assert params.type == AskUserType.MULTI_SELECT

    def test_type_default_confirm(self, ask_user_tool):
        """默认类型为 confirm"""
        params = AskUserParams(title="测试", message="测试?")
        assert params.type == AskUserType.CONFIRM

    def test_build_request(self, ask_user_tool):
        """构建请求 - 使用 AskUserRequest 直接创建"""
        request = AskUserRequest(
            request_id="req-test",
            type=AskUserType.SELECT,
            title="选择一个方案",
            message="选择数据库缓存方案？",
            options=[
                {"label": "Redis", "description": "内存缓存"},
                {"label": "无缓存", "description": "直接查询"},
            ],
            tool_call_id="call-123",
        )
        assert request.type == AskUserType.SELECT
        assert request.title == "选择一个方案"
        assert request.message == "选择数据库缓存方案？"
        assert len(request.options) == 2
        assert request.options[0]["label"] == "Redis"
        assert request.options[0]["description"] == "内存缓存"
        assert request.tool_call_id == "call-123"

    def test_build_request_message_only(self, ask_user_tool):
        """构建请求 - 仅消息"""
        request = AskUserRequest(
            request_id="req-test",
            type=AskUserType.CONFIRM,
            title="确认方案",
            message="方案是否可行？",
            options=[{"label": "确认"}, {"label": "取消"}],
        )
        assert request.title == "确认方案"
        assert request.message == "方案是否可行？"
        assert len(request.options) == 2

    @pytest.mark.asyncio
    async def test_invoke_stream_dismissed(self, ask_user_tool, mock_session_context):
        """流式调用：用户跳过"""
        request_id = None

        async def resolve_later():
            nonlocal request_id
            await asyncio.sleep(0.05)
            tool = get_ask_user_tool()
            await tool.resolve(request_id, approved=False)

        results = []
        async for result in ask_user_tool.invoke_stream(
            title="测试",
            message="确认删除？",
            options=[{"label": "确认"}, {"label": "取消"}],
        ):
            results.append(result)
            # 记录 request_id 从第一个事件的 artifacts
            if result.artifacts:
                import json

                event_data = json.loads(result.artifacts[0]["_streaming_event"]["content"])
                request_id = event_data["request_id"]
                asyncio.create_task(resolve_later())

        assert len(results) == 2
        final = results[1]
        assert final.is_error
        assert "已取消" in final.content

    @pytest.mark.asyncio
    async def test_invoke_stream_timeout(self, ask_user_tool, mock_session_context):
        """流式调用：超时"""
        results = []
        async for result in ask_user_tool.invoke_stream(
            title="测试",
            message="测试超时?",
            timeout=10,
        ):
            results.append(result)

        assert len(results) == 2
        final = results[1]
        assert final.is_error
        assert "超时" in final.content

    @pytest.mark.asyncio
    async def test_resolve_dismissed(self, ask_user_tool, mock_session_context):
        """通过 API resolve 跳过"""
        request = ask_user_tool._build_request(
            title="测试",
            message="测试?",
            options=[{"label": "A"}, {"label": "B"}],
        )

        store = AskUserStore()
        future = store.create_request(request, "test-session", "test-user")

        tool = get_ask_user_tool()
        success = await tool.resolve(request.request_id, approved=False)

        assert success is True
        response = await asyncio.wait_for(future, timeout=1)
        assert response.approved is False
        assert response.value is None

    @pytest.mark.asyncio
    async def test_resolve_with_answers(self, ask_user_tool, mock_session_context):
        """通过 API resolve 返回答案"""
        request = ask_user_tool._build_request(
            title="选择方案",
            message="选哪个?",
            options=[{"label": "A"}, {"label": "B"}],
        )

        store = AskUserStore()
        future = store.create_request(request, "test-session", "test-user")

        tool = get_ask_user_tool()
        success = await tool.resolve(request.request_id, approved=True, value="A")

        assert success is True
        response = await asyncio.wait_for(future, timeout=1)
        assert response.approved is True
        assert response.value == "A"


class TestAskUserStore:
    """测试 AskUserStore"""

    @pytest.fixture(autouse=True)
    def clear_store(self):
        """每个测试前清空 store"""
        store = AskUserStore()
        # 清空所有待处理请求
        for req_id in list(store._requests.keys()):
            store.remove_request(req_id)

    def test_create_and_resolve(self):
        """创建和解析请求"""
        store = AskUserStore()
        request = AskUserRequest(
            request_id="req-1",
            type=AskUserType.SELECT,
            title="测试",
            message="测试?",
            options=[{"label": "A"}],
        )
        future = store.create_request(request, "session-1", "user-1")
        assert store.pending_count == 1

        response = AskUserResponse(request_id="req-1", approved=True, value="A")
        success = store.resolve_request("req-1", response)
        assert success is True

        resolved = future.result()
        assert resolved.approved is True
        assert resolved.value == "A"

    def test_resolve_nonexistent(self):
        """解析不存在的请求"""
        store = AskUserStore()
        response = AskUserResponse(request_id="nonexistent", approved=False)
        success = store.resolve_request("nonexistent", response)
        assert success is False

    def test_cancel_by_session(self):
        """按会话取消"""
        store = AskUserStore()
        req1 = AskUserRequest(request_id="req-1", type=AskUserType.SELECT, title="1", message="1?")
        req2 = AskUserRequest(request_id="req-2", type=AskUserType.SELECT, title="2", message="2?")

        store.create_request(req1, "session-1", "user-1")
        store.create_request(req2, "session-2", "user-1")

        assert store.pending_count == 2

        cancelled = store.cancel_by_session("session-1", "user-1")
        assert cancelled == 1
        assert store.pending_count == 1

    def test_remove_request(self):
        """移除请求"""
        store = AskUserStore()
        request = AskUserRequest(
            request_id="req-1", type=AskUserType.SELECT, title="测试", message="测试?"
        )  # noqa: E501
        store.create_request(request, "session-1", "user-1")

        store.remove_request("req-1")
        assert store.pending_count == 0

    def test_list_pending(self):
        """列出待处理请求"""
        store = AskUserStore()
        req1 = AskUserRequest(request_id="req-1", type=AskUserType.SELECT, title="1", message="1?")
        req2 = AskUserRequest(request_id="req-2", type=AskUserType.INPUT, title="2", message="2?")

        store.create_request(req1, "session-1", "user-1")
        store.create_request(req2, "session-1", "user-2")

        all_pending = store.list_pending()
        assert len(all_pending) == 2

        user1_pending = store.list_pending(user_id="user-1")
        assert len(user1_pending) == 1
        assert user1_pending[0]["request_id"] == "req-1"

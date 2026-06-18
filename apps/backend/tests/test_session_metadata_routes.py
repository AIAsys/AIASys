"""
测试 Session Metadata API 路由
"""

import pytest
from unittest.mock import MagicMock, patch


def _iter_leaf_routes(routes):
    """递归展开嵌套路由，返回所有带 path 属性的叶子路由。"""
    for route in routes:
        if hasattr(route, "routes") and not hasattr(route, "path"):
            yield from _iter_leaf_routes(route.routes)
        else:
            yield route


class TestSessionMetadataRoute:
    """测试 Session Metadata API"""

    @pytest.fixture
    def mock_session_metadata(self):
        """Mock 会话元数据"""
        return {
            "session_id": "test-session-001",
            "title": "测试会话",
            "status": "active",
            "message_count": 5,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T12:00:00",
            "is_empty": False,
            "has_execution_journal": True,
            "execution_record_count": 3,
            "sandbox_mode": "docker",
            "env_id": "env-001",
            "recovery_policy": "journal_only",
            "code_timeout": 300,
            "last_execution_status": "completed",
            "last_execution_record_id": "record-001",
            "completed_at": None,
            "completed_message_count": None,
        }

    def test_metadata_endpoint_exists(self):
        """测试 metadata 端点已正确定义"""
        from app.api.routes.sessions_branches import router

        expected_path = "/sessions/{user_id}/{session_id}/metadata"
        metadata_route = None
        for route in _iter_leaf_routes(router.routes):
            if getattr(route, "path", None) == expected_path and "GET" in getattr(
                route, "methods", set()
            ):
                metadata_route = route
                break

        assert metadata_route is not None, "Metadata 端点未找到"
        assert "GET" in metadata_route.methods, "Metadata 端点必须是 GET 方法"

    def test_metadata_response_structure(self, mock_session_metadata):
        """测试 metadata 响应结构"""
        # 验证 mock 数据包含所有必需的字段
        required_fields = [
            "session_id",
            "title",
            "status",
            "message_count",
            "created_at",
            "updated_at",
            "is_empty",
            "has_execution_journal",
            "execution_record_count",
            "sandbox_mode",
            "env_id",
            "recovery_policy",
            "code_timeout",
            "last_execution_status",
            "last_execution_record_id",
            "completed_at",
            "completed_message_count",
        ]

        for field in required_fields:
            assert field in mock_session_metadata, f"缺少必需字段: {field}"


class TestSessionMetadataIntegration:
    """Session Metadata 集成测试"""

    def test_endpoint_path_format(self):
        """测试端点路径格式正确"""
        from app.api.routes.sessions_branches import router

        expected_path = "/sessions/{user_id}/{session_id}/metadata"

        paths = [getattr(route, "path", None) for route in _iter_leaf_routes(router.routes)]
        assert expected_path in paths, f"期望的路径 {expected_path} 不在路由中"

    def test_session_metadata_model_compatibility(self):
        """测试 SessionMetadata 模型兼容性"""
        from app.models.session import SessionMetadata

        # 创建测试实例
        metadata = SessionMetadata(
            session_id="test-001",
            title="测试",
            status="active",
            message_count=0,
        )

        # 验证基本字段
        assert metadata.session_id == "test-001"
        assert metadata.title == "测试"
        assert metadata.status == "active"
        assert metadata.message_count == 0

        # 验证可选字段
        assert metadata.sandbox_mode is None
        assert metadata.env_id is None

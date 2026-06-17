from app.api.routes.session_database import router as session_database_router


def _iter_leaf_routes(routes):
    """递归展开嵌套路由，返回所有带 path 属性的叶子路由。"""
    for route in routes:
        if hasattr(route, "routes") and not hasattr(route, "path"):
            yield from _iter_leaf_routes(route.routes)
        else:
            yield route


def test_api_router_includes_runtime_session_database_routes() -> None:
    """验证 session-database 路由已注册。

    session_database_router 前缀为 /session-database，
    挂载到 api_router（前缀 /api）后完整路径为 /api/session-database/...
    """
    paths = {
        route.path
        for route in _iter_leaf_routes(session_database_router.routes)
        if hasattr(route, "path")
    }

    assert "/session-database/handles" in paths
    assert "/session-database/query" in paths
    assert "/session-database/execute" in paths

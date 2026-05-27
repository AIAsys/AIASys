from app.api.routes import api_router


def test_api_router_includes_runtime_session_database_routes() -> None:
    paths = {route.path for route in api_router.routes}

    assert "/api/session-database/handles" in paths
    assert "/api/session-database/query" in paths
    assert "/api/session-database/execute" in paths

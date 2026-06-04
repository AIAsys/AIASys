from __future__ import annotations

import pytest
from fastapi.responses import Response
from starlette.requests import Request

from app import main as app_main


def _build_request(path: str, query_string: str = "") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query_string.encode("utf-8"),
        "headers": [],
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_inline_file_preview_response_removes_frame_blocking_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_main.AUTH_CONFIG, "enable_security_headers", True)
    request = _build_request(
        "/api/files/download/local_default/session-demo/sample.pdf",
        "user_id=local_default",
    )

    async def _call_next(_: Request) -> Response:
        return Response(
            content=b"%PDF-1.4",
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'inline; filename="sample.pdf"',
                "X-Frame-Options": "DENY",
                "X-XSS-Protection": "1; mode=block",
                "Content-Security-Policy": "default-src 'self'",
            },
        )

    response = await app_main.security_headers_middleware(request, _call_next)

    assert response.headers["content-disposition"] == 'inline; filename="sample.pdf"'
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "x-frame-options" not in response.headers
    assert "x-xss-protection" not in response.headers
    assert "content-security-policy" not in response.headers


@pytest.mark.asyncio
async def test_attachment_download_keeps_frame_blocking_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_main.AUTH_CONFIG, "enable_security_headers", True)
    request = _build_request(
        "/api/files/download/local_default/session-demo/sample.pdf",
        "user_id=local_default&disposition=attachment",
    )

    async def _call_next(_: Request) -> Response:
        return Response(
            content=b"%PDF-1.4",
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="sample.pdf"',
            },
        )

    response = await app_main.security_headers_middleware(request, _call_next)

    assert response.headers["content-disposition"] == 'attachment; filename="sample.pdf"'
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-xss-protection"] == "1; mode=block"
    assert response.headers["content-security-policy"] == "default-src 'self'"

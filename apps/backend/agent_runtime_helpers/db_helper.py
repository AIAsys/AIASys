"""本地运行态数据库 broker helper。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class RuntimeDatabaseHelperError(RuntimeError):
    """运行态数据库 helper 错误。"""


@dataclass(slots=True)
class RuntimeDatabaseClient:
    base_url: str
    session_token: str
    default_handle: str = ""

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        base = self.base_url.rstrip("/")
        url = f"{base}{path}"
        if query:
            query_pairs = {
                key: value
                for key, value in query.items()
                if value is not None
            }
            if query_pairs:
                url = f"{url}?{urllib.parse.urlencode(query_pairs)}"

        body: bytes | None = None
        headers = {
            "Authorization": f"Bearer {self.session_token}",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeDatabaseHelperError(
                f"数据库 broker 请求失败: {exc.code} {detail or exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeDatabaseHelperError(
                f"无法连接数据库 broker: {exc.reason}"
            ) from exc

        if not raw.strip():
            return None

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeDatabaseHelperError(
                f"数据库 broker 返回了非 JSON 响应: {raw[:200]}"
            ) from exc

    def list_handles(self) -> Any:
        return self._request("GET", "/handles")

    def list_tables(self, handle: str | None = None) -> Any:
        return self._request(
            "GET",
            "/tables",
            query={"handle": handle or self.default_handle},
        )

    def describe_table(self, table_name: str, handle: str | None = None) -> Any:
        return self._request(
            "GET",
            f"/tables/{table_name}",
            query={"handle": handle or self.default_handle},
        )

    def query(
        self,
        sql: str,
        *,
        handle: str | None = None,
        limit: int | None = None,
    ) -> Any:
        return self._request(
            "POST",
            "/query",
            payload={
                "handle": handle or self.default_handle,
                "sql": sql,
                "limit": limit,
            },
        )

    def execute(self, sql: str, *, handle: str | None = None) -> Any:
        return self._request(
            "POST",
            "/execute",
            payload={
                "handle": handle or self.default_handle,
                "sql": sql,
            },
        )


def get_db() -> RuntimeDatabaseClient:
    base_url = os.environ.get("AIASYS_DB_BROKER_URL", "").strip()
    session_token = os.environ.get("AIASYS_DB_SESSION_TOKEN", "").strip()
    default_handle = os.environ.get("AIASYS_DB_DEFAULT_HANDLE", "").strip()

    if not base_url:
        raise RuntimeDatabaseHelperError("缺少 AIASYS_DB_BROKER_URL")
    if not session_token:
        raise RuntimeDatabaseHelperError("缺少 AIASYS_DB_SESSION_TOKEN")

    return RuntimeDatabaseClient(
        base_url=base_url,
        session_token=session_token,
        default_handle=default_handle or "",
    )

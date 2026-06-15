"""
外部 MCP 市场服务

目标不是把某个第三方站点直接塞进产品概念，而是把外部目录源收敛成
AIASys 自己的“外部 MCP 市场”供给层。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Sequence
from urllib.parse import quote

import httpx

from app.models.external_mcp_market import (
    ExternalMCPEnvField,
    ExternalMCPMarketDetailResponse,
    ExternalMCPMarketItem,
    ExternalMCPMarketListResponse,
    ExternalMCPMarketSource,
    ExternalMCPTemplatePreview,
)
from app.models.mcp import MCPServerConfig

logger = logging.getLogger(__name__)


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_text_list(value: Any) -> list[str]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        return []
    result: list[str] = []
    for item in value:
        text = _string_or_none(item)
        if text:
            result.append(text)
    return result


def _sanitize_config_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "external-mcp"


def _truncate_text(value: str | None, limit: int = 1200) -> str | None:
    text = _string_or_none(value)
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


class ExternalMCPMarketAdapter:
    """外部 MCP 市场适配器基类。"""

    source: ExternalMCPMarketSource

    async def list_items(
        self,
        search: str | None,
        page_number: int,
        page_size: int,
    ) -> ExternalMCPMarketListResponse:
        raise NotImplementedError

    async def get_item_detail(self, item_id: str) -> ExternalMCPMarketDetailResponse:
        raise NotImplementedError

    async def build_import_configs(
        self,
        item_id: str,
        *,
        enabled: bool,
        env_overrides: dict[str, str] | None = None,
    ) -> list[MCPServerConfig]:
        raise NotImplementedError


class ModelScopeExternalMCPAdapter(ExternalMCPMarketAdapter):
    """ModelScope OpenAPI 适配器。

    这里只是当前第一个内容源，不代表产品主语。
    """

    _BASE_URL = "https://modelscope.cn/openapi/v1"

    source = ExternalMCPMarketSource(
        source_id="modelscope",
        display_name="ModelScope",
        description="当前通过官方 OpenAPI 接入的外部 MCP 目录源。",
        supports_public_catalog=True,
        supports_account_sync=True,
        requires_token_for_account_sync=True,
    )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._BASE_URL}{path}"
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=json_body,
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "外部 MCP 市场请求失败: %s %s -> %s", method, url, exc.response.status_code
            )
            raise ValueError(f"外部 MCP 市场请求失败: {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            logger.warning("外部 MCP 市场请求异常: %s %s -> %s", method, url, exc)
            raise ValueError("外部 MCP 市场暂时不可访问") from exc

        try:
            payload = response.json()
        except Exception:
            raise ValueError("外部 MCP 市场返回格式异常") from None
        if not payload.get("success", False):
            message = _string_or_none(payload.get("message")) or "外部 MCP 市场返回失败"
            raise ValueError(message)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("外部 MCP 市场返回格式异常")
        return data

    def _build_item_summary(self, raw: dict[str, Any]) -> ExternalMCPMarketItem:
        locales = raw.get("locales") if isinstance(raw.get("locales"), dict) else {}
        zh = locales.get("zh") if isinstance(locales.get("zh"), dict) else {}
        en = locales.get("en") if isinstance(locales.get("en"), dict) else {}
        display_name = (
            _string_or_none(raw.get("chinese_name"))
            or _string_or_none(raw.get("name"))
            or _string_or_none(zh.get("name"))
            or _string_or_none(en.get("name"))
            or _string_or_none(raw.get("id"))
            or "未命名 MCP"
        )
        description = (
            _string_or_none(raw.get("description"))
            or _string_or_none(zh.get("description"))
            or _string_or_none(en.get("description"))
        )
        return ExternalMCPMarketItem(
            source_id=self.source.source_id,
            item_id=str(raw.get("id") or ""),
            display_name=display_name,
            publisher=_string_or_none(raw.get("publisher")),
            description=description,
            logo_url=_string_or_none(raw.get("logo_url")),
            categories=_normalize_text_list(raw.get("categories")),
            tags=_normalize_text_list(raw.get("tags")),
            view_count=raw.get("view_count") if isinstance(raw.get("view_count"), int) else None,
            is_hosted=raw.get("is_hosted") if isinstance(raw.get("is_hosted"), bool) else None,
        )

    def _build_import_name(self, server_key: str) -> str:
        return f"ext_modelscope_{_sanitize_config_name(server_key)}"

    def _resolve_transport_type(
        self,
        payload: dict[str, Any],
    ) -> str | None:
        command = _string_or_none(payload.get("command"))
        if command:
            return "stdio"

        raw_type = _string_or_none(payload.get("type")) or _string_or_none(payload.get("transport"))
        if raw_type in {"streamable-http", "sse"}:
            return raw_type
        if raw_type == "http":
            return "streamable-http"

        if _string_or_none(payload.get("url")):
            return "streamable-http"
        return None

    def _extract_template_payloads(
        self,
        detail_data: dict[str, Any],
    ) -> list[tuple[str, dict[str, Any]]]:
        raw_server_config = detail_data.get("server_config")
        if isinstance(raw_server_config, dict):
            blocks: Sequence[Any] = [raw_server_config]
        elif isinstance(raw_server_config, list):
            blocks = raw_server_config
        else:
            blocks = []

        payloads: list[tuple[str, dict[str, Any]]] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            mcp_servers = block.get("mcpServers") or block.get("mcp_servers")
            if not isinstance(mcp_servers, dict):
                continue
            for server_key, payload in mcp_servers.items():
                if not isinstance(payload, dict):
                    continue
                payloads.append((str(server_key), payload))
        return payloads

    def _build_env_fields(
        self,
        detail_data: dict[str, Any],
        template_payloads: list[tuple[str, dict[str, Any]]],
    ) -> list[ExternalMCPEnvField]:
        env_schema = (
            detail_data.get("env_schema") if isinstance(detail_data.get("env_schema"), dict) else {}
        )
        properties = (
            env_schema.get("properties") if isinstance(env_schema.get("properties"), dict) else {}
        )
        required = {str(item) for item in _normalize_text_list(env_schema.get("required"))}
        defaults: dict[str, str | None] = {}
        for _, payload in template_payloads:
            env_map = payload.get("env") if isinstance(payload.get("env"), dict) else {}
            for key, value in env_map.items():
                defaults.setdefault(str(key), _string_or_none(value) or "")

        field_names = list(
            dict.fromkeys(
                [
                    *properties.keys(),
                    *defaults.keys(),
                    *required,
                ]
            )
        )
        env_fields: list[ExternalMCPEnvField] = []
        for key in field_names:
            prop = properties.get(key) if isinstance(properties.get(key), dict) else {}
            env_fields.append(
                ExternalMCPEnvField(
                    name=key,
                    required=key in required,
                    description=_string_or_none(prop.get("description")),
                    default_value=defaults.get(key),
                )
            )
        return env_fields

    def _build_template_previews(
        self,
        template_payloads: list[tuple[str, dict[str, Any]]],
    ) -> list[ExternalMCPTemplatePreview]:
        previews: list[ExternalMCPTemplatePreview] = []
        for server_key, payload in template_payloads:
            transport_type = self._resolve_transport_type(payload)
            if not transport_type:
                continue
            target = (
                _string_or_none(payload.get("command"))
                if transport_type == "stdio"
                else _string_or_none(payload.get("url"))
            )
            env_keys = sorted(
                str(key)
                for key in (
                    (payload.get("env") or {}).keys()
                    if isinstance(payload.get("env"), dict)
                    else []
                )
            )
            header_keys = sorted(
                str(key)
                for key in (
                    (payload.get("headers") or {}).keys()
                    if isinstance(payload.get("headers"), dict)
                    else []
                )
            )
            previews.append(
                ExternalMCPTemplatePreview(
                    server_key=server_key,
                    import_name=self._build_import_name(server_key),
                    transport_type=transport_type,  # type: ignore[arg-type]
                    target=target,
                    args=_normalize_text_list(payload.get("args")),
                    env_keys=env_keys,
                    header_keys=header_keys,
                )
            )
        return previews

    async def list_items(
        self,
        search: str | None,
        page_number: int,
        page_size: int,
    ) -> ExternalMCPMarketListResponse:
        body: dict[str, Any] = {
            "page_number": page_number,
            "page_size": page_size,
        }
        if _string_or_none(search):
            body["search"] = _string_or_none(search)

        data = await self._request("PUT", "/mcp/servers", json_body=body)
        raw_items = (
            data.get("mcp_server_list") if isinstance(data.get("mcp_server_list"), list) else []
        )
        items = [
            self._build_item_summary(item)
            for item in raw_items
            if isinstance(item, dict) and _string_or_none(item.get("id"))
        ]
        total_count = (
            data.get("total_count") if isinstance(data.get("total_count"), int) else len(items)
        )
        return ExternalMCPMarketListResponse(
            source=self.source,
            items=items,
            total_count=total_count,
            page_number=page_number,
            page_size=page_size,
        )

    async def get_item_detail(self, item_id: str) -> ExternalMCPMarketDetailResponse:
        safe_item_id = quote(item_id, safe="")
        data = await self._request("GET", f"/mcp/servers/{safe_item_id}")
        item = self._build_item_summary(data)
        template_payloads = self._extract_template_payloads(data)
        template_previews = self._build_template_previews(template_payloads)
        env_fields = self._build_env_fields(data, template_payloads)
        can_import = len(template_previews) > 0
        reason = None
        if not can_import:
            reason = "当前公开详情没有可导入模板，可能需要账号态托管链接，或源站尚未提供安装模板。"
        return ExternalMCPMarketDetailResponse(
            source=self.source,
            item=item,
            env_fields=env_fields,
            template_previews=template_previews,
            readme_excerpt=_truncate_text(data.get("readme")),
            can_import=can_import,
            import_disabled_reason=reason,
        )

    async def build_import_configs(
        self,
        item_id: str,
        *,
        enabled: bool,
        env_overrides: dict[str, str] | None = None,
    ) -> list[MCPServerConfig]:
        safe_item_id = quote(item_id, safe="")
        data = await self._request("GET", f"/mcp/servers/{safe_item_id}")
        item = self._build_item_summary(data)
        template_payloads = self._extract_template_payloads(data)
        env_fields = self._build_env_fields(data, template_payloads)
        env_override_map = {
            str(key): str(value)
            for key, value in (env_overrides or {}).items()
            if _string_or_none(key) is not None
        }

        configs: list[MCPServerConfig] = []
        for server_key, payload in template_payloads:
            transport_type = self._resolve_transport_type(payload)
            if not transport_type:
                continue

            env_map = {
                str(key): str(value) if value is not None else ""
                for key, value in (
                    (payload.get("env") or {}).items()
                    if isinstance(payload.get("env"), dict)
                    else []
                )
            }
            for field in env_fields:
                if field.name in env_override_map:
                    env_map[field.name] = env_override_map[field.name]
                elif field.name not in env_map and field.default_value is not None:
                    env_map[field.name] = field.default_value
                elif field.name not in env_map:
                    env_map[field.name] = ""

            headers = {
                str(key): str(value)
                for key, value in (
                    (payload.get("headers") or {}).items()
                    if isinstance(payload.get("headers"), dict)
                    else []
                )
            }

            base_kwargs: dict[str, Any] = {
                "name": self._build_import_name(server_key),
                "type": transport_type,
                "enabled": enabled,
                "description": f"{item.display_name} · 外部 MCP 市场导入（{self.source.display_name}）",
            }
            if transport_type == "stdio":
                base_kwargs["command"] = _string_or_none(payload.get("command"))
                base_kwargs["args"] = _normalize_text_list(payload.get("args"))
                base_kwargs["env"] = env_map
            else:
                base_kwargs["url"] = _string_or_none(payload.get("url"))
                base_kwargs["headers"] = headers
                if env_map:
                    # AIASys 当前 HTTP/SSE 配置也允许保留 env 字段，便于后续统一显示和重导入。
                    base_kwargs["env"] = env_map

            configs.append(MCPServerConfig(**base_kwargs))

        if not configs:
            raise ValueError("当前条目暂不支持无 token 一键导入")
        return configs


class AIASysBuiltinMCPAdapter(ExternalMCPMarketAdapter):
    """AIASys 精选 MCP 适配器 — 提供系统预审过的 MCP 服务器定义。

    Token 等敏感值不进入代码。定义中只声明需要的环境变量（env_schema +
    env_fields），用户导入时在前端填入自己的 token。

    添加新的精选 MCP：在 _CURATED_MCPS 字典中追加一条记录即可。
    """

    source = ExternalMCPMarketSource(
        source_id="aiasys",
        display_name="AIASys 精选",
        description="AIASys 团队预审过的 MCP 服务器，开箱即用。导入时需填入你自己的 API token。",
        supports_public_catalog=True,
        supports_account_sync=False,
        requires_token_for_account_sync=False,
    )

    _CURATED_MCPS: list[dict[str, Any]] = [
        {
            "id": "paddleocr-vl",
            "display_name": "PaddleOCR-VL",
            "publisher": "PaddleOCR",
            "description": "基于 PaddleOCR 视觉语言模型的文档解析 MCP 服务，支持 PDF/图片的版式识别、表格提取和 Markdown 转换。",
            "categories": ["文档解析", "OCR", "AI"],
            "tags": ["paddleocr", "ocr", "layout-parsing", "markdown"],
            "template_previews": [
                {
                    "server_key": "PaddleOCR-VL",
                    "import_name": "paddleocr-vl",
                    "transport_type": "stdio",
                    "target": "uvx",
                    "args": ["--from", "paddleocr-mcp", "paddleocr_mcp"],
                    "env_keys": [
                        "PADDLEOCR_MCP_PIPELINE",
                        "PADDLEOCR_MCP_PPOCR_SOURCE",
                        "PADDLEOCR_MCP_SERVER_URL",
                        "PADDLEOCR_MCP_AISTUDIO_ACCESS_TOKEN",
                    ],
                }
            ],
            "env_fields": [
                {
                    "name": "PADDLEOCR_MCP_PIPELINE",
                    "required": False,
                    "description": "OCR 流水线类型",
                    "default_value": "PaddleOCR-VL",
                },
                {
                    "name": "PADDLEOCR_MCP_PPOCR_SOURCE",
                    "required": False,
                    "description": "PPOCR 数据源",
                    "default_value": "aistudio",
                },
                {
                    "name": "PADDLEOCR_MCP_SERVER_URL",
                    "required": False,
                    "description": "API 服务地址",
                    "default_value": "https://b6cdz14b8ch3q5z1.aistudio-app.com",
                },
                {
                    "name": "PADDLEOCR_MCP_AISTUDIO_ACCESS_TOKEN",
                    "required": True,
                    "description": "AI Studio 访问令牌。前往 https://aistudio.baidu.com/ 获取",
                    "default_value": None,
                },
            ],
            "readme_excerpt": (
                "PaddleOCR-VL MCP 服务器，基于 PaddleOCR 的视觉语言模型。\n\n"
                "安装后 Agent 可通过 MCP 协议调用 OCR 能力：\n"
                "- 版式解析（layout parsing）\n"
                "- 表格识别\n"
                "- PDF/图片转 Markdown\n\n"
                "使用前需前往 AI Studio 获取 Access Token。"
            ),
        },
        {
            "id": "stepfun-search",
            "display_name": "StepFun Search",
            "publisher": "StepFun",
            "description": "阶跃星辰官方搜索 MCP 服务，提供 web_search 全网搜索与 web_fetch 网页内容获取。",
            "categories": ["搜索", "AI"],
            "tags": ["stepfun", "search", "web-search", "mcp"],
            "template_previews": [
                {
                    "server_key": "StepSearch",
                    "import_name": "stepfun-search",
                    "transport_type": "streamable-http",
                    "target": "https://api.stepfun.com/step_plan/v1/mcp/web_search/mcp",
                    "args": [],
                    "env_keys": ["STEPFUN_API_KEY"],
                    "header_keys": ["Authorization"],
                    "headers": {"Authorization": "Bearer ${STEPFUN_API_KEY}"},
                }
            ],
            "env_fields": [
                {
                    "name": "STEPFUN_API_KEY",
                    "required": True,
                    "description": "StepFun 开放平台 API Key（Step Plan 套餐 key），前往 https://platform.stepfun.com 获取",
                    "default_value": None,
                }
            ],
            "readme_excerpt": (
                "StepSearch MCP Server 基于模型上下文协议，为兼容 MCP 的客户端提供阶跃星辰的专业搜索能力。\n\n"
                "支持工具：\n"
                "- web_search：全网信息检索与索引化结果输出\n"
                "- web_fetch：指定 URL 的网页内容抓取与结构化提取\n\n"
                "计费：web_search 每次调用 0.04 元，与 Step Plan 其他用量叠加；web_fetch 不单独计费。\n"
                "使用前需前往阶跃星辰开放平台获取 Step Plan API Key（与普通 API Key 不同）。"
            ),
        },
    ]

    async def list_items(
        self,
        search: str | None,
        page_number: int,
        page_size: int,
    ) -> ExternalMCPMarketListResponse:
        items: list[ExternalMCPMarketItem] = []
        for mcp in self._CURATED_MCPS:
            item = ExternalMCPMarketItem(
                source_id=self.source.source_id,
                item_id=mcp["id"],
                display_name=mcp["display_name"],
                publisher=mcp.get("publisher"),
                description=mcp.get("description"),
                logo_url=mcp.get("logo_url"),
                categories=mcp.get("categories", []),
                tags=mcp.get("tags", []),
                view_count=mcp.get("view_count"),
                is_hosted=mcp.get("is_hosted"),
            )
            items.append(item)

        search_text = _string_or_none(search)
        if search_text:
            tokens = re.split(r"\s+", search_text.lower())
            items = [
                item
                for item in items
                if all(
                    token
                    in f"{item.display_name} {item.description or ''} {' '.join(item.tags)} {' '.join(item.categories)}".lower()
                    for token in tokens
                )
            ]

        total = len(items)
        safe_page = max(page_number, 1)
        safe_size = max(min(page_size, 60), 1)
        start = (safe_page - 1) * safe_size
        paged = items[start : start + safe_size]

        return ExternalMCPMarketListResponse(
            source=self.source,
            items=paged,
            total_count=total,
            page_number=safe_page,
            page_size=safe_size,
        )

    async def get_item_detail(self, item_id: str) -> ExternalMCPMarketDetailResponse:
        match = next((m for m in self._CURATED_MCPS if m["id"] == item_id), None)
        if match is None:
            raise ValueError(f"AIASys 精选 MCP 中不存在: {item_id}")

        item = ExternalMCPMarketItem(
            source_id=self.source.source_id,
            item_id=match["id"],
            display_name=match["display_name"],
            publisher=match.get("publisher"),
            description=match.get("description"),
            logo_url=match.get("logo_url"),
            categories=match.get("categories", []),
            tags=match.get("tags", []),
            view_count=match.get("view_count"),
            is_hosted=match.get("is_hosted"),
        )

        env_fields = [
            ExternalMCPEnvField(
                name=f["name"],
                required=f["required"],
                description=f.get("description"),
                default_value=f.get("default_value"),
            )
            for f in match.get("env_fields", [])
        ]

        template_previews = [
            ExternalMCPTemplatePreview(
                server_key=t["server_key"],
                import_name=t["import_name"],
                transport_type=t["transport_type"],  # type: ignore[arg-type]
                target=t.get("target"),
                args=t.get("args", []),
                env_keys=t.get("env_keys", []),
                header_keys=t.get("header_keys", []),
            )
            for t in match.get("template_previews", [])
        ]

        return ExternalMCPMarketDetailResponse(
            source=self.source,
            item=item,
            env_fields=env_fields,
            template_previews=template_previews,
            readme_excerpt=match.get("readme_excerpt"),
            can_import=True,
            import_disabled_reason=None,
        )

    async def build_import_configs(
        self,
        item_id: str,
        *,
        enabled: bool,
        env_overrides: dict[str, str] | None = None,
    ) -> list[MCPServerConfig]:
        match = next((m for m in self._CURATED_MCPS if m["id"] == item_id), None)
        if match is None:
            raise ValueError(f"AIASys 精选 MCP 中不存在: {item_id}")

        env_override_map = {
            str(key): str(value)
            for key, value in (env_overrides or {}).items()
            if _string_or_none(key) is not None
        }

        configs: list[MCPServerConfig] = []
        for t in match.get("template_previews", []):
            # 合并默认 env 值 + 用户覆盖
            env_map: dict[str, str] = {}
            for f in match.get("env_fields", []):
                default = f.get("default_value")
                if default is not None:
                    env_map[f["name"]] = str(default)
                elif f["required"]:
                    env_map[f["name"]] = ""  # 必填但无默认，用户提供

            # 用户覆盖
            for key, value in env_override_map.items():
                env_map[key] = value

            transport_type = t["transport_type"]
            base_kwargs: dict[str, Any] = {
                "name": t["import_name"],
                "type": transport_type,
                "enabled": enabled,
                "description": f"{match['display_name']} · AIASys 精选",
            }

            if transport_type == "stdio":
                base_kwargs["command"] = t.get("target")
                base_kwargs["args"] = t.get("args", [])
                base_kwargs["env"] = env_map
            else:
                base_kwargs["url"] = t.get("target")
                if env_map:
                    base_kwargs["env"] = env_map
                headers = t.get("headers") or {}
                if headers:
                    base_kwargs["headers"] = dict(headers)

            configs.append(MCPServerConfig(**base_kwargs))

        return configs


class ExternalMCPMarketService:
    """外部 MCP 市场聚合服务。"""

    def __init__(self) -> None:
        aiasys_adapter = AIASysBuiltinMCPAdapter()
        modelscope_adapter = ModelScopeExternalMCPAdapter()
        self._adapters: dict[str, ExternalMCPMarketAdapter] = {
            aiasys_adapter.source.source_id: aiasys_adapter,
            modelscope_adapter.source.source_id: modelscope_adapter,
        }

    def list_sources(self) -> list[ExternalMCPMarketSource]:
        return [adapter.source for adapter in self._adapters.values()]

    def get_adapter(self, source_id: str) -> ExternalMCPMarketAdapter:
        adapter = self._adapters.get(source_id)
        if adapter is None:
            raise ValueError(f"不支持的外部 MCP 市场源: {source_id}")
        return adapter

    async def list_items(
        self,
        source_id: str,
        *,
        search: str | None,
        page_number: int,
        page_size: int,
    ) -> ExternalMCPMarketListResponse:
        adapter = self.get_adapter(source_id)
        return await adapter.list_items(search=search, page_number=page_number, page_size=page_size)

    async def get_item_detail(
        self,
        source_id: str,
        *,
        item_id: str,
    ) -> ExternalMCPMarketDetailResponse:
        adapter = self.get_adapter(source_id)
        return await adapter.get_item_detail(item_id=item_id)

    async def build_import_configs(
        self,
        source_id: str,
        *,
        item_id: str,
        enabled: bool,
        env_overrides: dict[str, str] | None = None,
    ) -> list[MCPServerConfig]:
        adapter = self.get_adapter(source_id)
        return await adapter.build_import_configs(
            item_id=item_id,
            enabled=enabled,
            env_overrides=env_overrides,
        )


_external_mcp_market_service: ExternalMCPMarketService | None = None


def get_external_mcp_market_service() -> ExternalMCPMarketService:
    global _external_mcp_market_service
    if _external_mcp_market_service is None:
        _external_mcp_market_service = ExternalMCPMarketService()
    return _external_mcp_market_service

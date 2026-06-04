"""统一能力注册表服务。"""

from __future__ import annotations

import os
import tomllib
from typing import Any, Iterable, Optional

from app.core.config import SANDBOX_DEFAULT_MODE, _get_config, is_sandbox_mode_enabled
from app.models.capability import (
    CapabilityDescriptor,
    CapabilityEvidenceLevel,
    CapabilityHealthcheck,
    CapabilityKind,
    CapabilityRegistryResponse,
    CapabilitySecretRequirement,
    CapabilityStatus,
    IntegrationMarketItem,
    IntegrationMarketResponse,
    ModeCapabilityPreset,
    ToolCategoryRegistryResponse,
    ToolCategorySummary,
)
from app.services.agent.system_presets import (
    build_system_config_from_preset,
    resolve_system_agent_preset_from_path,
)
from app.services.agent_config.models import AgentMode, get_system_default_config_path
from app.services.capability_catalog import (
    _SYSTEM_INTEGRATION_CATALOG,
    _TOOL_CATEGORY_CAPABILITY_IDS,
    _TOOL_CATEGORY_CATALOG,
    _TOOL_METADATA,
    _parse_bool_env,
    _sanitize_capability_id,
    resolve_tool_category_for_capability_id,
    resolve_tool_category_tool_names,
)
from app.services.llm.mcp_config_service import get_system_default_mcps
from app.services.runtime_tooling import (
    canonicalize_runtime_tool_name,
    probe_runtime_tool,
)


class CapabilityRegistryService:
    """统一 capability registry 聚合服务。"""

    def __init__(self) -> None:
        self._runtime_mcp_tool_descriptors: dict[str, CapabilityDescriptor] = {}

    def _read_agent_tools(
        self,
        mode: AgentMode,
        *,
        sandbox_mode: Optional[str] = None,
    ) -> tuple[str, list[str]]:
        config_path = get_system_default_config_path(mode, sandbox_mode=sandbox_mode)
        preset = resolve_system_agent_preset_from_path(config_path)
        if preset is not None:
            config = build_system_config_from_preset(preset)
            source_ref = preset.config_ref
        else:
            config = tomllib.loads(config_path.read_text(encoding="utf-8")) or {}
            source_ref = str(config_path)
        tools = list(config.get("agent", {}).get("tools", []) or [])
        return source_ref, tools

    def _tool_descriptor(
        self,
        tool_name: str,
        *,
        default_modes: Iterable[str],
        source_config_paths: list[str],
    ) -> CapabilityDescriptor:
        canonical_tool_name = canonicalize_runtime_tool_name(tool_name)
        default_mode_list = list(default_modes)
        metadata = _TOOL_METADATA.get(canonical_tool_name) or _TOOL_METADATA.get(tool_name, {})
        source_kind = (
            "system_preset"
            if source_config_paths
            and all(path.startswith("preset://") for path in source_config_paths)
            else "agent_yaml"
        )
        availability = probe_runtime_tool(canonical_tool_name)
        capability_id = (
            metadata.get("capability_id") or f"native.{_sanitize_capability_id(tool_name)}"
        )
        category_id, category_label = resolve_tool_category_for_capability_id(capability_id)
        kind = metadata.get("kind", CapabilityKind.NATIVE_TOOL)
        provider = metadata.get("provider") or "aiasys"

        healthcheck = CapabilityHealthcheck(
            type="runtime_probe",
            target=tool_name,
            description=(
                "当前运行时已验证该工具可导入。"
                if availability.available
                else f"当前运行时不可导入该工具：{availability.reason}"
            ),
        )

        return CapabilityDescriptor(
            capability_id=capability_id,
            display_name=metadata.get("display_name", tool_name.split(":")[-1]),
            kind=kind,
            provider=provider,
            category_id=category_id,
            category_label=category_label,
            description=metadata.get("description"),
            default_enabled=bool(default_mode_list) and availability.available,
            default_modes=default_mode_list,
            status=(
                CapabilityStatus.ACTIVE if availability.available else CapabilityStatus.DISABLED
            ),
            evidence_level=(
                CapabilityEvidenceLevel.RUNTIME_VERIFIED
                if availability.available
                else CapabilityEvidenceLevel.CONFIG_BACKED
            ),
            config_schema={
                "tool_name": canonical_tool_name,
                "requested_tool_name": tool_name,
                "source": source_kind,
                "source_config_paths": source_config_paths,
                "runtime_available": availability.available,
                "runtime_reason": availability.reason,
                "runtime_detail": availability.detail,
            },
            healthcheck=healthcheck,
        )

    def _mcp_descriptor(self, server) -> CapabilityDescriptor:
        secret_requirements: list[CapabilitySecretRequirement] = []
        if server.headers and "Authorization" in server.headers:
            secret_requirements.append(
                CapabilitySecretRequirement(
                    name="Authorization",
                    location="header",
                    required=True,
                    description="MCP HTTP 鉴权头。",
                )
            )

        return CapabilityDescriptor(
            capability_id=f"mcp.{_sanitize_capability_id(server.name)}",
            display_name=server.name,
            kind=CapabilityKind.MCP_SERVER,
            provider=server.name,
            category_id="mcp",
            category_label="MCP",
            description=server.description,
            default_enabled=bool(server.enabled),
            default_modes=list(server.auto_attach_modes or []),
            status=CapabilityStatus.ACTIVE if server.enabled else CapabilityStatus.DISABLED,
            evidence_level=CapabilityEvidenceLevel.RUNTIME_VERIFIED,
            config_schema={
                "transport_type": server.type,
                "url": server.url,
                "timeout_ms": server.timeout_ms,
                "auto_attach_modes": list(server.auto_attach_modes or []),
                "is_system_default": bool(server.is_system_default),
            },
            secret_requirements=secret_requirements,
            healthcheck=CapabilityHealthcheck(
                type="mcp_connection_test",
                target=server.name,
                description="通过 MCP 连接测试接口验证。",
            ),
        )

    def register_mcp_tools(
        self,
        server_name: str,
        tools: Iterable[Any],
    ) -> list[CapabilityDescriptor]:
        """将运行时 MCP server 工具同步为能力注册表条目。"""
        normalized_server_name = str(server_name or "").strip()
        if not normalized_server_name:
            return []

        server_id = _sanitize_capability_id(normalized_server_name)
        server_prefix = f"mcp.{server_id}."
        for capability_id in list(self._runtime_mcp_tool_descriptors):
            if capability_id.startswith(server_prefix):
                del self._runtime_mcp_tool_descriptors[capability_id]

        descriptors: list[CapabilityDescriptor] = []
        for tool in tools or []:
            if isinstance(tool, dict):
                tool_name = str(tool.get("name") or "").strip()
                description = tool.get("description")
                input_schema = tool.get("inputSchema") or tool.get("input_schema")
            else:
                tool_name = str(getattr(tool, "name", "") or "").strip()
                description = getattr(tool, "description", None)
                input_schema = getattr(tool, "inputSchema", None)

            if not tool_name:
                continue

            descriptor = CapabilityDescriptor(
                capability_id=f"{server_prefix}{_sanitize_capability_id(tool_name)}",
                display_name=tool_name,
                kind=CapabilityKind.MCP_SERVER,
                provider=normalized_server_name,
                category_id="mcp",
                category_label="MCP",
                description=str(description) if description else None,
                default_enabled=True,
                default_modes=[],
                status=CapabilityStatus.ACTIVE,
                evidence_level=CapabilityEvidenceLevel.RUNTIME_VERIFIED,
                config_schema={
                    "source": f"mcp:{normalized_server_name}",
                    "server_name": normalized_server_name,
                    "tool_name": tool_name,
                    "input_schema": input_schema
                    or {
                        "type": "object",
                        "properties": {},
                    },
                },
                healthcheck=CapabilityHealthcheck(
                    type="mcp_connection_test",
                    target=f"{normalized_server_name}:{tool_name}",
                    description="通过 MCP 运行时 list_tools 结果登记。",
                ),
            )
            self._runtime_mcp_tool_descriptors[descriptor.capability_id] = descriptor
            descriptors.append(descriptor)

        return descriptors

    def _build_integration_market_item(
        self,
        catalog: dict[str, Any],
    ) -> IntegrationMarketItem:
        config = _get_config(catalog["config_path"], {}) or {}
        if not isinstance(config, dict):
            config = {}

        enabled = _parse_bool_env(
            catalog["enable_env"],
            bool(config.get("enabled", False)),
        )
        secret_value = os.getenv(catalog["secret_env"]) or config.get("api_key", "")
        configured = bool(str(secret_value).strip())

        if enabled and configured:
            activation_state = "ready"
            activation_message = "当前部署已启用且完成最小密钥配置。"
            evidence_level = CapabilityEvidenceLevel.RUNTIME_VERIFIED
        elif enabled and not configured:
            activation_state = "needs_secret"
            activation_message = "当前部署已开启该集成，但仍缺少必需密钥配置。"
            evidence_level = CapabilityEvidenceLevel.CONFIG_BACKED
        else:
            activation_state = "disabled"
            activation_message = "当前部署未启用该集成。"
            evidence_level = CapabilityEvidenceLevel.DECLARED

        url = (
            os.getenv(catalog.get("url_env", ""))
            or config.get("url")
            or catalog.get("default_url", "")
        )
        url_env = catalog.get("url_env")
        timeout_env = catalog.get("timeout_env")
        timeout_ms_raw = (
            os.getenv(str(timeout_env or ""))
            or config.get("timeout_ms")
            or catalog["default_timeout_ms"]
        )
        try:
            timeout_ms = int(timeout_ms_raw)
        except (TypeError, ValueError):
            timeout_ms = int(catalog["default_timeout_ms"])

        return IntegrationMarketItem(
            capability_id=catalog["capability_id"],
            display_name=catalog["display_name"],
            kind=catalog["kind"],
            provider=catalog["provider"],
            description=config.get("description") or catalog["description"],
            status=catalog["status"],
            evidence_level=evidence_level,
            default_modes=list(catalog.get("default_modes") or []),
            config_schema={
                "transport_type": "streamable-http",
                "url": url,
                "timeout_ms": timeout_ms,
                "config_path": catalog["config_path"],
                "env_vars": {
                    "enabled": catalog["enable_env"],
                    "secret": catalog["secret_env"],
                    "url": url_env,
                    "timeout_ms": timeout_env,
                },
                "management": {
                    "configure_entry": catalog.get("configure_entry", "global_mcp_config"),
                    "secret_entry": catalog.get("secret_entry", "deploy_env"),
                    "supports_healthcheck": bool(catalog.get("supports_healthcheck", False)),
                    "change_effect": "next_execution_session_recreate",
                    "supports_hot_reload": False,
                    "requires_service_reload_for_secret": True,
                },
            },
            secret_requirements=[
                CapabilitySecretRequirement(
                    name="Authorization",
                    location="header",
                    required=True,
                    description="API 密钥组装 Bearer 鉴权头。",
                )
            ],
            healthcheck=CapabilityHealthcheck(
                type="mcp_connection_test",
                target=catalog["display_name"],
                description="通过 MCP 连接测试接口验证。",
            ),
            available=True,
            enabled=enabled,
            configured=configured,
            activation_state=activation_state,
            activation_message=activation_message,
        )

    def get_registry(
        self,
        *,
        user_id: Optional[str] = None,
        analysis_sandbox_mode: Optional[str] = None,
    ) -> CapabilityRegistryResponse:
        effective_analysis_sandbox = (
            str(analysis_sandbox_mode or SANDBOX_DEFAULT_MODE or "local").strip().lower()
        )
        if not is_sandbox_mode_enabled(effective_analysis_sandbox):
            effective_analysis_sandbox = "local"

        presets: list[ModeCapabilityPreset] = []
        capability_map: dict[str, CapabilityDescriptor] = {}
        tool_sources: dict[str, list[str]] = {}
        tool_default_modes: dict[str, list[str]] = {}

        mode_configs = {
            "analysis": self._read_agent_tools(
                AgentMode.ANALYSIS,
                sandbox_mode=effective_analysis_sandbox,
            ),
        }

        for mode, (source_ref, tools) in mode_configs.items():
            capability_ids: list[str] = []

            for tool_name in tools:
                canonical_tool_name = canonicalize_runtime_tool_name(tool_name)
                metadata = _TOOL_METADATA.get(canonical_tool_name) or _TOOL_METADATA.get(
                    tool_name, {}
                )
                capability_id = (
                    metadata.get("capability_id") or f"native.{_sanitize_capability_id(tool_name)}"
                )
                availability = probe_runtime_tool(tool_name)
                if availability.available:
                    capability_ids.append(capability_id)
                tool_sources.setdefault(canonical_tool_name, [])
                if source_ref not in tool_sources[canonical_tool_name]:
                    tool_sources[canonical_tool_name].append(source_ref)
                tool_default_modes.setdefault(canonical_tool_name, [])
                if mode not in tool_default_modes[canonical_tool_name]:
                    tool_default_modes[canonical_tool_name].append(mode)

            for server in get_system_default_mcps(user_id or "local_default"):
                capability_id = f"mcp.{_sanitize_capability_id(server.name)}"
                if server.should_auto_attach_for_mode(mode):
                    capability_ids.append(capability_id)
                if capability_id not in capability_map:
                    capability_map[capability_id] = self._mcp_descriptor(server)

            presets.append(
                ModeCapabilityPreset(
                    mode=mode,
                    capability_ids=capability_ids,
                    source_config_path=source_ref,
                    notes=("内部场景只表达默认工具基线，不表达能力上限。"),
                )
            )

        for tool_name in _TOOL_METADATA:
            canonical_tool_name = canonicalize_runtime_tool_name(tool_name)
            tool_sources.setdefault(canonical_tool_name, [])
            tool_default_modes.setdefault(canonical_tool_name, [])

        for tool_name, modes in tool_default_modes.items():
            descriptor = self._tool_descriptor(
                tool_name,
                default_modes=modes,
                source_config_paths=tool_sources.get(tool_name, []),
            )
            capability_map[descriptor.capability_id] = descriptor

        for descriptor in self._runtime_mcp_tool_descriptors.values():
            capability_map[descriptor.capability_id] = descriptor

        capabilities = sorted(
            capability_map.values(),
            key=lambda item: (item.kind.value, item.capability_id),
        )

        return CapabilityRegistryResponse(
            analysis_sandbox_mode=effective_analysis_sandbox,
            capabilities=capabilities,
            mode_presets=presets,
        )

    def get_integrations_market(self) -> IntegrationMarketResponse:
        """返回系统级扩展与集成市场目录。"""
        items = [
            self._build_integration_market_item(catalog) for catalog in _SYSTEM_INTEGRATION_CATALOG
        ]

        recommended_by_mode: dict[str, list[str]] = {}
        installed_capability_ids: list[str] = []
        active_capability_ids: list[str] = []

        for item in items:
            for mode in item.default_modes:
                recommended_by_mode.setdefault(mode, [])
                if item.capability_id not in recommended_by_mode[mode]:
                    recommended_by_mode[mode].append(item.capability_id)
            if item.enabled:
                installed_capability_ids.append(item.capability_id)
            if item.activation_state == "ready":
                active_capability_ids.append(item.capability_id)

        items.sort(key=lambda item: (item.kind.value, item.capability_id))
        installed_capability_ids.sort()
        active_capability_ids.sort()

        for capability_ids in recommended_by_mode.values():
            capability_ids.sort()

        return IntegrationMarketResponse(
            items=items,
            recommended_by_mode=recommended_by_mode,
            installed_capability_ids=installed_capability_ids,
            active_capability_ids=active_capability_ids,
        )

    def get_tool_category_registry(self) -> ToolCategoryRegistryResponse:
        """返回 AIASys 工具功能分类目录。"""
        categories: list[ToolCategorySummary] = []
        for catalog in _TOOL_CATEGORY_CATALOG:
            category_id = str(catalog["category_id"])
            capability_ids = list(_TOOL_CATEGORY_CAPABILITY_IDS.get(category_id, ()))
            categories.append(
                ToolCategorySummary(
                    category_id=category_id,
                    display_name=str(catalog["display_name"]),
                    description=str(catalog.get("description") or ""),
                    capability_ids=capability_ids,
                    tool_names=resolve_tool_category_tool_names([category_id]),
                    permission_summary=list(catalog.get("permission_summary") or []),
                    runtime_dependencies=list(catalog.get("runtime_dependencies") or []),
                    status=CapabilityStatus.ACTIVE,
                )
            )
        return ToolCategoryRegistryResponse(categories=categories, total=len(categories))


_capability_registry_service: Optional[CapabilityRegistryService] = None


def get_capability_registry_service() -> CapabilityRegistryService:
    global _capability_registry_service
    if _capability_registry_service is None:
        _capability_registry_service = CapabilityRegistryService()
    return _capability_registry_service

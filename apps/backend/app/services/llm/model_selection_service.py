"""
LLM 模型作用域选择服务
"""

from __future__ import annotations

from typing import Any, Optional

from app.models.llm_selection import (
    LLMModelIdentity,
    LLMModelScopeSelection,
    SessionLLMSelectionResponse,
    WorkspaceLLMSelectionResponse,
)
from app.services.llm.llm_config_service import LLMConfigService, get_llm_config_service


def _normalize_model_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class ModelSelectionService:
    def __init__(
        self,
        *,
        llm_config_service: LLMConfigService | None = None,
        workspace_registry: Any | None = None,
    ) -> None:
        self._llm_config_service = llm_config_service or get_llm_config_service()
        if workspace_registry is None:
            from app.services.workspace_registry import get_workspace_registry_service

            workspace_registry = get_workspace_registry_service()
        self._workspace_registry = workspace_registry

    def _load_catalog(
        self,
        user_id: str,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], str | None]:
        full_config = self._llm_config_service.get_full_config(user_id)
        raw_models = full_config.get("models") or {}
        raw_providers = full_config.get("providers") or {}
        models = {
            str(model_id): model_cfg
            for model_id, model_cfg in raw_models.items()
            if isinstance(model_cfg, dict) and str(model_cfg.get("model_type") or "chat") == "chat"
        }
        providers = {
            str(provider_id): provider_cfg
            for provider_id, provider_cfg in raw_providers.items()
            if isinstance(provider_cfg, dict)
        }
        default_model_id = _normalize_model_id(full_config.get("default_model"))
        if default_model_id not in models:
            default_model_id = next(iter(models), None)
        return models, providers, default_model_id

    def _build_identity(
        self,
        models: dict[str, dict[str, Any]],
        providers: dict[str, dict[str, Any]],
        model_id: str | None,
    ) -> LLMModelIdentity:
        normalized_model_id = _normalize_model_id(model_id)
        if not normalized_model_id:
            return LLMModelIdentity()

        model_cfg = models.get(normalized_model_id)
        if not isinstance(model_cfg, dict):
            return LLMModelIdentity()

        provider_id = _normalize_model_id(model_cfg.get("provider"))
        provider_cfg = providers.get(provider_id or "", {})
        provider_name = (
            str(provider_cfg.get("name")).strip()
            if isinstance(provider_cfg, dict) and provider_cfg.get("name")
            else provider_id
        )

        return LLMModelIdentity(
            model_id=normalized_model_id,
            display_name=_normalize_model_id(model_cfg.get("name")),
            model_name=_normalize_model_id(model_cfg.get("model")),
            provider=provider_id,
            provider_name=provider_name,
        )

    def _build_scope_selection(
        self,
        *,
        scope: str,
        configured_model_id: str | None,
        inherited_from: str | None,
        effective_identity: LLMModelIdentity,
        models: dict[str, dict[str, Any]],
        providers: dict[str, dict[str, Any]],
    ) -> LLMModelScopeSelection:
        normalized_configured_id = _normalize_model_id(configured_model_id)
        configured_identity = self._build_identity(
            models,
            providers,
            normalized_configured_id,
        )
        configured_missing = bool(normalized_configured_id and not configured_identity.display_name)
        return LLMModelScopeSelection(
            scope=scope,  # type: ignore[arg-type]
            configured_model_id=normalized_configured_id,
            configured_missing=configured_missing,
            configured_display_name=configured_identity.display_name,
            configured_model_name=configured_identity.model_name,
            configured_provider=configured_identity.provider,
            configured_provider_name=configured_identity.provider_name,
            inherited_from=inherited_from,  # type: ignore[arg-type]
            effective=effective_identity,
        )

    def validate_model_id(self, user_id: str, model_id: str | None) -> str | None:
        normalized_model_id = _normalize_model_id(model_id)
        if normalized_model_id is None:
            return None
        models, _, _ = self._load_catalog(user_id)
        if normalized_model_id not in models:
            raise ValueError("模型不存在，或当前用户无权使用该模型")
        return normalized_model_id

    def get_workspace_selection(
        self,
        *,
        user_id: str,
        workspace_id: str,
    ) -> WorkspaceLLMSelectionResponse:
        models, providers, global_model_id = self._load_catalog(user_id)
        global_identity = self._build_identity(models, providers, global_model_id)
        workspace_model_id = self._workspace_registry.get_workspace_preferred_model_id(
            user_id,
            workspace_id,
        )
        workspace_identity = self._build_identity(models, providers, workspace_model_id)
        effective_identity = workspace_identity if workspace_identity.model_id else global_identity
        return WorkspaceLLMSelectionResponse(
            workspace_id=workspace_id,
            global_scope=self._build_scope_selection(
                scope="global",
                configured_model_id=global_model_id,
                inherited_from=None,
                effective_identity=global_identity,
                models=models,
                providers=providers,
            ),
            workspace_scope=self._build_scope_selection(
                scope="workspace",
                configured_model_id=workspace_model_id,
                inherited_from="global" if not workspace_model_id else None,
                effective_identity=effective_identity,
                models=models,
                providers=providers,
            ),
            effective=effective_identity,
        )

    def get_session_selection(
        self,
        *,
        user_id: str,
        session_id: str,
    ) -> SessionLLMSelectionResponse:
        models, providers, global_model_id = self._load_catalog(user_id)
        global_identity = self._build_identity(models, providers, global_model_id)
        workspace_id = self._workspace_registry.find_workspace_id_by_session_id(
            user_id,
            session_id,
        )
        workspace_model_id = (
            self._workspace_registry.get_workspace_preferred_model_id(
                user_id,
                workspace_id,
            )
            if workspace_id
            else None
        )
        workspace_identity = self._build_identity(models, providers, workspace_model_id)
        workspace_effective_identity = (
            workspace_identity if workspace_identity.model_id else global_identity
        )

        session_metadata = self._workspace_registry.session_manager.get_session(
            session_id,
            user_id,
        )
        session_model_id = _normalize_model_id(
            getattr(session_metadata, "preferred_model_id", None),
        )
        session_identity = self._build_identity(models, providers, session_model_id)
        effective_identity = (
            session_identity if session_identity.model_id else workspace_effective_identity
        )

        return SessionLLMSelectionResponse(
            session_id=session_id,
            workspace_id=workspace_id,
            global_scope=self._build_scope_selection(
                scope="global",
                configured_model_id=global_model_id,
                inherited_from=None,
                effective_identity=global_identity,
                models=models,
                providers=providers,
            ),
            workspace_scope=self._build_scope_selection(
                scope="workspace",
                configured_model_id=workspace_model_id,
                inherited_from="global" if not workspace_model_id else None,
                effective_identity=workspace_effective_identity,
                models=models,
                providers=providers,
            ),
            session_scope=self._build_scope_selection(
                scope="session",
                configured_model_id=session_model_id,
                inherited_from="workspace" if not session_model_id else None,
                effective_identity=effective_identity,
                models=models,
                providers=providers,
            ),
            effective=effective_identity,
        )

    def resolve_effective_model_id(
        self,
        *,
        user_id: str,
        session_id: str | None = None,
        workspace_id: str | None = None,
    ) -> str | None:
        if session_id:
            return self.get_session_selection(
                user_id=user_id,
                session_id=session_id,
            ).effective.model_id
        if workspace_id:
            return self.get_workspace_selection(
                user_id=user_id,
                workspace_id=workspace_id,
            ).effective.model_id
        _, _, default_model_id = self._load_catalog(user_id)
        return default_model_id

    def update_workspace_model_selection(
        self,
        *,
        user_id: str,
        workspace_id: str,
        model_id: str | None,
    ) -> WorkspaceLLMSelectionResponse:
        normalized_model_id = self.validate_model_id(user_id, model_id)
        self._workspace_registry.update_workspace_preferred_model_id(
            user_id,
            workspace_id,
            normalized_model_id,
        )
        return self.get_workspace_selection(user_id=user_id, workspace_id=workspace_id)

    def update_session_model_selection(
        self,
        *,
        user_id: str,
        session_id: str,
        model_id: str | None,
    ) -> SessionLLMSelectionResponse:
        normalized_model_id = self.validate_model_id(user_id, model_id)
        updated = self._workspace_registry.session_manager.update_session_preferred_model_id(
            session_id=session_id,
            user_id=user_id,
            preferred_model_id=normalized_model_id,
        )
        if not updated:
            raise FileNotFoundError("会话不存在")
        return self.get_session_selection(user_id=user_id, session_id=session_id)


_model_selection_service: ModelSelectionService | None = None


def get_model_selection_service() -> ModelSelectionService:
    global _model_selection_service
    if _model_selection_service is None:
        _model_selection_service = ModelSelectionService()
    return _model_selection_service

"""
LLM 配置存储 — 单用户本地配置

存储路径: workspaces/{user_id}/global_workspace/.aiasys/llm_config.json
API Key 使用 Fernet 对称加密保护
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.auth import LOCAL_DEFAULT_USER_ID
from app.core.config import get_user_global_config_dir
from app.core.encryption import decrypt_api_key, encrypt_api_key

logger = logging.getLogger(__name__)


def _utcnow_isoformat() -> str:
    return datetime.now(UTC).isoformat()


class LLMProviderStorage:
    """LLM 配置存储 — 仅支持单用户本地配置"""

    def _get_user_config_path(self, user_id: str | None) -> Path:
        """获取用户配置文件路径"""
        effective_user_id = user_id or LOCAL_DEFAULT_USER_ID
        return get_user_global_config_dir(effective_user_id) / "llm_config.json"

    def _load_config(self, user_id: str) -> Dict[str, Any]:
        """加载配置文件"""
        config_path = self._get_user_config_path(user_id)

        if not config_path.exists():
            return {"providers": [], "models": []}

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"加载配置失败 ({config_path}): {e}")
            return {"providers": [], "models": []}

    def _save_config(self, user_id: str, config: Dict[str, Any]) -> None:
        """保存配置文件"""
        config_path = self._get_user_config_path(user_id)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False, default=str)

    def _decrypt_provider(self, provider: Dict[str, Any]) -> Dict[str, Any]:
        """解密 provider 中的 api_key"""
        result = provider.copy()
        if "api_key_encrypted" in provider:
            try:
                result["api_key"] = decrypt_api_key(provider["api_key_encrypted"])
            except Exception as e:
                logger.warning(f"解密 API Key 失败: {e}")
                result["api_key"] = ""
        return result

    def _encrypt_provider(self, provider: Dict[str, Any]) -> Dict[str, Any]:
        """加密 provider 中的 api_key"""
        result = provider.copy()
        if "api_key" in result and result["api_key"]:
            result["api_key_encrypted"] = encrypt_api_key(result["api_key"])
            del result["api_key"]
        return result

    # ========== Provider CRUD ==========

    def create_provider(self, user_id: str, provider: Dict[str, Any]) -> Dict[str, Any]:
        """创建服务商配置"""
        config = self._load_config(user_id)

        # 检查 ID 是否已存在
        for existing in config["providers"]:
            if existing.get("id") == provider["id"]:
                raise ValueError(f"Provider with id '{provider['id']}' already exists")

        # 加密 API Key
        provider = self._encrypt_provider(provider)
        provider["created_at"] = _utcnow_isoformat()
        provider["updated_at"] = provider["created_at"]

        config["providers"].append(provider)
        self._save_config(user_id, config)

        logger.info(f"创建服务商: {provider['id']}")
        return self._decrypt_provider(provider)

    def get_provider(self, user_id: str, provider_id: str) -> Optional[Dict[str, Any]]:
        """获取服务商配置（脱敏）"""
        config = self._load_config(user_id)

        for provider in config["providers"]:
            if provider.get("id") == provider_id:
                # 解密后脱敏显示
                decrypted = self._decrypt_provider(provider)
                if decrypted.get("api_key"):
                    key = decrypted["api_key"]
                    decrypted["api_key"] = "***" if len(key) <= 8 else f"{key[:4]}...{key[-4:]}"
                return decrypted

        return None

    def get_provider_with_key(self, user_id: str, provider_id: str) -> Optional[Dict[str, Any]]:
        """获取服务商配置（含解密的 API Key）"""
        config = self._load_config(user_id)

        for provider in config["providers"]:
            if provider.get("id") == provider_id:
                return self._decrypt_provider(provider)

        return None

    def list_providers(self, user_id: str, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """列出服务商配置"""
        config = self._load_config(user_id)
        providers = config.get("providers", [])

        if enabled_only:
            providers = [p for p in providers if p.get("enabled", True)]

        # 解密并脱敏 API Key
        result = []
        for provider in providers:
            decrypted = self._decrypt_provider(provider)
            if decrypted.get("api_key"):
                key = decrypted["api_key"]
                decrypted["api_key"] = "***" if len(key) <= 8 else f"{key[:4]}...{key[-4:]}"
            result.append(decrypted)

        return result

    def update_provider(
        self, user_id: str, provider_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """更新服务商配置"""
        config = self._load_config(user_id)

        for i, provider in enumerate(config["providers"]):
            if provider.get("id") == provider_id:
                # 更新字段
                for key, value in updates.items():
                    if key != "id" and value is not None:
                        provider[key] = value

                # 加密 API Key
                provider = self._encrypt_provider(provider)
                provider["updated_at"] = _utcnow_isoformat()

                config["providers"][i] = provider
                self._save_config(user_id, config)

                logger.info(f"更新服务商: {provider_id}")
                return self._decrypt_provider(provider)

        return None

    def delete_provider(self, user_id: str, provider_id: str) -> bool:
        """删除服务商配置"""
        config = self._load_config(user_id)

        original_len = len(config["providers"])
        config["providers"] = [p for p in config["providers"] if p.get("id") != provider_id]

        # 同时删除关联的模型
        models_before = len(config.get("models", []))
        if "models" in config:
            config["models"] = [m for m in config["models"] if m.get("provider") != provider_id]
            if len(config["models"]) < models_before:
                logger.info(
                    f"删除服务商 '{provider_id}' 关联的 {models_before - len(config['models'])} 个模型"
                )

        if len(config["providers"]) < original_len:
            self._save_config(user_id, config)
            logger.info(f"删除服务商: {provider_id}")
            return True

        return False

    # ========== Model CRUD ==========

    def create_model(self, user_id: str, model: Dict[str, Any]) -> Dict[str, Any]:
        """创建模型配置"""
        config = self._load_config(user_id)

        # 确保 models 列表存在
        if "models" not in config:
            config["models"] = []

        # 检查 ID 是否已存在
        for existing in config["models"]:
            if existing.get("id") == model["id"]:
                raise ValueError(f"Model with id '{model['id']}' already exists")

        model["created_at"] = _utcnow_isoformat()
        model["updated_at"] = model["created_at"]

        config["models"].append(model)
        self._save_config(user_id, config)

        logger.info(f"创建模型: {model['id']}")
        return model

    def get_model(self, user_id: str, model_id: str) -> Optional[Dict[str, Any]]:
        """获取模型配置"""
        config = self._load_config(user_id)

        for model in config.get("models", []):
            if model.get("id") == model_id:
                return model

        return None

    def list_models(
        self, user_id: str, enabled_only: bool = False, provider_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """列出模型配置"""
        config = self._load_config(user_id)
        models = config.get("models", [])

        if enabled_only:
            models = [m for m in models if m.get("enabled", True)]

        if provider_id:
            models = [m for m in models if m.get("provider") == provider_id]

        return models

    def update_model(
        self, user_id: str, model_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """更新模型配置"""
        config = self._load_config(user_id)

        for i, model in enumerate(config.get("models", [])):
            if model.get("id") == model_id:
                # 更新字段
                for key, value in updates.items():
                    if key != "id" and value is not None:
                        model[key] = value

                model["updated_at"] = _utcnow_isoformat()
                config["models"][i] = model
                self._save_config(user_id, config)

                logger.info(f"更新模型: {model_id}")
                return model

        return None

    def delete_model(self, user_id: str, model_id: str) -> bool:
        """删除模型配置"""
        config = self._load_config(user_id)

        original_len = len(config.get("models", []))
        if "models" in config:
            config["models"] = [m for m in config["models"] if m.get("id") != model_id]

        if config.get("default_model") == model_id:
            config["default_model"] = None
        if config.get("default_chat_model") == model_id:
            config["default_chat_model"] = None
        if config.get("default_embedding_model") == model_id:
            config["default_embedding_model"] = None

        if len(config.get("models", [])) < original_len:
            self._save_config(user_id, config)
            logger.info(f"删除模型: {model_id}")
            return True

        return False

    def unset_default_models(self, user_id: str, exclude_model_id: Optional[str] = None) -> None:
        """取消所有模型的默认状态"""
        config = self._load_config(user_id)

        if "models" not in config:
            return

        for model in config["models"]:
            if model.get("is_default") and (
                exclude_model_id is None or model.get("id") != exclude_model_id
            ):
                model["is_default"] = False
                model["updated_at"] = _utcnow_isoformat()

        self._save_config(user_id, config)
        logger.info(f"取消默认模型状态 (排除: {exclude_model_id or '无'})")

    def unset_default_providers(
        self, user_id: str, exclude_provider_id: Optional[str] = None
    ) -> None:
        """取消所有 provider 的默认状态"""
        config = self._load_config(user_id)

        for provider in config.get("providers", []):
            if provider.get("is_default") and (
                exclude_provider_id is None or provider.get("id") != exclude_provider_id
            ):
                provider["is_default"] = False
                provider["updated_at"] = _utcnow_isoformat()

        self._save_config(user_id, config)
        logger.info(f"取消默认服务商状态 (排除: {exclude_provider_id or '无'})")

    # ========== Full Config ==========

    def get_full_config(self, user_id: str) -> Dict[str, Any]:
        """获取完整配置（含解密的 API Key）"""
        config = self._load_config(user_id)

        # 解密所有 provider 的 API Key
        providers = []
        for provider in config.get("providers", []):
            providers.append(self._decrypt_provider(provider))

        return {
            "providers": providers,
            "models": config.get("models", []),
            "default_model": config.get("default_model"),
            "default_chat_model": config.get("default_chat_model"),
            "default_embedding_model": config.get("default_embedding_model"),
        }

    def initialize_defaults(self, user_id: str) -> None:
        """初始化空配置"""
        config = self._load_config(user_id)

        # 如果已有配置，不做任何操作
        if config.get("providers") or config.get("models"):
            return

        # 创建空配置
        config = {
            "providers": [],
            "models": [],
            "default_model": None,
            "default_chat_model": None,
            "default_embedding_model": None,
        }
        self._save_config(user_id, config)

        logger.info("初始化空 LLM 配置")

    def get_model_defaults(self, user_id: str) -> Dict[str, Any]:
        """获取默认 chat / embedding 模型配置。"""
        config = self._load_config(user_id)
        return {
            "default_model": config.get("default_model"),
            "default_chat_model": config.get("default_chat_model"),
            "default_embedding_model": config.get("default_embedding_model"),
        }

    def update_model_defaults(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新默认 chat / embedding 模型配置。"""
        config = self._load_config(user_id)
        for key in ("default_model", "default_chat_model", "default_embedding_model"):
            if key in updates:
                config[key] = updates[key]
        self._save_config(user_id, config)
        return self.get_model_defaults(user_id)


# 全局存储实例
_llm_provider_storage: Optional[LLMProviderStorage] = None


def get_llm_provider_storage() -> LLMProviderStorage:
    """获取 LLM 配置存储实例"""
    global _llm_provider_storage
    if _llm_provider_storage is None:
        _llm_provider_storage = LLMProviderStorage()
    return _llm_provider_storage

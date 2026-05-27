"""模板外部市场服务。

将系统内置模板以市场形式展示给用户，支持安装到用户自定义模板目录。
"""

from __future__ import annotations

import logging
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.core.templates import (
    _TEMPLATES_DIR,
    _get_user_templates_dir,
    _is_safe_template_id,
    _list_template_dirs,
    _load_template,
    build_template_payload,
)
from app.models.external_template_market import (
    ExternalTemplateMarketDetailResponse,
    ExternalTemplateMarketItem,
    ExternalTemplateMarketListResponse,
    ExternalTemplateMarketSource,
)

logger = logging.getLogger(__name__)


class ExternalTemplateMarketAdapter(ABC):
    """模板市场适配器基类。"""

    @property
    @abstractmethod
    def source(self) -> ExternalTemplateMarketSource:
        """返回该适配器对应的市场源元数据。"""

    @abstractmethod
    def list_items(
        self,
        user_id: str,
        search: str | None = None,
        category: str | None = None,
    ) -> ExternalTemplateMarketListResponse:
        """列出市场条目。"""

    @abstractmethod
    def get_item_detail(
        self,
        user_id: str,
        item_id: str,
    ) -> ExternalTemplateMarketDetailResponse | None:
        """获取单个条目详情。"""

    @abstractmethod
    def install_item(
        self,
        user_id: str,
        item_id: str,
    ) -> dict[str, Any]:
        """安装条目到用户模板目录。

        返回 {"installed": bool, "template_id": str}
        """


class AIASysBuiltinTemplateAdapter(ExternalTemplateMarketAdapter):
    """AIASys 内置模板市场适配器。

    扫描 apps/backend/templates/ 目录，将系统内置模板作为市场条目展示。
    """

    _SOURCE = ExternalTemplateMarketSource(
        source_id="aiasys-builtin",
        display_name="AIASys 内置",
        description="AIASys 系统预置的工作区模板",
        supports_public_catalog=True,
        supports_install=True,
        install_available=True,
    )

    @property
    def source(self) -> ExternalTemplateMarketSource:
        return self._SOURCE

    def _is_installed(self, user_id: str, item_id: str) -> bool:
        """检查模板是否已安装到用户目录。"""
        user_dir = _get_user_templates_dir(user_id)
        return (user_dir / item_id).exists()

    def _template_to_item(self, user_id: str, template) -> ExternalTemplateMarketItem:
        cap_count = len(template.recommended_capabilities)
        if cap_count == 0:
            cap_count = len(template.recommended_skills) + len(template.recommended_mcps)
        return ExternalTemplateMarketItem(
            source_id=self._SOURCE.source_id,
            item_id=template.template_id,
            name=template.name,
            description=template.description or None,
            icon=template.icon,
            category=template.category,
            env_kind=template.env_kind,
            file_count=len(template.files),
            capability_count=cap_count,
            is_installed=self._is_installed(user_id, template.template_id),
            official=True,
        )

    def list_items(
        self,
        user_id: str,
        search: str | None = None,
        category: str | None = None,
    ) -> ExternalTemplateMarketListResponse:
        items: list[ExternalTemplateMarketItem] = []
        categories: set[str] = set()

        for template_dir in _list_template_dirs():
            template = _load_template(template_dir)
            if template is None:
                continue
            categories.add(template.category)

            if search:
                query = search.lower()
                if (
                    query not in template.name.lower()
                    and query not in template.description.lower()
                    and query not in template.template_id.lower()
                ):
                    continue

            if category and template.category != category:
                continue

            items.append(self._template_to_item(user_id, template))

        return ExternalTemplateMarketListResponse(
            source=self._SOURCE,
            items=items,
            available_categories=sorted(categories),
            total_count=len(items),
        )

    def get_item_detail(
        self,
        user_id: str,
        item_id: str,
    ) -> ExternalTemplateMarketDetailResponse | None:
        if not _is_safe_template_id(item_id):
            return None

        for template_dir in _list_template_dirs():
            template = _load_template(template_dir)
            if template is None or template.template_id != item_id:
                continue

            item = self._template_to_item(user_id, template)
            payload = build_template_payload(template)

            return ExternalTemplateMarketDetailResponse(
                source=self._SOURCE,
                item=item,
                files=payload.get("files", []),
                recommended_capabilities=payload.get("recommended_capabilities", []),
                env_vars=payload.get("env_vars", {}),
                can_install=not item.is_installed,
                install_disabled_reason=(
                    "该模板已安装到您的模板目录" if item.is_installed else None
                ),
            )

        return None

    def install_item(
        self,
        user_id: str,
        item_id: str,
    ) -> dict[str, Any]:
        if not _is_safe_template_id(item_id):
            raise ValueError(f"不安全的模板 ID: {item_id}")

        # 查找内置模板源目录
        source_dir: Path | None = None
        for template_dir in _list_template_dirs():
            tmpl = _load_template(template_dir)
            if tmpl is not None and tmpl.template_id == item_id:
                source_dir = template_dir
                break

        if source_dir is None:
            raise ValueError(f"模板不存在: {item_id}")

        user_templates_dir = _get_user_templates_dir(user_id)
        target_dir = user_templates_dir / item_id

        if target_dir.exists():
            # 已存在则覆盖（先删除旧目录再复制）
            shutil.rmtree(target_dir)

        shutil.copytree(source_dir, target_dir)
        logger.info("内置模板已安装到用户目录: %s -> %s", source_dir, target_dir)

        return {"installed": True, "template_id": item_id}


class ExternalTemplateMarketService:
    """模板市场聚合服务。"""

    def __init__(self) -> None:
        self._adapters: dict[str, ExternalTemplateMarketAdapter] = {
            "aiasys-builtin": AIASysBuiltinTemplateAdapter(),
        }

    def list_sources(self) -> list[ExternalTemplateMarketSource]:
        return [adapter.source for adapter in self._adapters.values()]

    def get_adapter(self, source_id: str) -> ExternalTemplateMarketAdapter:
        if source_id not in self._adapters:
            raise ValueError(f"未知的市场源: {source_id}")
        return self._adapters[source_id]

    def list_items(
        self,
        source_id: str,
        user_id: str,
        search: str | None = None,
        category: str | None = None,
    ) -> ExternalTemplateMarketListResponse:
        return self.get_adapter(source_id).list_items(user_id, search, category)

    def get_item_detail(
        self,
        source_id: str,
        user_id: str,
        item_id: str,
    ) -> ExternalTemplateMarketDetailResponse | None:
        return self.get_adapter(source_id).get_item_detail(user_id, item_id)

    def install_item(
        self,
        source_id: str,
        user_id: str,
        item_id: str,
    ) -> dict[str, Any]:
        return self.get_adapter(source_id).install_item(user_id, item_id)


_external_template_market_service: ExternalTemplateMarketService | None = None


def get_external_template_market_service() -> ExternalTemplateMarketService:
    global _external_template_market_service
    if _external_template_market_service is None:
        _external_template_market_service = ExternalTemplateMarketService()
    return _external_template_market_service

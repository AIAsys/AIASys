"""Claw session 级通信绑定服务（聚合类）."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.core.config import WORKSPACE_DIR
from app.services.session import SessionManager

from .mixins.bindings import ClawBindingsMixin
from .mixins.connectors import ClawConnectorsMixin
from .mixins.dingtalk_qr_login import ClawDingTalkQrLoginMixin
from .mixins.feishu_qr_login import ClawFeishuQrLoginMixin
from .mixins.gateway import ClawGatewayMixin
from .mixins.hermes import ClawHermesMixin
from .mixins.inbound import ClawInboundMixin
from .mixins.messages import ClawMessagesMixin
from .mixins.outbound import ClawOutboundMixin
from .mixins.qr_login import ClawQrLoginMixin
from .mixins.runtime import ClawRuntimeMixin
from .mixins.storage import ClawStorageMixin
from .mixins.workspace import ClawWorkspaceMixin


class ClawService(
    ClawStorageMixin,
    ClawWorkspaceMixin,
    ClawInboundMixin,
    ClawBindingsMixin,
    ClawGatewayMixin,
    ClawConnectorsMixin,
    ClawMessagesMixin,
    ClawRuntimeMixin,
    ClawHermesMixin,
    ClawQrLoginMixin,
    ClawFeishuQrLoginMixin,
    ClawDingTalkQrLoginMixin,
    ClawOutboundMixin,
):
    """管理用户级 Claw 连接资产与 session 级绑定。"""

    def __init__(
        self,
        workspace_root: Path = WORKSPACE_DIR,
        session_manager: Optional[SessionManager] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.session_manager = session_manager or SessionManager(self.workspace_root)


_claw_service_instance: Optional[ClawService] = None


def get_claw_service() -> ClawService:
    global _claw_service_instance
    if _claw_service_instance is None:
        _claw_service_instance = ClawService()
    return _claw_service_instance

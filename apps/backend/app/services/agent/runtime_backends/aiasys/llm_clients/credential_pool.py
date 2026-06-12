from __future__ import annotations

import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

_EXHAUSTED_COOLDOWN_SECONDS = 3600  # 1 hour


@dataclass
class PooledCredential:
    """单个池化凭证的状态。"""

    id: str
    api_key: str
    status: Literal["ok", "exhausted"] = "ok"
    exhausted_at: float = 0.0
    exhausted_reason: str = ""
    error_count: int = 0
    request_count: int = 0

    @property
    def is_available(self) -> bool:
        if self.status == "ok":
            return True
        if time.time() - self.exhausted_at > _EXHAUSTED_COOLDOWN_SECONDS:
            # 冷却结束，自动恢复为 ok
            return True
        return False


@dataclass
class CredentialPool:
    """同一 provider 的多凭证池，支持耗尽时自动轮换。

    使用场景：同一 provider 配置了多个 API key，当某个 key
    因 billing (402) 或 rate limit (429) 耗尽时，自动切换到
    池中下一个可用的 key，无需跨 provider fallback。
    """

    provider_id: str
    credentials: list[PooledCredential] = field(default_factory=list)
    strategy: Literal["round_robin", "random", "least_used"] = "round_robin"
    _index: int = field(default=0, repr=False)
    _lock: Any = field(default_factory=lambda: None, repr=False)

    def __post_init__(self):
        import asyncio

        if self._lock is None:
            self._lock = asyncio.Lock()

    @classmethod
    def from_provider_config(
        cls,
        provider_id: str,
        api_key: str | None,
        api_keys: list[str] | None,
        strategy: Literal["round_robin", "random", "least_used"] = "round_robin",
    ) -> "CredentialPool | None":
        """从 LlmProviderConfig 构建凭证池。

        如果只有单个 api_key 且没有 api_keys 列表，返回 None
        （不需要池化）。
        """
        keys: list[str] = []
        if api_key:
            keys.append(api_key)
        if api_keys:
            for k in api_keys:
                if k and k not in keys:
                    keys.append(k)

        if len(keys) <= 1:
            return None

        creds = [
            PooledCredential(
                id=f"{provider_id}-{uuid.uuid4().hex[:6]}",
                api_key=k,
            )
            for k in keys
        ]
        return cls(provider_id=provider_id, credentials=creds, strategy=strategy)

    def _ensure_lock(self):
        """延迟初始化 asyncio.Lock，确保在事件循环中创建。"""
        if self._lock is None:
            import asyncio

            self._lock = asyncio.Lock()

    async def get_next(self) -> PooledCredential | None:
        """获取下一个可用的凭证。"""
        self._ensure_lock()
        async with self._lock:
            available = [c for c in self.credentials if c.is_available]
            if not available:
                return None

            if self.strategy == "random":
                chosen = random.choice(available)
            elif self.strategy == "least_used":
                chosen = min(available, key=lambda c: c.request_count)
            else:
                # round_robin: 从当前索引开始循环查找
                for _ in range(len(self.credentials)):
                    candidate = self.credentials[self._index % len(self.credentials)]
                    self._index = (self._index + 1) % len(self.credentials)
                    if candidate.is_available:
                        chosen = candidate
                        break
                else:
                    # fallback to first available if round-robin didn't find one
                    chosen = available[0]

            chosen.request_count += 1
            return chosen

    async def mark_exhausted(
        self,
        credential_id: str,
        reason: str = "",
        cooldown_seconds: float | None = None,
    ) -> PooledCredential | None:
        """标记指定凭证为耗尽状态，返回下一个可用凭证（如有）。"""
        self._ensure_lock()
        async with self._lock:
            for cred in self.credentials:
                if cred.id == credential_id:
                    cred.status = "exhausted"
                    cred.exhausted_at = time.time()
                    cred.exhausted_reason = reason
                    cred.error_count += 1
                    logger.warning(
                        "Credential %s exhausted (%s), error_count=%d",
                        cred.id,
                        reason,
                        cred.error_count,
                    )
                    break

            # 内联 get_next 逻辑，避免 asyncio.Lock 非重入死锁
            available = [c for c in self.credentials if c.is_available]
            if not available:
                return None

            if self.strategy == "random":
                chosen = random.choice(available)
            elif self.strategy == "least_used":
                chosen = min(available, key=lambda c: c.request_count)
            else:
                # round_robin
                for _ in range(len(self.credentials)):
                    candidate = self.credentials[self._index % len(self.credentials)]
                    self._index = (self._index + 1) % len(self.credentials)
                    if candidate.is_available:
                        chosen = candidate
                        break
                else:
                    chosen = available[0]

            chosen.request_count += 1
            return chosen

    async def mark_ok(self, credential_id: str) -> None:
        """将指定凭证重置为 ok 状态。"""
        self._ensure_lock()
        async with self._lock:
            for cred in self.credentials:
                if cred.id == credential_id:
                    cred.status = "ok"
                    cred.exhausted_at = 0.0
                    cred.exhausted_reason = ""
                    logger.info("Credential %s reset to ok", cred.id)
                    return

    @property
    def has_available(self) -> bool:
        """池中是否还有可用凭证。"""
        return any(c.is_available for c in self.credentials)

    @property
    def size(self) -> int:
        return len(self.credentials)

    def stats(self) -> dict[str, Any]:
        """返回池统计信息。"""
        return {
            "provider_id": self.provider_id,
            "total": len(self.credentials),
            "available": sum(1 for c in self.credentials if c.is_available),
            "exhausted": sum(1 for c in self.credentials if not c.is_available),
            "credentials": [
                {
                    "id": c.id,
                    "status": c.status,
                    "error_count": c.error_count,
                    "request_count": c.request_count,
                    "is_available": c.is_available,
                }
                for c in self.credentials
            ],
        }

"""
缓存管理器
支持 Redis 和内存缓存两种模式
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

# 尝试导入 redis，如果没有则使用内存缓存
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class MemoryCache:
    """带 TTL 清理和容量上限的进程内缓存。"""

    def __init__(self, max_entries: int = 2048):
        self._cache: Dict[str, tuple[Any, Optional[float]]] = {}
        self._max_entries = max(max_entries, 1)

    def get(self, key: str) -> Optional[str]:
        self._prune_expired()
        if key not in self._cache:
            return None
        value, expire_time = self._cache[key]
        if expire_time and time.time() > expire_time:
            del self._cache[key]
            return None
        return json.dumps(value) if value is not None else None

    def setex(self, key: str, ttl: int, value: str) -> bool:
        try:
            self._prune_expired()
            parsed = json.loads(value)
            expire_time = time.time() + ttl if ttl > 0 else None
            self._cache[key] = (parsed, expire_time)
            self._prune_overflow()
            return True
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def scan_iter(self, match: str):
        """模拟 redis scan_iter"""
        self._prune_expired()
        pattern = match.replace("*", "")
        for key in list(self._cache.keys()):
            if key.startswith(pattern):
                yield key

    def _prune_expired(self) -> None:
        now = time.time()
        expired = [
            key
            for key, (_, expire_time) in self._cache.items()
            if expire_time is not None and now > expire_time
        ]
        for key in expired:
            self._cache.pop(key, None)

    def _prune_overflow(self) -> None:
        overflow = len(self._cache) - self._max_entries
        if overflow <= 0:
            return
        sorted_keys = sorted(
            self._cache,
            key=lambda key: self._cache[key][1] or float("inf"),
        )
        for key in sorted_keys[:overflow]:
            self._cache.pop(key, None)


class CacheManager:
    """缓存管理器，支持 Redis 和内存缓存"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        ttl: int = 86400,
        memory_max_entries: int = 2048,
    ):
        self.ttl = ttl  # 默认24小时
        self._prefix = "graphrag:"

        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=host,
                    port=port,
                    db=db,
                    decode_responses=True,
                    socket_connect_timeout=0.2,
                    socket_timeout=0.2,
                    retry_on_timeout=False,
                )
                # 测试连接
                self.redis_client.ping()
                self._use_redis = True
            except Exception as e:
                logger.warning("Redis connection failed: %s, using in-memory cache", e)
                self.redis_client = MemoryCache(max_entries=memory_max_entries)
                self._use_redis = False
        else:
            self.redis_client = MemoryCache(max_entries=memory_max_entries)
            self._use_redis = False

    def _make_key(self, key_type: str, *args) -> str:
        """生成缓存键"""
        hasher = hashlib.md5()
        hasher.update(str(args).encode())
        return f"{self._prefix}{key_type}:{hasher.hexdigest()}"

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
        except Exception as e:
            logger.error("Cache get error: %s", e)
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值"""
        try:
            expire = ttl or self.ttl
            self.redis_client.setex(key, expire, json.dumps(value))
            return True
        except Exception as e:
            logger.error("Cache set error: %s", e)
            return False

    def get_llm_cache(self, llm_name: str, prompt: str, history: list) -> Optional[str]:
        """获取 LLM 调用缓存"""
        key = self._make_key("llm", llm_name, prompt, str(history))
        return self.get(key)

    def set_llm_cache(self, llm_name: str, prompt: str, history: list, response: str) -> bool:
        """设置 LLM 调用缓存"""
        key = self._make_key("llm", llm_name, prompt, str(history))
        return self.set(key, response)

    def get_embed_cache(self, model: str, text: str) -> Optional[np.ndarray]:
        """获取 Embedding 缓存"""
        key = self._make_key("embed", model, text)
        cached = self.get(key)
        if cached is not None:
            return np.array(cached)
        return None

    def set_embed_cache(self, model: str, text: str, embedding: np.ndarray) -> bool:
        """设置 Embedding 缓存"""
        key = self._make_key("embed", model, text)
        return self.set(key, embedding.tolist())

    def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.error("Cache delete error: %s", e)
            return False

    def clear_prefix(self, prefix: str) -> bool:
        """清除指定前缀的缓存"""
        try:
            pattern = f"{self._prefix}{prefix}:*"
            for key in self.redis_client.scan_iter(match=pattern):
                self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.error("Cache clear error: %s", e)
            return False


# 全局缓存实例
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager

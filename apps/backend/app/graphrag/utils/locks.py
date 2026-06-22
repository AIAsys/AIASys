"""
分布式锁 - 用于控制多进程/多线程的图谱构建并发
支持 Redis 和纯内存锁两种模式
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# 尝试导入 redis
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class MemoryLock:
    """基于内存的锁实现（单进程使用）"""

    def __init__(self):
        self._locks: Dict[str, tuple[str, float]] = {}  # key -> (identifier, expire_time)

    def set(self, key: str, identifier: str, nx: bool = False, ex: int = 60) -> bool:
        """设置锁"""
        now = time.time()
        # 清理过期锁
        expired = [k for k, (_, exp) in self._locks.items() if now > exp]
        for k in expired:
            del self._locks[k]

        if nx and key in self._locks:
            return False

        self._locks[key] = (identifier, now + ex)
        return True

    def delete(self, key: str) -> bool:
        """删除锁"""
        if key in self._locks:
            del self._locks[key]
            return True
        return False


class GraphLock:
    """分布式锁，支持 Redis 和内存模式"""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self._local_locks: Dict[str, asyncio.Lock] = {}
        self._use_redis = False

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
                self.redis_client.ping()
                self._use_redis = True
            except Exception as e:
                logger.warning("Redis connection failed: %s, using in-memory lock", e)
                self.redis_client = MemoryLock()
        else:
            self.redis_client = MemoryLock()

    async def acquire(self, key: str, timeout: int = 1200, blocking: bool = True) -> bool:
        """
        获取锁

        Args:
            key: 锁的标识
            timeout: 锁的超时时间（秒）
            blocking: 是否阻塞等待

        Returns:
            是否成功获取锁
        """
        lock_key = f"graphrag:lock:{key}"
        identifier = str(time.time())

        if self._use_redis:
            # Redis 模式
            acquired = self.redis_client.set(lock_key, identifier, nx=True, ex=timeout)
            if acquired:
                return True
            if not blocking:
                return False
            # 阻塞等待
            while True:
                await asyncio.sleep(0.1)
                acquired = self.redis_client.set(lock_key, identifier, nx=True, ex=timeout)
                if acquired:
                    return True
        else:
            # 内存模式 - 使用 asyncio.Lock
            if key not in self._local_locks:
                self._local_locks[key] = asyncio.Lock()
            lock = self._local_locks[key]

            if blocking:
                await lock.acquire()
                return True
            else:
                try:
                    lock.acquire_nowait()
                    return True
                except asyncio.LockError:
                    return False

    async def release(self, key: str) -> bool:
        """释放锁"""
        lock_key = f"graphrag:lock:{key}"
        try:
            if self._use_redis:
                self.redis_client.delete(lock_key)
            else:
                if key in self._local_locks:
                    lock = self._local_locks[key]
                    if lock.locked():
                        await lock.release()
            return True
        except Exception as e:
            logger.error("Lock release error: %s", e)
            return False

    @asynccontextmanager
    async def lock(self, key: str, timeout: int = 1200):
        """上下文管理器方式使用锁"""
        try:
            await self.acquire(key, timeout)
            yield
        finally:
            await self.release(key)


# 全局锁实例
_lock_manager: Optional[GraphLock] = None


def get_lock_manager() -> GraphLock:
    """获取全局锁管理器"""
    global _lock_manager
    if _lock_manager is None:
        _lock_manager = GraphLock()
    return _lock_manager

"""
Embedding 服务提供商

支持多种 Embedding 服务：
- OpenAI API
- Kimi (Moonshot) API
- 其他兼容 OpenAI API 的服务
"""

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from functools import wraps
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)


# ============ 限速和重试工具 ============


def rate_limited(max_calls_per_second: float = 2.0):
    """
    速率限制装饰器（支持 async 函数）

    Args:
        max_calls_per_second: 每秒最大调用次数（默认 2 QPS，即每 0.5 秒一个请求）
    """
    min_interval = 1.0 / max_calls_per_second
    last_call_time = [0.0]  # 使用列表存储可变状态

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            elapsed = time.time() - last_call_time[0]
            if elapsed < min_interval:
                sleep_time = min_interval - elapsed
                logger.debug(f"[Rate Limit] Sleeping {sleep_time:.3f}s")
                await asyncio.sleep(sleep_time)

            result = await func(*args, **kwargs)
            last_call_time[0] = time.time()
            return result

        return wrapper

    return decorator


def retry_with_exponential_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_status_codes: tuple = (429, 500, 502, 503, 504),
):
    """
    指数退避重试装饰器（支持 async 函数）

    特别处理阿里云限流错误：
    - 429: 请求频率超限
    - 503: 服务暂时不可用
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except httpx.HTTPStatusError as e:
                    status_code = e.response.status_code

                    # 判断是否可重试的错误
                    if status_code not in retryable_status_codes:
                        raise

                    # 最后一次尝试，直接抛出异常
                    if attempt == max_retries:
                        logger.error(
                            f"[Retry] Max retries ({max_retries}) exceeded for {func.__name__}"
                        )
                        raise

                    # 尝试从响应中获取 Retry-After 头
                    retry_after = e.response.headers.get("retry-after")
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except (ValueError, TypeError):
                            pass

                    # 特定错误类型的提示
                    if status_code == 429:
                        error_msg = e.response.text.lower()
                        if "rate limit" in error_msg or "requests rate" in error_msg:
                            logger.warning(
                                f"[Retry] RPM/QPS limit hit (429), waiting {delay:.1f}s before retry {attempt + 1}/{max_retries}"
                            )
                        elif "quota" in error_msg:
                            logger.warning(
                                f"[Retry] TPM/Quota limit hit (429), waiting {delay:.1f}s before retry {attempt + 1}/{max_retries}"
                            )
                        else:
                            logger.warning(
                                f"[Retry] Rate limit (429), waiting {delay:.1f}s before retry {attempt + 1}/{max_retries}"
                            )
                    else:
                        logger.warning(
                            f"[Retry] HTTP {status_code}, waiting {delay:.1f}s before retry {attempt + 1}/{max_retries}"
                        )

                    await asyncio.sleep(delay)
                    delay = min(delay * exponential_base, max_delay)

                except Exception:
                    # 非 HTTP 错误，直接抛出
                    raise

            return None  # 理论上不会执行到这里

        return wrapper

    return decorator


class BaseEmbedder(ABC):
    """Embedding 基类"""

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """将文本列表转换为向量列表"""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""
        pass


class OpenAIEmbedder(BaseEmbedder):
    """OpenAI Embedding (兼容阿里云 DashScope 等 OpenAI 兼容接口)"""

    # 模型特定的批次大小限制（根据阿里云文档）
    BATCH_SIZE_LIMITS = {
        "text-embedding-v4": 96,  # 阿里云 text-embedding-v4 最大 96
        "text-embedding-v3": 25,  # 阿里云 text-embedding-v3 最大 25
        "text-embedding-v2": 25,  # 阿里云 text-embedding-v2 最大 25
        "text-embedding-3-small": 100,
        "text-embedding-3-large": 100,
    }

    # 默认限速：每秒 2 个请求（可根据模型调整）
    DEFAULT_RATE_LIMIT = 2.0

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "text-embedding-3-small",
        rate_limit_qps: Optional[float] = None,
        enable_retry: bool = True,
        dimension: Optional[int] = None,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = model
        self.enable_retry = enable_retry

        # 优先使用用户配置的维度，没有再用模型名称推断
        self._dimension = dimension or self._get_dimension_for_model(model)

        # 设置限速
        if rate_limit_qps is None:
            # 阿里云 embedding 模型建议使用较低 QPS
            if "aliyun" in self.base_url or "dashscope" in self.base_url:
                self.rate_limit_qps = 1.0  # 阿里云建议每秒 1 个请求
            else:
                self.rate_limit_qps = self.DEFAULT_RATE_LIMIT
        else:
            self.rate_limit_qps = rate_limit_qps

        if not self.api_key:
            raise ValueError("OpenAI API Key 未设置")

    def _get_dimension_for_model(self, model: str) -> int:
        """根据模型名称获取向量维度"""
        dimensions = {
            "text-embedding-v4": 1536,
            "text-embedding-v3": 1024,
            "text-embedding-v2": 1536,
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
        }
        return dimensions.get(model, 1536)

    @property
    def dimension(self) -> int:
        return self._dimension

    def _get_batch_size(self) -> int:
        """获取当前模型的批次大小限制"""
        return self.BATCH_SIZE_LIMITS.get(self.model, 100)

    async def _embed_batch(self, batch: List[str], headers: dict) -> List[List[float]]:
        """发送单个批次的 embedding 请求"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers=headers,
                json={"input": batch, "model": self.model, "encoding_format": "float"},
            )
            response.raise_for_status()
            data = response.json()

            # 按索引排序
            embeddings = sorted(data["data"], key=lambda x: x["index"])
            return [e["embedding"] for e in embeddings]

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """调用 OpenAI API 获取 Embedding（带限速和重试）"""
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        # 处理空文本
        if not texts:
            return []

        # 获取批次大小限制
        batch_size = self._get_batch_size()
        all_embeddings = []
        total_batches = (len(texts) + batch_size - 1) // batch_size

        for i in range(0, len(texts), batch_size):
            batch_num = i // batch_size + 1
            batch = texts[i : i + batch_size]

            # 替换空字符串
            batch = [t if t.strip() else " " for t in batch]

            # 速率限制：批次之间添加延迟
            if i > 0:
                sleep_time = 1.0 / self.rate_limit_qps
                logger.debug(
                    f"[Rate Limit] Batch {batch_num}/{total_batches}: sleeping {sleep_time:.2f}s"
                )
                await asyncio.sleep(sleep_time)

            try:
                if self.enable_retry:
                    # 使用重试包装
                    embeddings = await self._embed_with_retry(batch, headers)
                else:
                    embeddings = await self._embed_batch(batch, headers)

                all_embeddings.extend(embeddings)
                logger.debug(
                    f"[Embed] Batch {batch_num}/{total_batches}: {len(batch)} texts processed"
                )

            except Exception as e:
                logger.error(f"[Embed] Batch {batch_num}/{total_batches} failed: {e}")
                raise

        logger.info(f"[Embed] Total: {len(texts)} texts in {total_batches} batches")
        return all_embeddings

    @retry_with_exponential_backoff(max_retries=3, initial_delay=1.0)
    async def _embed_with_retry(self, batch: List[str], headers: dict) -> List[List[float]]:
        """带重试的 embedding 请求"""
        return await self._embed_batch(batch, headers)


# Embedder 工厂

EMBEDDER_REGISTRY = {
    "openai": OpenAIEmbedder,
    "dashscope": OpenAIEmbedder,
    "kimi": OpenAIEmbedder,
    "moonshot": OpenAIEmbedder,
    "siliconflow": OpenAIEmbedder,
}

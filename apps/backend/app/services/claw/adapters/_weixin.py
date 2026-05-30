"""WeChat adapter stub — module exists but full implementation is pending."""

AIOHTTP_AVAILABLE = False
aiohttp = None
QR_TIMEOUT_MS = 300_000


async def _api_get(*args, **kwargs):
    raise RuntimeError("WeChat adapter not available")


class WeixinAdapter:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("WeChat adapter not available")


async def send_weixin_direct(*args, **kwargs):
    raise RuntimeError("WeChat adapter not available")

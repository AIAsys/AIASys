"""LLM 服务商 base_url 安全校验。

防止认证用户通过配置 base_url 让后端代为访问内部服务（SSRF）。
"""

import ipaddress
from urllib.parse import urlparse


# 明确禁止的 hostname（不区分大小写）
_BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "metadata.google.internal",
    "metadata.oracle.internal",
    "169.254.169.254",
}


def validate_llm_base_url(url: str) -> None:
    """校验 LLM 服务商 base_url 是否合法。

    拒绝：
    - 非 http/https 协议
    - 无 hostname
    - 私有/回环/链路本地 IP
    - 常见内部 metadata 地址
    - 空字符串或明显非法格式

    Raises:
        ValueError: URL 不合法时抛出可读的校验错误。
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("base_url 不能为空")

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"base_url 必须使用 http:// 或 https:// 协议: {url}")

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        raise ValueError(f"base_url 缺少有效主机名: {url}")

    if hostname in _BLOCKED_HOSTS:
        raise ValueError(f"base_url 指向被禁止的内部地址: {hostname}")

    # 尝试按 IP 地址解析并检查是否为私有/回环/链路本地
    try:
        # IPv6 字面量会带 []，urlparse 返回的 hostname 已去掉括号
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
            raise ValueError(f"base_url 指向私有/回环/链路本地地址: {hostname}")
    except ValueError:
        # 不是 IP 地址，继续按域名处理
        pass

    # 拒绝常见的 DNS rebinding / 内部域名后缀
    if hostname.endswith((".internal", ".local", ".localhost")):
        raise ValueError(f"base_url 指向内部域名: {hostname}")

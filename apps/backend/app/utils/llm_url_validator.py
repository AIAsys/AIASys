"""LLM 服务商 base_url 安全校验。

AIASys 是本地部署的桌面应用，用户有权配置本地/私有 LLM（如 Ollama、LM Studio）。
本校验只保留最基础的安全约束：协议、空 hostname、云厂商 metadata 地址。
"""

import ipaddress
from urllib.parse import urlparse

# 明确禁止的 hostname（不区分大小写）
# 仅保留云厂商 metadata 等已知的、非用户本地服务的内部地址
_BLOCKED_HOSTS = {
    "metadata.google.internal",
    "metadata.oracle.internal",
    "169.254.169.254",
}


def validate_llm_base_url(url: str) -> None:
    """校验 LLM 服务商 base_url 是否合法。

    拒绝：
    - 非 http/https 协议
    - 无 hostname
    - 常见云厂商 metadata 地址
    - 空字符串或明显非法格式

    允许：
    - localhost / 127.0.0.1 / ::1（本地 LLM 如 Ollama 常用）
    - 私有/回环/链路本地 IP
    - .local / .localhost 等本地域名

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
        raise ValueError(f"base_url 指向被禁止的云 metadata 地址: {hostname}")

    # 拒绝云厂商链路本地 metadata IP
    addr = None
    try:
        # IPv6 字面量会带 []，urlparse 返回的 hostname 已去掉括号
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # 不是 IP 地址，继续按域名处理
        pass

    if addr is not None and addr.is_link_local and str(addr) == "169.254.169.254":
        raise ValueError(f"base_url 指向云 metadata 地址: {hostname}")

    # 拒绝明确的云内部域名后缀
    if hostname.endswith(".internal"):
        raise ValueError(f"base_url 指向内部域名: {hostname}")

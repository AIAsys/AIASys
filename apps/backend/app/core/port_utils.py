"""
端口探测与自动回退工具。

为独立后端（python main.py）和 dev.sh 提供端口冲突自动处理能力。
与桌面版 utils.cjs 的核心逻辑对齐，但保持简洁，只做端口级探测。
"""

import logging
import socket
from typing import Tuple

logger = logging.getLogger(__name__)

MAX_PORT_ATTEMPTS = 200


def probe_port(host: str, port: int) -> bool:
    """检查端口是否空闲（可绑定）。

    使用 connect 探测而非 bind 探测，避免 SO_REUSEADDR 在 Linux 上
    允许绑定已在监听端口的问题。

    Args:
        host: 绑定地址，如 "127.0.0.1"
        port: 端口号

    Returns:
        True 表示端口空闲，False 表示已被占用
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            # 尝试连接：连接成功 = 端口被占用，连接失败 = 端口空闲
            result = s.connect_ex((host, port))
            return result != 0
    except OSError:
        # 网络不可达等情况，保守地认为端口空闲
        return True


def find_available_port(
    host: str,
    start_port: int,
    max_attempts: int = MAX_PORT_ATTEMPTS,
    exclude_ports: set[int] | None = None,
) -> int:
    """从 start_port 开始扫描，找到第一个空闲端口。

    Args:
        host: 绑定地址
        start_port: 起始端口号
        max_attempts: 最大扫描范围
        exclude_ports: 需要排除的端口集合

    Returns:
        空闲端口号

    Raises:
        RuntimeError: 在扫描范围内未找到空闲端口
    """
    blocked = exclude_ports or set()
    for candidate in range(start_port, start_port + max_attempts):
        if candidate in blocked:
            continue
        if probe_port(host, candidate):
            return candidate

    raise RuntimeError(f"无法在 {start_port}~{start_port + max_attempts - 1} 范围内找到空闲端口")


def resolve_port(
    host: str,
    requested_port: int,
    locked: bool = False,
    label: str = "backend",
) -> Tuple[int, bool]:
    """解析端口，在冲突时自动回退或报错。

    决策逻辑：
    - 端口空闲 → 返回 (requested_port, False)
    - 端口被占用 + locked=True → 抛 RuntimeError
    - 端口被占用 + locked=False → 扫描回退，返回 (fallback_port, False)

    Args:
        host: 绑定地址
        requested_port: 请求的端口号
        locked: 是否锁定端口（不允许回退）。当用户显式设置环境变量时为 True
        label: 服务标签，用于日志输出

    Returns:
        (actual_port, reused): actual_port 为实际使用的端口，reused 始终为 False
                                （独立后端不做复用，仅做回退）

    Raises:
        RuntimeError: 端口被占用且 locked=True，或扫描范围内无可用端口
    """
    if probe_port(host, requested_port):
        return requested_port, False

    if locked:
        raise RuntimeError(
            f"{label} 端口 {requested_port} 已被占用，且当前通过环境变量锁定了该端口，不会自动回退"
        )

    fallback_port = find_available_port(host, requested_port + 1)
    logger.warning(f"{label} 端口 {requested_port} 已被占用，自动切换到 {fallback_port}")
    return fallback_port, False

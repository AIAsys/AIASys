"""跨平台编码自适应工具。

Windows 子进程输出通常是 GBK (cp936)，硬编码 UTF-8 解码会导致乱码。
本模块提供 smart_decode() 函数，按优先级尝试解码：
  1. UTF-8（最常见）
  2. locale.getpreferredencoding()（系统默认，Windows 上通常是 cp936）
  3. GBK（中文 Windows 的最终 fallback）
"""

from __future__ import annotations

import locale


def smart_decode(data: bytes) -> str:
    """自适应解码 bytes 为 str。

    按 UTF-8 → 系统 locale 编码 → GBK 的顺序尝试，
    使用 errors="replace" 确保不会因解码失败而抛出异常。
    """
    if not data:
        return ""

    # 优先 UTF-8
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # 尝试系统 locale 编码
    try:
        sys_enc = locale.getpreferredencoding(do_setlocale=False)
        if sys_enc and sys_enc.lower() not in ("utf-8", "utf8"):
            return data.decode(sys_enc, errors="replace")
    except (UnicodeDecodeError, LookupError):
        pass

    # 最终 fallback：GBK + replace
    return data.decode("gbk", errors="replace")

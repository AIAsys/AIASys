"""Agent 运行时异常定义。

独立模块，避免循环导入。
"""

from __future__ import annotations


class RunCancelled(Exception):
    """表示会话运行被用户主动取消。"""

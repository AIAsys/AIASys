"""验证工具函数"""

import re


def validate_id(id_str: str, name: str | None = None) -> bool:
    """验证 ID 格式（只允许字母、数字、下划线、连字符），不通过时抛出 ValueError。"""
    if not bool(re.match(r"^[a-zA-Z0-9_\-]+$", id_str)):
        raise ValueError(f"无效的{name or 'ID'}: {id_str}")
    return True

"""
MCP 集成测试

测试脚本说明:
- test_mcp_service.py: 测试 MCP 配置服务功能（无需启动后端）
- test_system_default_mcp.py: 测试系统默认 MCP 逻辑
- test_mcp_backend.py: 集成测试（需要启动后端和 MCP Server）
- start_with_mcp.sh: 启动脚本

使用方法:
1. 单元测试: cd apps/backend && python3 -m tests.mcp.test_mcp_service
2. 集成测试: 先启动服务，然后 python3 -m tests.mcp.test_mcp_backend
"""

import sys
from pathlib import Path

# 添加 backend 到路径
backend_dir = Path(__file__).parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

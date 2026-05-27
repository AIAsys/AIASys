"""API 路由"""

from fastapi import APIRouter

from app.graphrag.api.routes import router as graphrag_router

from .agent import router as agent_router
from .agent_config import router as agent_config_router
from .ask_user import router as ask_user_router
from .auth import router as auth_router
from .auto_tasks import router as auto_tasks_router
from .canvas import router as canvas_router
from .capabilities import router as capabilities_router
from .channels import router as channels_router
from .claw import router as claw_router
from .container_resources import router as container_resources_router
from .data_tables import router as data_tables_router
from .database_connectors import router as database_connectors_router
from .diff import router as diff_router
from .file_database import router as file_database_router
from .files import router as files_router
from .global_env_vars import router as global_env_vars_router
from .kernel_envs import router as kernel_envs_router
from .knowledge import router as knowledge_router
from .llm_config import router as llm_config_router
from .mcp import router as mcp_router
from .mcp_session import router as mcp_session_router
from .memory import router as memory_router
from .notebooks import router as notebooks_router
from .runtime_database import router as runtime_database_router
from .runtime_envs import router as runtime_envs_router
from .session_database import router as session_database_router
from .sessions import router as sessions_router
from .skills import router as skills_router
from .system import router as system_router
from .ui_settings import router as ui_settings_router
from .workspaces import router as workspaces_router

# 主路由
api_router = APIRouter(prefix="/api")

# 注册子路由
#  注意：sessions_router 有 /{user_id}/{session_id} 这种通配路径，
# 所以更具体的 MCP 路由（/{session_id}/mcp）必须优先注册
api_router.include_router(agent_router)
api_router.include_router(claw_router)
api_router.include_router(channels_router)
api_router.include_router(mcp_session_router)  # 会话级 MCP 路由（必须先于 sessions_router）
api_router.include_router(diff_router)
api_router.include_router(workspaces_router)
api_router.include_router(canvas_router)
api_router.include_router(auto_tasks_router)
api_router.include_router(data_tables_router)
api_router.include_router(sessions_router)
api_router.include_router(files_router)
api_router.include_router(notebooks_router)
api_router.include_router(capabilities_router)
api_router.include_router(skills_router)
api_router.include_router(system_router)
api_router.include_router(auth_router)
api_router.include_router(ask_user_router)
api_router.include_router(mcp_router)
api_router.include_router(memory_router)
api_router.include_router(ui_settings_router)
api_router.include_router(global_env_vars_router)
api_router.include_router(graphrag_router)
api_router.include_router(knowledge_router)  # 知识库路由
api_router.include_router(runtime_database_router)
api_router.include_router(runtime_envs_router)
api_router.include_router(container_resources_router)
api_router.include_router(database_connectors_router)
api_router.include_router(session_database_router)
api_router.include_router(file_database_router)
api_router.include_router(llm_config_router)  # LLM 配置路由
api_router.include_router(agent_config_router)  # Agent 配置路由
api_router.include_router(kernel_envs_router)  # Jupyter kernel 环境路由

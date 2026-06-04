"""
FastAPI 应用入口

基于 AIASys runtime backend 的 Agent 服务
支持认证方式：local/none
"""

# Windows WMI 绕过补丁：防止 platform.machine() 调用 WMI 时卡死
# 必须在任何可能触发 platform 导入的模块之前执行
import sys

if sys.platform == "win32":
    import platform

    def _wmi_query_noop(*args, **kwargs):
        raise OSError("WMI query disabled to avoid hang on frozen WMI service")

    platform._wmi_query = _wmi_query_noop

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.api.routes import api_router
from app.api.routes.terminal import router as terminal_router
from app.core.auth import (
    AuthenticationError,
    AuthorizationError,
    ensure_local_default_user_exists,
    get_auth_provider,
)
from app.core.config import (
    APP_NAME,
    APP_VERSION,
    AUTH_CONFIG,
    DEBUG,
    _check_data_format_version,
)
from app.core.database import init_db
from app.core.logging import setup_logging
from app.services.runtime_storage_settings import is_runtime_storage_migration_in_progress

# 设置日志
setup_logging()
logger = logging.getLogger(__name__)


def _log_task_exception(task: asyncio.Task) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        exc = task.exception()
        if exc is not None:
            logger.error("kernel 清理任务异常: %s", exc, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动
    logger.info(f" {APP_NAME} v{APP_VERSION} 启动")
    logger.info(f" 认证模式: {AUTH_CONFIG.mode}")

    # 检查数据格式版本
    try:
        _check_data_format_version()
        logger.info(" 数据格式版本检查通过")
    except Exception as e:
        logger.error(f" {e}")
        raise

    # 初始化数据库
    try:
        init_db()
        logger.info(" 数据库初始化成功")
    except Exception as e:
        logger.error(f" 数据库初始化失败: {e}")

    if AUTH_CONFIG.mode == "local":
        try:
            local_user = ensure_local_default_user_exists()
            logger.info(" 默认本地用户已就绪: %s", local_user.id)
        except Exception as e:
            logger.error(f" 默认本地用户初始化失败: {e}")

    # 同步 config.json → 用户 LLM 配置（仅在用户配置为空时执行）
    try:
        from app.services.llm import get_llm_config_service

        llm_service = get_llm_config_service()
        llm_service.sync_config_json_to_user("local_default")
        logger.info(" 用户 LLM 配置同步完成")
    except Exception as e:
        logger.warning(f" 用户 LLM 配置同步失败（不影响服务）: {e}")

    # 预热认证提供者
    try:
        provider = get_auth_provider()
        logger.info(f" 认证提供者初始化成功: {provider.__class__.__name__}")
    except Exception as e:
        logger.error(f" 认证提供者初始化失败: {e}")

    # 启动自动任务引擎
    try:
        from app.services.auto_tasks import ensure_auto_tasks_running

        ensure_auto_tasks_running()
        logger.info(" 自动任务引擎已启动")
    except Exception as e:
        logger.warning(f" 自动任务引擎启动失败（不影响服务）: {e}")

    # 恢复 Claw 常驻 runtime，保证 session 级通信绑定在服务重启后继续生效
    try:
        from app.services.claw_runtime import ensure_claw_runtime_running

        ensure_claw_runtime_running()
        logger.info(" Claw runtime manager 已调度启动")
    except Exception as e:
        logger.warning(f" Claw runtime manager 启动失败（不影响服务）: {e}")

    # 启动时尝试追加写入上次遗留的 Stage 1 memory 产物
    memory_stage2_task = None
    try:
        from app.services.memory import schedule_stage2_consolidation

        memory_stage2_task = schedule_stage2_consolidation(user_id="local_default")
        logger.info(" Memory Stage 2 后台追加写入已调度")
    except Exception as e:
        logger.warning(f" Memory Stage 2 后台追加写入调度失败（不影响服务）: {e}")

    # 启动 kernel 空闲清理循环
    kernel_cleanup_task = None
    try:
        import asyncio

        from app.agents.tools.local_ipython_box import LocalIPythonBox

        async def _kernel_cleanup_loop():
            while True:
                await asyncio.sleep(300)
                try:
                    count = LocalIPythonBox.cleanup_idle_kernels()
                    if count:
                        logger.info(" 自动清理 %d 个空闲 kernel", count)
                except Exception as exc:
                    logger.warning(" kernel 空闲清理失败: %s", exc)

        kernel_cleanup_task = asyncio.create_task(_kernel_cleanup_loop())
        kernel_cleanup_task.add_done_callback(_log_task_exception)
        logger.info(" Kernel 空闲清理循环已启动（间隔 5 分钟）")
    except Exception as e:
        logger.warning(f" Kernel 空闲清理循环启动失败（不影响服务）: {e}")

    yield

    if memory_stage2_task is not None:
        memory_stage2_task.cancel()

    if kernel_cleanup_task is not None:
        kernel_cleanup_task.cancel()

    try:
        from app.services.claw_runtime import shutdown_claw_runtime_manager

        await shutdown_claw_runtime_manager()
        logger.info(" Claw runtime manager 已停止")
    except Exception as e:
        logger.warning(f" Claw runtime manager 停止失败（忽略）: {e}")

    # 清理所有终端 PTY 会话
    try:
        from app.services.terminal.pty_manager import get_pty_manager

        await get_pty_manager().kill_all()
        logger.info(" 终端 PTY 会话已清理")
    except Exception as e:
        logger.warning(f" 终端 PTY 清理失败（忽略）: {e}")

    logger.info(f" {APP_NAME} 关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    debug=DEBUG,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    lifespan=lifespan,
)

# CORS 中间件 - 使用配置中的值
app.add_middleware(
    CORSMiddleware,
    allow_origins=AUTH_CONFIG.cors_origins,
    allow_credentials=AUTH_CONFIG.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],  # 暴露自定义 headers
)


# SSE 流式端点路径 —— 跳过 BaseHTTPMiddleware 包裹，避免缓冲
_SSE_PATHS = {"/api/agent/execute/stream"}
_STORAGE_MIGRATION_ALLOWED_PREFIXES = (
    "/api/system/storage-settings",
    "/api/auth",
)
_STORAGE_MIGRATION_ALLOWED_PATHS = {
    "/health",
    "/health/auth",
}


def _storage_migration_allows_request(request: Request) -> bool:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return True
    path = request.url.path
    if path in _STORAGE_MIGRATION_ALLOWED_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in _STORAGE_MIGRATION_ALLOWED_PREFIXES)


@app.middleware("http")
async def storage_migration_guard_middleware(request: Request, call_next):
    """存储迁移期间拒绝普通写操作，避免复制过程中继续写旧目录。"""
    if (
        request.url.path.startswith("/api/")
        and not _storage_migration_allows_request(request)
        and is_runtime_storage_migration_in_progress()
    ):
        return JSONResponse(
            status_code=423,
            content={
                "error": "storage_migration_in_progress",
                "message": "存储迁移正在进行，完成前暂时不能操作。",
                "path": request.url.path,
            },
        )
    return await call_next(request)


def _is_inline_file_preview(request: Request, response: Response | None = None) -> bool:
    if not request.url.path.startswith("/api/files/download/"):
        return False

    if request.query_params.get("disposition") == "inline":
        return True

    if response is None:
        return False

    content_disposition = response.headers.get("content-disposition", "")
    return content_disposition.lower().startswith("inline")


# 安全 Headers 中间件
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """添加安全相关的 HTTP Headers（SSE 端点跳过以避免流缓冲）"""
    if request.url.path in _SSE_PATHS:
        return await call_next(request)

    response = await call_next(request)

    if AUTH_CONFIG.enable_security_headers:
        is_inline_preview = _is_inline_file_preview(request, response)
        # 防止 MIME 类型嗅探
        response.headers["X-Content-Type-Options"] = "nosniff"
        if not is_inline_preview:
            # XSS 保护
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            # 内容安全策略（可根据需要调整）
            response.headers["Content-Security-Policy"] = "default-src 'self'"
        else:
            for header_name in (
                "X-Frame-Options",
                "X-XSS-Protection",
                "Content-Security-Policy",
            ):
                if header_name in response.headers:
                    del response.headers[header_name]
        # 添加请求 ID 便于追踪
    request_id = request.headers.get("X-Request-ID")
    if request_id:
        response.headers["X-Request-ID"] = request_id

    return response


# 调试中间件：仅在调试模式下记录请求 Cookie
@app.middleware("http")
async def debug_cookie_middleware(request: Request, call_next):
    """调试 Cookie 传递（SSE 端点跳过以避免流缓冲）"""
    if request.url.path in _SSE_PATHS:
        return await call_next(request)

    if DEBUG and "/api/" in request.url.path:
        cookies = dict(request.cookies)
        has_auth = any(
            k.endswith("authjs.session-token") or k.endswith("next-auth.session-token")
            for k in cookies.keys()
        )
        logger.debug(
            "[DEBUG] [%s] %s - Cookies: %s items, has_auth: %s, Cookie keys: %s",
            request.method,
            request.url.path,
            len(cookies),
            has_auth,
            list(cookies.keys()),
        )
    return await call_next(request)


# 注册路由
app.include_router(api_router)
app.include_router(terminal_router)


# 认证/授权异常处理
@app.exception_handler(AuthenticationError)
async def authentication_exception_handler(request: Request, exc: AuthenticationError):
    """处理认证错误"""
    logger.warning(f"认证失败: {request.url.path} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "authentication_error",
            "message": exc.detail,
            "path": request.url.path,
        },
    )


@app.exception_handler(AuthorizationError)
async def authorization_exception_handler(request: Request, exc: AuthorizationError):
    """处理授权错误"""
    logger.warning(f"授权失败: {request.url.path} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "authorization_error",
            "message": exc.detail,
            "path": request.url.path,
        },
    )


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """处理未捕获的异常"""
    logger.exception(f"未处理的异常: {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "Internal server error" if not DEBUG else str(exc),
            "path": request.url.path,
        },
    )


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "ok",
        "app": APP_NAME,
        "version": APP_VERSION,
        "auth_mode": AUTH_CONFIG.mode,
    }


@app.get("/health/auth")
async def auth_health_check():
    """
    认证健康检查

    可用于验证认证配置是否正确
    """
    return {
        "auth_mode": AUTH_CONFIG.mode,
        "cors_origins": AUTH_CONFIG.cors_origins,
    }


if __name__ == "__main__":
    import uvicorn

    from app.core.config import PORT

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=PORT,
        reload=DEBUG,
    )

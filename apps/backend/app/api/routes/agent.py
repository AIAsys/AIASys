"""
Agent API 路由

基于 AIASys runtime backend 的 Agent 执行接口，
支持历史会话恢复、文件上传、多用户隔离和认证
"""

import asyncio
import contextlib
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.auth import (
    AuthenticationError,
    require_auth,
)
from app.models.user import UserInfo
from app.services.agent import agent_service
from app.services.workspace_registry import get_workspace_registry_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


def _log_task_exception(task: asyncio.Task) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        exc = task.exception()
        if exc is not None:
            logger.error("Agent 后台任务异常: %s", exc, exc_info=True)


class AgentExecuteRequest(BaseModel):
    """Agent 执行请求"""

    prompt: str = Field(..., description="用户提示词")
    # user_id 变为可选，因为可以从认证信息获取
    user_id: str | None = Field(None, description="用户 ID（可选，优先使用认证信息）")
    workspace_id: str | None = Field(
        default=None,
        description="当前工作区 ID；提供时后端会校验 session 是否属于该工作区",
    )
    session_id: str = Field(..., description="会话 ID")
    model: str | None = Field(
        None, description="模型名称（如 kimi-for-coding），默认使用配置中的默认模型"
    )
    model_id: str | None = Field(
        None, description="模型配置 ID（如 my-kimi-model），优先使用，默认使用配置中的默认模型"
    )
    attachments: list[str] | None = Field(
        default=None,
        description="当前轮附带的工作区文件路径或文件名列表",
    )
    references: list[str] | None = Field(
        default=None,
        description="当前轮显式引用的资源、专家或能力 ID，区别于文件附件",
    )
    thinking_enabled: bool | None = Field(
        default=None,
        description="是否启用 reasoning / thinking 模式；None 表示由模型配置决定",
    )
    thinking_effort: str | None = Field(
        default=None,
        description="thinking 强度：low / medium / high；仅 thinking_enabled 为 True 时生效",
    )


class AgentStopRequest(BaseModel):
    """中断请求"""

    session_id: str = Field(..., description="会话 ID")
    user_id: str | None = Field(None, description="用户 ID")


def _resolve_user_id(request: AgentExecuteRequest, user: UserInfo) -> str:
    """
    解析最终使用的 user_id

    优先级：
    1. 请求中的 user_id（如果提供）
    2. 认证信息中的 user_id

    如果请求中的 user_id 与认证用户不一致，检查是否有权限
    """
    if request.user_id:
        # 检查是否有权访问该用户的数据
        if not user.can_access_user_data(request.user_id):
            raise AuthenticationError(f"You cannot access data for user: {request.user_id}")
        return request.user_id
    return user.user_id


def _resolve_requested_user_id(request_user_id: str | None, user: UserInfo) -> str:
    if request_user_id:
        if not user.can_access_user_data(request_user_id):
            raise AuthenticationError(f"You cannot access data for user: {request_user_id}")
        return request_user_id
    return user.user_id


def _validate_workspace_binding(
    *,
    user_id: str,
    session_id: str,
    workspace_id: str | None,
) -> None:
    if not workspace_id:
        return
    resolved_workspace_id = get_workspace_registry_service().find_workspace_id_by_session_id(
        user_id,
        session_id,
    )
    if resolved_workspace_id != workspace_id:
        logger.warning(
            "workspace binding 校验失败: user=%s session=%s "
            "request_workspace=%s resolved_workspace=%s",
            user_id,
            session_id,
            workspace_id,
            resolved_workspace_id,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": "session_id 与 workspace_id 不匹配",
                "workspace_id": workspace_id,
                "resolved_workspace_id": resolved_workspace_id,
                "session_id": session_id,
            },
        )


@router.post("/execute/stream")
async def execute_stream(request: AgentExecuteRequest, user: UserInfo = Depends(require_auth())):
    """
    流式执行 Agent 任务

    使用 SSE 实时返回执行进度和结果
    支持历史会话恢复，保持上下文连续性

    文件访问：
    - 用户上传的文件在 /workspace/ 目录下
    - Agent 可以读写该目录进行文件处理
    """
    # 解析用户ID
    user_id = _resolve_user_id(request, user)

    logger.info(
        "Agent execute_stream 请求: user=%s session=%s workspace=%s model_id=%s",
        user_id,
        request.session_id,
        request.workspace_id,
        request.model_id,
    )

    # 懒创建/绑定 workspace conversation：
    # - session 不存在：创建新的 workspace conversation
    # - session 已存在但未绑定到任何 workspace（例如 /status 自动创建的草稿）：
    #   将其绑定到请求中的 workspace_id，避免后续 workspace binding 校验失败
    existing_metadata = agent_service._session_manager.get_session(request.session_id, user_id)
    resolved_workspace_id: str | None = None
    if existing_metadata:
        resolved_workspace_id = get_workspace_registry_service().find_workspace_id_by_session_id(
            user_id,
            request.session_id,
        )

    if request.workspace_id and (not existing_metadata or not resolved_workspace_id):
        try:
            get_workspace_registry_service().create_conversation(
                user_id=user_id,
                workspace_id=request.workspace_id,
                title="新会话",
                conversation_id=request.session_id,
                make_current=True,
            )
            logger.info(
                "懒创建/绑定 workspace conversation 成功: user=%s session=%s workspace=%s "
                "existing_session=%s",
                user_id,
                request.session_id,
                request.workspace_id,
                bool(existing_metadata),
            )
        except Exception as e:
            logger.warning(f"懒创建 workspace conversation 失败（继续执行）: {e}")

    _validate_workspace_binding(
        user_id=user_id,
        session_id=request.session_id,
        workspace_id=request.workspace_id,
    )

    async def event_stream():
        """SSE 流式响应，内置 15 秒心跳保活。

        使用 asyncio.Queue 将事件生产和心跳发送解耦：
        - producer task 消费 agent_service.execute_stream() 的事件
        - heartbeat task 每 15 秒注入一个 heartbeat 事件
        - 主循环从队列取出事件并 yield
        """
        done_sent = False
        queue: asyncio.Queue = asyncio.Queue()

        async def producer():
            try:
                async for event in agent_service.execute_stream(
                    prompt=request.prompt,
                    user_id=user_id,
                    session_id=request.session_id,
                    model=request.model,
                    model_id=request.model_id,
                    attachments=request.attachments,
                    references=request.references,
                    thinking_enabled=request.thinking_enabled,
                    thinking_effort=request.thinking_effort,
                ):
                    await queue.put(("event", event))
            except Exception as e:
                await queue.put(("error", e))
            finally:
                await queue.put(("done", None))

        async def heartbeat_sender():
            while True:
                await asyncio.sleep(15)
                await queue.put(("heartbeat", None))

        producer_task = asyncio.create_task(producer())
        producer_task.add_done_callback(_log_task_exception)
        heartbeat_task = asyncio.create_task(heartbeat_sender())
        heartbeat_task.add_done_callback(_log_task_exception)

        try:
            while True:
                item_type, item = await queue.get()
                if item_type == "done":
                    break
                elif item_type == "heartbeat":
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                elif item_type == "error":
                    logger.error(f"流式执行失败: {item}")
                    if not done_sent:
                        yield f"data: {json.dumps({'type': 'error', 'message': str(item)})}\n\n"
                elif item_type == "event":
                    event = item
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "status" and event.get("message") == "清理资源...":
                        yield "data: [DONE]\n\n"
                        done_sent = True
        except Exception as e:
            logger.error(f"流式执行失败: {e}")
            if not done_sent:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            # 清理后台任务
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
            if not producer_task.done():
                producer_task.cancel()
                try:
                    await producer_task
                except (asyncio.CancelledError, Exception):
                    pass
            # SSE 结束标记。放在 finally，避免普通异常分支或生成器收尾路径漏发。
            if not done_sent:
                try:
                    yield "data: [DONE]\n\n"
                except Exception:
                    pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        },
    )


@router.post("/stop")
async def stop_stream(request: AgentStopRequest, user: UserInfo = Depends(require_auth())):
    """
    停止流式执行 Agent 任务
    """
    user_id = _resolve_requested_user_id(request.user_id, user)
    try:
        await agent_service.stop_session(user_id, request.session_id)
        return {"success": True}
    except Exception as e:
        logger.error(f"中断执行失败: {e}")
        raise HTTPException(status_code=500, detail="Internal execution error") from e


@router.get("/execution/{user_id}/{session_id}/flow")
async def get_execution_flow(
    user_id: str,
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """
    获取本地执行流历史（Notebook 风格）
    """
    if not current_user.can_access_user_data(user_id):
        raise AuthenticationError("Access denied")

    try:
        from app.services.agent import get_work_dir
        from app.services.history import SessionExecutionJournal

        work_dir = get_work_dir(user_id, session_id)
        journal_work_dir = Path(str(work_dir))

        journal = SessionExecutionJournal(journal_work_dir, session_id)
        journal_history = []
        if journal.has_structure():
            try:
                records = journal.list_records()
                for record in records:
                    # 只包含 IPythonBox 和 LocalIPythonBox 的记录
                    if record.origin.tool_name == "LocalIPythonBox":
                        # 读取 stdout 和 stderr 产物
                        stdout_path = journal.stdout_dir / f"{record.record_id}.log"
                        stderr_path = journal.stderr_dir / f"{record.record_id}.log"
                        stdout = (
                            stdout_path.read_text(encoding="utf-8") if stdout_path.exists() else ""
                        )
                        stderr = (
                            stderr_path.read_text(encoding="utf-8") if stderr_path.exists() else ""
                        )

                        # 解析时间戳为秒级时间戳
                        try:
                            ts = datetime.fromisoformat(record.started_at).timestamp()
                        except Exception:
                            ts = datetime.now().timestamp()

                        journal_history.append(
                            {
                                "code": record.code,
                                "stdout": stdout,
                                "stderr": stderr,
                                "success": record.status == "completed",
                                "timestamp": ts,
                            }
                        )
            except Exception as journal_err:
                logger.warning(f"读取 SessionExecutionJournal 失败: {journal_err}")

        journal_history.sort(key=lambda x: x.get("timestamp", ""))
        return {"history": journal_history}
    except Exception as e:
        logger.error(f"获取执行流失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取执行流失败: {e}") from e

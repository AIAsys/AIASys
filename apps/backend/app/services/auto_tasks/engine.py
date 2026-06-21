"""
自动任务引擎。

基于 asyncio 的轮询与 continuous 触发事件运行，使用工作区本地 JSON 存储。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
import threading
from datetime import datetime, timedelta
from pathlib import Path

from app.utils.path_utils import as_system_path
from typing import Any

from croniter import croniter
from filelock import FileLock

from app.core.config import WORKSPACE_DIR
from app.services.auto_tasks.execution_result import (
    non_execution_error_message,
    record_execution_failure,
    record_execution_success,
    result_executed,
)
from app.services.auto_tasks.models import (
    MIN_INTERVAL_SECONDS,
    AutoTask,
    AutoTaskTriggerType,
    FirstRunPolicy,
    OverlapPolicy,
    TaskCategory,
    TaskStatus,
)

logger = logging.getLogger(__name__)

# 轮询粒度与最小秒级间隔保持一致，避免用户以为能比最小间隔更快触发。
_POLL_INTERVAL_SECONDS = MIN_INTERVAL_SECONDS
_ERROR_BACKOFF_SECONDS = [30, 60, 300, 900]
_MISS_THRESHOLD_SECONDS = 60

_auto_tasks_task: asyncio.Task | None = None
_running_locks: dict[str, asyncio.Lock] = {}
_running_locks_create_lock = threading.Lock()
_continuous_event = asyncio.Event()
# 全局并发上限：同时执行的自动任务不超过 8 个
_MAX_CONCURRENT_TASKS = 8
_task_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_TASKS)


def _get_task_lock(task_id: str) -> asyncio.Lock:
    with _running_locks_create_lock:
        if task_id not in _running_locks:
            _running_locks[task_id] = asyncio.Lock()
        return _running_locks[task_id]


def _cleanup_task_lock(task_id: str) -> None:
    """任务删除后清理对应的执行锁，防止内存泄漏。"""
    _running_locks.pop(task_id, None)


_AUTO_TASKS_DIR_NAME = "auto_tasks"


def _now() -> datetime:
    return datetime.now()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    text = str(value).strip()
    if not text:
        return None

    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except Exception:
        return None

    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed


def _auto_tasks_dir(user_id: str, workspace_id: str) -> Path:
    return (
        Path(WORKSPACE_DIR)
        / user_id
        / workspace_id
        / ".aiasys"
        / "workspace"
        / _AUTO_TASKS_DIR_NAME
    )


def _tasks_file(user_id: str, workspace_id: str) -> Path:
    return _auto_tasks_dir(user_id, workspace_id) / "tasks.json"


def _workspace_root(user_id: str, workspace_id: str) -> Path:
    return Path(WORKSPACE_DIR) / user_id / workspace_id


def _workspace_meta_file(user_id: str, workspace_id: str) -> Path:
    return _workspace_root(user_id, workspace_id) / ".aiasys" / "workspace" / "workspace.json"


def _ensure_auto_tasks_dir(user_id: str, workspace_id: str) -> Path:
    directory = _auto_tasks_dir(user_id, workspace_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _calculate_next_run(task: AutoTask, after: datetime | None = None) -> datetime | None:
    base = after or _now()
    if task.status != TaskStatus.active:
        return None

    if task.trigger_type == AutoTaskTriggerType.once:
        target = _parse_datetime(task.trigger_value)
        if target is None:
            return None
        if task.last_run_at:
            return None
        return target

    if task.task_category == TaskCategory.continuous:
        return base

    first_run_policy = getattr(task, "first_run_policy", FirstRunPolicy.next_scheduled)
    first_run_anchor = _parse_datetime(task.updated_at) or _parse_datetime(task.created_at) or base

    if task.trigger_type == AutoTaskTriggerType.interval:
        try:
            interval_seconds = int(task.trigger_value)
        except Exception:
            return None
        if interval_seconds <= 0:
            return None
        if task.last_run_at:
            last_run = _parse_datetime(task.last_run_at) or base
            return last_run + timedelta(seconds=interval_seconds)
        if first_run_policy == FirstRunPolicy.immediate:
            return base
        return first_run_anchor + timedelta(seconds=interval_seconds)

    if task.trigger_type == AutoTaskTriggerType.cron:
        if not task.last_run_at and first_run_policy == FirstRunPolicy.immediate:
            return base
        try:
            # 使用上次执行时间作为锚点，避免轮询时把当前时间当锚点导致
            # "永远差一个轮询间隔" 而触发不了的问题。
            last_run = _parse_datetime(task.last_run_at) if task.last_run_at else None
            anchor = last_run if last_run is not None else first_run_anchor
            iterator = croniter(task.trigger_value, anchor)
            return iterator.get_next(datetime)
        except Exception as exc:
            logger.warning("cron 表达式解析失败: %s, error=%s", task.trigger_value, exc)
            return None

    return None


def _is_task_due(task: AutoTask) -> bool:
    if task.status != TaskStatus.active:
        return False
    if _get_task_lock(task.task_id).locked():
        return False

    if task.consecutive_errors > 0 and task.last_run_at:
        backoff = _ERROR_BACKOFF_SECONDS[
            min(task.consecutive_errors, len(_ERROR_BACKOFF_SECONDS)) - 1
        ]
        last_run = _parse_datetime(task.last_run_at)
        if last_run is not None and (_now() - last_run).total_seconds() < backoff:
            return False

    next_run = _calculate_next_run(task)
    if next_run is None:
        return False
    return _now() >= next_run


def _maybe_mark_completed(task: AutoTask) -> bool:
    if task.trigger_type != AutoTaskTriggerType.once:
        return False
    target = _parse_datetime(task.trigger_value)
    if target is None:
        return False
    if _now() >= target and task.status == TaskStatus.active:
        task.status = TaskStatus.completed
        return True
    return False


class AutoTaskStore:
    """基于 JSON 文件的任务存储（文件级互斥锁保护）"""

    _file_locks: dict[str, FileLock] = {}

    @classmethod
    def _get_lock(cls, user_id: str, workspace_id: str) -> FileLock:
        key = f"{user_id}:{workspace_id}"
        if key not in cls._file_locks:
            lock_path = _auto_tasks_dir(user_id, workspace_id) / ".tasks.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            cls._file_locks[key] = FileLock(str(lock_path))
        return cls._file_locks[key]

    @staticmethod
    def list_tasks(user_id: str, workspace_id: str) -> list[AutoTask]:
        path = _tasks_file(user_id, workspace_id)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            tasks = [AutoTask.from_dict(item) for item in data]
        except Exception as exc:
            logger.warning("读取自动任务失败: %s, error=%s", path, exc)
            return []

        return tasks

    @staticmethod
    def save_tasks(user_id: str, workspace_id: str, tasks: list[AutoTask]) -> None:
        path = _tasks_file(user_id, workspace_id)
        _ensure_auto_tasks_dir(user_id, workspace_id)
        path.write_text(
            json.dumps([task.to_dict() for task in tasks], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def get_task(user_id: str, workspace_id: str, task_id: str) -> AutoTask | None:
        for task in AutoTaskStore.list_tasks(user_id, workspace_id):
            if task.task_id == task_id:
                return task
        return None

    @staticmethod
    def put_task(user_id: str, workspace_id: str, task: AutoTask) -> None:
        with AutoTaskStore._get_lock(user_id, workspace_id):
            tasks = AutoTaskStore.list_tasks(user_id, workspace_id)
            for index, current in enumerate(tasks):
                if current.task_id == task.task_id:
                    tasks[index] = task
                    break
            else:
                tasks.append(task)
            AutoTaskStore.save_tasks(user_id, workspace_id, tasks)

    @staticmethod
    def delete_task(user_id: str, workspace_id: str, task_id: str) -> bool:
        with AutoTaskStore._get_lock(user_id, workspace_id):
            tasks = AutoTaskStore.list_tasks(user_id, workspace_id)
            filtered_tasks = [task for task in tasks if task.task_id != task_id]
            if len(filtered_tasks) == len(tasks):
                return False
            if filtered_tasks:
                AutoTaskStore.save_tasks(user_id, workspace_id, filtered_tasks)
            else:
                AutoTaskStore.clear_workspace(user_id, workspace_id)
            _cleanup_task_lock(task_id)
            return True

    @staticmethod
    def clear_workspace(user_id: str, workspace_id: str) -> None:
        with AutoTaskStore._get_lock(user_id, workspace_id):
            # 清理该工作区所有任务的执行锁
            for task in AutoTaskStore.list_tasks(user_id, workspace_id):
                _cleanup_task_lock(task.task_id)

            tasks_path = _tasks_file(user_id, workspace_id)
            auto_tasks_dir = _auto_tasks_dir(user_id, workspace_id)
            workspace_dir = _workspace_root(user_id, workspace_id)

            if tasks_path.exists():
                tasks_path.unlink()

            for candidate in (auto_tasks_dir, auto_tasks_dir.parent, workspace_dir):
                try:
                    candidate.rmdir()
                except OSError:
                    continue

            workspace_meta = _workspace_meta_file(user_id, workspace_id)
            if not workspace_meta.exists() and workspace_dir.exists():
                try:
                    shutil.rmtree(as_system_path(str(workspace_dir)))
                except OSError:
                    pass

    @staticmethod
    def all_tasks_across_workspaces() -> list[tuple[str, str, AutoTask]]:
        results: list[tuple[str, str, AutoTask]] = []
        base_dir = Path(WORKSPACE_DIR)
        if not base_dir.exists():
            return results
        for user_dir in base_dir.iterdir():
            if user_dir.name.startswith(".") or not user_dir.is_dir():
                continue
            user_id = user_dir.name
            for workspace_dir in user_dir.iterdir():
                if workspace_dir.name.startswith(".") or not workspace_dir.is_dir():
                    continue
                workspace_id = workspace_dir.name
                tasks_path = (
                    workspace_dir / ".aiasys" / "workspace" / _AUTO_TASKS_DIR_NAME / "tasks.json"
                )
                if not tasks_path.exists():
                    continue
                if not (workspace_dir / ".aiasys" / "workspace" / "workspace.json").exists():
                    logger.warning(
                        "发现缺少 workspace 元数据的孤儿自动任务目录，已清理: user=%s workspace=%s",
                        user_id,
                        workspace_id,
                    )
                    AutoTaskStore.clear_workspace(user_id, workspace_id)
                    continue
                try:
                    payload = json.loads(tasks_path.read_text(encoding="utf-8"))
                    if not isinstance(payload, list):
                        continue
                    for item in payload:
                        results.append((user_id, workspace_id, AutoTask.from_dict(item)))
                except Exception as exc:
                    logger.warning("扫描自动任务失败: %s, error=%s", tasks_path, exc)
        return results


def _effective_overlap_policy(task: AutoTask) -> OverlapPolicy:
    overlap_policy = getattr(task, "overlap_policy", OverlapPolicy.skip)

    # 绑定会话时 parallel 无意义（没有新建 Session 的场景），退化为 skip。
    if task.bind_session_id and overlap_policy == OverlapPolicy.parallel:
        return OverlapPolicy.skip
    return overlap_policy


def _queue_pending_run(task: AutoTask) -> int:
    with AutoTaskStore._get_lock(task.user_id, task.workspace_id):
        current = AutoTaskStore.get_task(task.user_id, task.workspace_id, task.task_id)
        target = current or task
        target.pending_run_count = int(target.pending_run_count or 0) + 1
        AutoTaskStore.put_task(task.user_id, task.workspace_id, target)
        return target.pending_run_count


def _overlap_result(reason: str, *, pending_run_count: int | None = None) -> dict:
    result = {
        "executed": False,
        "execution_reason": reason,
    }
    if pending_run_count is not None:
        result["pending_run_count"] = pending_run_count
    return result


def _log_task_exception(task: asyncio.Task[Any]) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        exc = task.exception()
        if exc is not None:
            logger.error("自动任务执行异常: %s", exc, exc_info=True)


async def _run_task_with_lock(task: AutoTask) -> None:
    try:
        overlap_policy = _effective_overlap_policy(task)

        # parallel 模式：不锁，直接并发执行
        if overlap_policy == OverlapPolicy.parallel:
            t = asyncio.create_task(_execute_and_persist(task))
            t.add_done_callback(_log_task_exception)
            return

        # skip / queue 模式：同一 task 同一时间只允许一个在执行
        lock = _get_task_lock(task.task_id)
        if lock.locked():
            if overlap_policy == OverlapPolicy.queue:
                pending_run_count = _queue_pending_run(task)
                logger.info(
                    "任务正在执行中，排队等候: task=%s pending=%s",
                    task.task_id,
                    pending_run_count,
                )
            else:
                logger.info(
                    "任务正在执行中，跳过本次: task=%s",
                    task.task_id,
                )
            return

        async with lock:
            await _execute_and_persist(task)
    except Exception:
        logger.error(
            "自动任务执行异常: task=%s workspace=%s user=%s",
            task.task_id,
            task.workspace_id,
            task.user_id,
            exc_info=True,
        )


async def run_task_now_with_lock(
    task: AutoTask,
    *,
    origin: str = "auto_task_manual_run",
) -> dict:
    """立即执行一次任务，并复用引擎级 task 锁与重叠策略。"""
    overlap_policy = _effective_overlap_policy(task)

    if overlap_policy != OverlapPolicy.parallel:
        lock = _get_task_lock(task.task_id)
        if lock.locked():
            if overlap_policy == OverlapPolicy.queue:
                pending_run_count = _queue_pending_run(task)
                logger.info(
                    "任务正在执行中，立即运行已排队: task=%s pending=%s",
                    task.task_id,
                    pending_run_count,
                )
                return _overlap_result(
                    "overlap_queued_until_previous_auto_task_branch_finishes",
                    pending_run_count=pending_run_count,
                )

            logger.info("任务正在执行中，立即运行按 skip 策略跳过: task=%s", task.task_id)
            return _overlap_result("overlap_skipped_active_auto_task_branch")

        async with lock:
            return await _execute_and_persist(
                task,
                origin=origin,
                manual_run=True,
            )

    return await _execute_and_persist(
        task,
        origin=origin,
        manual_run=True,
    )


async def _execute_and_persist(
    task: AutoTask,
    *,
    origin: str = "auto_task_loop",
    manual_run: bool = False,
) -> dict:
    from app.services.auto_tasks.executor import run_auto_task

    baseline_fired_count = int(task.fired_count or 0)
    workspace_missing = False
    run_succeeded = False
    result: dict | None = None
    try:
        try:
            logger.info(
                "触发自动任务: task=%s workspace=%s user=%s",
                task.task_id,
                task.workspace_id,
                task.user_id,
            )
            result = await run_auto_task(
                task,
                origin=origin,
                manual_run=manual_run,
            )
            run_succeeded = result_executed(result)
            if run_succeeded:
                record_execution_success(task)
            else:
                record_execution_failure(task, non_execution_error_message(result))
        except FileNotFoundError as exc:
            if str(exc).strip() == f"工作区不存在: {task.workspace_id}":
                workspace_missing = True
                logger.warning(
                    "自动任务目标工作区已不存在，清理孤儿任务: task=%s workspace=%s user=%s",
                    task.task_id,
                    task.workspace_id,
                    task.user_id,
                )
                result = {
                    "executed": False,
                    "execution_reason": "workspace_missing",
                    "error": str(exc),
                }
            else:
                record_execution_failure(task, str(exc))
                result = {
                    "executed": False,
                    "execution_reason": "execution_error",
                    "error": str(exc),
                }
                logger.error(
                    "自动任务执行失败: task=%s workspace=%s user=%s errors=%s error=%s",
                    task.task_id,
                    task.workspace_id,
                    task.user_id,
                    task.consecutive_errors,
                    exc,
                    exc_info=True,
                )
        except Exception as exc:
            record_execution_failure(task, str(exc))
            result = {
                "executed": False,
                "execution_reason": "execution_error",
                "error": str(exc),
            }
            logger.error(
                "自动任务执行失败: task=%s workspace=%s user=%s errors=%s error=%s",
                task.task_id,
                task.workspace_id,
                task.user_id,
                task.consecutive_errors,
                exc,
                exc_info=True,
            )
        finally:
            if workspace_missing:
                AutoTaskStore.clear_workspace(task.user_id, task.workspace_id)
                return result or _overlap_result("workspace_missing")
            current_task = AutoTaskStore.get_task(task.user_id, task.workspace_id, task.task_id)
            if current_task is None:
                return result or _overlap_result("task_missing_after_execution")

            current_task.consecutive_errors = task.consecutive_errors
            current_task.last_error = task.last_error
            current_task.last_run_at = _now().isoformat()
            if run_succeeded:
                current_task.fired_count = max(
                    int(current_task.fired_count or 0),
                    baseline_fired_count + 1,
                )
            if task.status != TaskStatus.active:
                current_task.status = task.status

            _maybe_mark_completed(current_task)
            next_run = _calculate_next_run(current_task)
            current_task.next_run_at = next_run.isoformat() if next_run else None

            if current_task.task_category == TaskCategory.continuous:
                max_cont = getattr(current_task, "max_continuations", -1) or -1
                if max_cont > 0 and int(current_task.fired_count or 0) >= max_cont:
                    current_task.status = TaskStatus.paused
                    logger.info(
                        "continuous 任务达到续杯上限，已暂停: task=%s fired=%s max=%s",
                        current_task.task_id,
                        current_task.fired_count,
                        max_cont,
                    )

            queued_followup = False
            if (
                current_task.status == TaskStatus.active
                and current_task.overlap_policy == OverlapPolicy.queue
                and int(current_task.pending_run_count or 0) > 0
            ):
                current_task.pending_run_count = int(current_task.pending_run_count or 0) - 1
                queued_followup = True

            AutoTaskStore.put_task(task.user_id, task.workspace_id, current_task)

            if queued_followup:
                t = asyncio.create_task(_execute_and_persist(current_task))
                t.add_done_callback(_log_task_exception)
            elif current_task.task_category == TaskCategory.continuous:
                _continuous_event.set()

            return result or _overlap_result("execution_returned_no_result")
    except Exception:
        logger.error(
            "自动任务持久化异常: task=%s workspace=%s user=%s",
            task.task_id,
            task.workspace_id,
            task.user_id,
            exc_info=True,
        )
        return _overlap_result("execution_persist_error")


def _recover_missed_tasks() -> list[AutoTask]:
    missed: list[AutoTask] = []
    now = _now()
    for _, _, task in AutoTaskStore.all_tasks_across_workspaces():
        if task.status != TaskStatus.active:
            continue
        next_run = _calculate_next_run(task)
        if next_run is None:
            continue
        if (now - next_run).total_seconds() > _MISS_THRESHOLD_SECONDS:
            missed.append(task)
    return missed


async def _auto_task_loop() -> None:
    logger.info("自动任务引擎轮询启动，间隔=%s秒", _POLL_INTERVAL_SECONDS)
    missed = _recover_missed_tasks()
    if missed:
        logger.info("恢复 %s 个错过的自动任务", len(missed))
        for task in missed:
            async with _task_semaphore:
                t = asyncio.create_task(_run_task_with_lock(task))
                t.add_done_callback(_log_task_exception)

    while True:
        try:
            for _, _, task in AutoTaskStore.all_tasks_across_workspaces():
                if _is_task_due(task):
                    async with _task_semaphore:
                        t = asyncio.create_task(_run_task_with_lock(task))
                        t.add_done_callback(_log_task_exception)
        except Exception as exc:
            logger.error("自动任务轮询异常: %s", exc, exc_info=True)
        try:
            await asyncio.wait_for(_continuous_event.wait(), timeout=_POLL_INTERVAL_SECONDS)
            _continuous_event.clear()
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            logger.info("自动任务轮询收到取消信号，正常退出")
            raise


def ensure_auto_tasks_running() -> None:
    """确保全局自动任务轮询任务已启动（幂等）。"""
    global _auto_tasks_task
    if _auto_tasks_task is not None and not _auto_tasks_task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("自动任务引擎启动时无运行中的事件循环，跳过")
        return
    _auto_tasks_task = loop.create_task(_auto_task_loop())
    _auto_tasks_task.add_done_callback(_log_task_exception)
    logger.info("自动任务引擎已启动")


def stop_auto_tasks() -> None:
    """停止全局自动任务轮询任务。"""
    global _auto_tasks_task
    if _auto_tasks_task is not None and not _auto_tasks_task.done():
        _auto_tasks_task.cancel()
        _auto_tasks_task = None
        logger.info("自动任务引擎已停止")

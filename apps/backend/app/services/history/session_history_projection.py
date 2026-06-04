import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.agent.message_content import build_content_signature
from app.services.runtime.session_runtime_state import (
    format_runtime_summary_for_prompt,
)

USER_PROMPT_EXECUTION_CONTRACT_HEADER = """[执行契约]
下面的 USER_TASK 就是用户当前要你执行的唯一任务。
- 不要把 USER_TASK 改写成别的任务
- 不要先自我介绍、寒暄、展示能力或要求用户再次描述需求
- 除非 USER_TASK 明确要求查看工作区文件，或当前轮 ATTACHED_FILES / RESOURCE_CONTEXT 已经指向相关文件，否则不要先扫描目录、列文件、看 CSV、看 Python 文件
- 如果 USER_TASK 明确点名了工具、步骤、顺序或约束，必须优先严格执行
- 如果 USER_TASK 只是简单问候且没有实际任务，可以简短回应；否则直接执行
- 对知识型任务，优先顺序是：当前轮附件与工作区文件 -> 当前任务挂载知识库 -> 当前任务主知识图谱 / 已挂载知识图谱 -> 其他工具
"""
USER_PROMPT_USER_TASK_MARKER = "[USER_TASK]"
USER_PROMPT_RUNTIME_CONTEXT_START = "[RUNTIME_CONTEXT]"
USER_PROMPT_RUNTIME_CONTEXT_END = "[/RUNTIME_CONTEXT]"
USER_PROMPT_RESOURCE_CONTEXT_START = "[RESOURCE_CONTEXT]"
USER_PROMPT_RESOURCE_CONTEXT_END = "[/RESOURCE_CONTEXT]"
USER_PROMPT_MESSAGE_SOURCE_START = "[MESSAGE_SOURCE]"
USER_PROMPT_MESSAGE_SOURCE_END = "[/MESSAGE_SOURCE]"
USER_PROMPT_EXECUTION_CONTRACT = (
    f"{USER_PROMPT_EXECUTION_CONTRACT_HEADER}\n\n{USER_PROMPT_USER_TASK_MARKER}\n"
)

DISPLAY_HISTORY_FILE_NAME = "display_history.jsonl"


def wrap_user_prompt(
    prompt: str,
    runtime_summary: dict[str, Any] | None = None,
    resource_context: str | None = None,
) -> str:
    runtime_context = format_runtime_summary_for_prompt(runtime_summary)
    normalized_resource_context = str(resource_context or "").strip()
    if not runtime_context and not normalized_resource_context:
        return f"{USER_PROMPT_EXECUTION_CONTRACT}{prompt}"

    sections = [USER_PROMPT_EXECUTION_CONTRACT_HEADER, ""]
    if runtime_context:
        sections.extend(
            [
                USER_PROMPT_RUNTIME_CONTEXT_START,
                runtime_context,
                USER_PROMPT_RUNTIME_CONTEXT_END,
                "",
            ]
        )
    if normalized_resource_context:
        sections.extend(
            [
                USER_PROMPT_RESOURCE_CONTEXT_START,
                normalized_resource_context,
                USER_PROMPT_RESOURCE_CONTEXT_END,
                "",
            ]
        )
    sections.extend([USER_PROMPT_USER_TASK_MARKER, prompt])
    return "\n".join(sections)


def unwrap_user_prompt(raw_content: Any) -> Optional[str]:
    if not isinstance(raw_content, str):
        return None
    if raw_content.startswith(USER_PROMPT_EXECUTION_CONTRACT):
        return raw_content[len(USER_PROMPT_EXECUTION_CONTRACT) :]
    if not raw_content.startswith(USER_PROMPT_EXECUTION_CONTRACT_HEADER):
        return None

    payload = raw_content[len(USER_PROMPT_EXECUTION_CONTRACT_HEADER) :].lstrip()
    context_blocks = (
        (USER_PROMPT_RUNTIME_CONTEXT_START, USER_PROMPT_RUNTIME_CONTEXT_END),
        (USER_PROMPT_RESOURCE_CONTEXT_START, USER_PROMPT_RESOURCE_CONTEXT_END),
        (USER_PROMPT_MESSAGE_SOURCE_START, USER_PROMPT_MESSAGE_SOURCE_END),
    )
    stripped = True
    while stripped:
        stripped = False
        for start_marker, end_marker in context_blocks:
            if payload.startswith(start_marker):
                end_index = payload.find(end_marker)
                if end_index >= 0:
                    payload = payload[end_index + len(end_marker) :].lstrip()
                    stripped = True
                    break

    if payload.startswith(USER_PROMPT_USER_TASK_MARKER):
        payload = payload[len(USER_PROMPT_USER_TASK_MARKER) :].lstrip()
    return payload


def get_session_sidecar_dir(workspace_path: Path, session_id: str) -> Path:
    return workspace_path / ".aiasys" / "session" / session_id


def append_display_history_entry(
    workspace_path: Path,
    session_id: str,
    *,
    role: str,
    content: Any,
    transport_content: Any | None = None,
) -> None:
    sidecar_dir = get_session_sidecar_dir(workspace_path, session_id)
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    display_history_path = sidecar_dir / DISPLAY_HISTORY_FILE_NAME

    entry: Dict[str, Any] = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    }
    if transport_content is not None:
        entry["transport_content"] = transport_content

    with open(display_history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_display_history_entries(
    workspace_path: Path,
    session_id: str,
) -> List[Dict[str, Any]]:
    display_history_path = (
        get_session_sidecar_dir(workspace_path, session_id) / DISPLAY_HISTORY_FILE_NAME
    )
    if not display_history_path.exists():
        return []

    entries: List[Dict[str, Any]] = []
    with open(display_history_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict) and entry.get("role") == "user":
                entries.append(entry)

    return entries


def match_display_entry(
    raw_content: Any,
    display_entries: List[Dict[str, Any]],
    start_index: int,
) -> tuple[Optional[Dict[str, Any]], int]:
    raw_signature = build_content_signature(raw_content)

    for index in range(start_index, len(display_entries)):
        entry = display_entries[index]
        entry_content = entry.get("content")
        entry_transport_content = entry.get("transport_content")

        if raw_signature is not None and raw_signature == build_content_signature(
            entry_transport_content
        ):
            return entry, index + 1
        if raw_signature is not None and raw_signature == build_content_signature(entry_content):
            return entry, index + 1
        if raw_signature is None and entry_transport_content == raw_content:
            return entry, index + 1
        if raw_signature is None and entry_content == raw_content:
            return entry, index + 1

    return None, start_index


def apply_display_content_to_history(
    history: List[Dict[str, Any]],
    display_entries: List[Dict[str, Any]],
    *,
    allow_older_orphan_entries: bool = False,
) -> List[Dict[str, Any]]:
    """将显示历史与 SDK 历史合并，确保所有用户消息都显示。

    处理场景：
    1. SDK history 和 display_history 正常匹配 - 正常合并
    2. SDK history 中缺失某些消息（但 display_history 中有）- 补充缺失的消息
    3. display_history 为空 - 使用 SDK history 的原始内容
    """
    hydrated_history: List[Dict[str, Any]] = []
    display_index = 0
    matched_display_indices: set[int] = set()
    latest_history_timestamp = ""

    # 第一遍：处理 SDK history 中的消息，并记录匹配的 display_entries
    for message in history:
        hydrated_message = dict(message)
        timestamp = hydrated_message.get("timestamp")
        if isinstance(timestamp, str) and timestamp > latest_history_timestamp:
            latest_history_timestamp = timestamp
        if hydrated_message.get("role") == "user":
            raw_content = hydrated_message.get("content")
            display_entry, new_display_index = match_display_entry(
                raw_content, display_entries, display_index
            )

            if display_entry is not None:
                # 记录实际匹配的 display_entry 索引（不是范围）
                matched_display_indices.add(new_display_index - 1)
                display_index = new_display_index

                display_content = display_entry.get("content")
                transport_content = display_entry.get("transport_content")
                if transport_content is not None:
                    hydrated_message["transport_content"] = transport_content

                if display_content is not None:
                    hydrated_message["display_content"] = display_content
                display_timestamp = display_entry.get("timestamp")
                if (
                    not isinstance(hydrated_message.get("timestamp"), str)
                    and isinstance(display_timestamp, str)
                    and display_timestamp
                ):
                    hydrated_message["timestamp"] = display_timestamp
            else:
                # 没有匹配的 display_entry，尝试解包原始内容
                unwrapped = unwrap_user_prompt(raw_content)
                if unwrapped != raw_content:
                    hydrated_message["display_content"] = unwrapped

        hydrated_history.append(hydrated_message)

    # 第二遍：补充 display_entries 中未匹配的消息（SDK 遗漏的消息）
    latest_matched_display_index = max(matched_display_indices) if matched_display_indices else None
    for i, entry in enumerate(display_entries):
        if i not in matched_display_indices and entry.get("role") == "user":
            if (
                not allow_older_orphan_entries
                and latest_matched_display_index is not None
                and i <= latest_matched_display_index
            ):
                continue
            entry_timestamp = entry.get("timestamp")
            if latest_history_timestamp and not allow_older_orphan_entries:
                if not isinstance(entry_timestamp, str):
                    continue
                # 如果 display entry 明显早于当前 SDK 主历史，说明它很可能来自
                # compact / clear 前的旧展示记录，不应再补回当前聊天流。
                if entry_timestamp <= latest_history_timestamp:
                    continue
            # 这条消息在 display_history 中但不在 SDK history 中，补充进去
            entry_content = entry.get("content", "")
            entry_transport = entry.get("transport_content", "")
            hydrated_history.append(
                {
                    "role": "user",
                    "content": entry_transport or entry_content,
                    "display_content": entry_content,
                    "timestamp": entry.get("timestamp"),
                }
            )

    # 有些旧 runtime 历史没有 timestamp，尽量继承上一条消息的时间，
    # 让排序至少保持轮次稳定，不要把最新一轮插到最前面。
    last_known_timestamp = ""
    for message in hydrated_history:
        timestamp = message.get("timestamp")
        if isinstance(timestamp, str) and timestamp:
            last_known_timestamp = timestamp
            continue
        if last_known_timestamp:
            message["timestamp"] = last_known_timestamp

    # 按时间戳排序（如果有的话）
    def get_timestamp(msg: Dict[str, Any]) -> str:
        ts = msg.get("timestamp")
        if isinstance(ts, str):
            return ts
        return ""

    hydrated_history.sort(key=get_timestamp)

    return hydrated_history

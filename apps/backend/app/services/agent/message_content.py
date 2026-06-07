from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, TypeAlias
from urllib.parse import unquote

from pydantic import BaseModel, Field, TypeAdapter

_WORKSPACE_ROOT = PurePosixPath("/workspace")
_SUPPORTED_IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
}
_DATA_URL_PREFIX = "data:"
MAX_INLINE_IMAGE_BYTES = 20 * 1024 * 1024


class TextContentPart(BaseModel):
    type: Literal["text"] = "text"
    text: str = Field(default="")


class ImageURLValue(BaseModel):
    url: str
    detail: str | None = None


class ImageContentPart(BaseModel):
    type: Literal["image_url"] = "image_url"
    image_url: ImageURLValue
    source_path: str | None = None


class ImageReferenceContentPart(BaseModel):
    type: Literal["image_reference"] = "image_reference"
    source_path: str | None = None


MessageContentPart: TypeAlias = TextContentPart | ImageContentPart | ImageReferenceContentPart
MessageContent: TypeAlias = str | list[MessageContentPart]

_MESSAGE_CONTENT_ADAPTER = TypeAdapter(MessageContent)


@dataclass(slots=True)
class AttachmentContentParts:
    transport_parts: list[dict[str, Any]]
    display_parts: list[dict[str, Any]]
    image_paths: list[str]


def normalize_message_content(content: Any) -> MessageContent:
    return _MESSAGE_CONTENT_ADAPTER.validate_python(content)


def dump_message_content(content: Any) -> MessageContent | list[dict[str, Any]]:
    normalized = normalize_message_content(content)
    if isinstance(normalized, str):
        return normalized
    return [part.model_dump(mode="json", exclude_none=True) for part in normalized]


def extract_message_text(content: Any) -> str:
    try:
        normalized = normalize_message_content(content)
    except Exception:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            return "".join(parts)
        return ""

    if isinstance(normalized, str):
        return normalized
    parts: list[str] = []
    for part in normalized:
        if isinstance(part, TextContentPart):
            parts.append(part.text)
            continue
        if isinstance(part, ImageReferenceContentPart):
            parts.append(render_image_reference_text(part.source_path))
    return "".join(parts)


def extract_image_paths(content: Any) -> list[str]:
    try:
        normalized = normalize_message_content(content)
    except Exception:
        return _extract_image_paths_from_untyped(content)

    if isinstance(normalized, str):
        return []

    results: list[str] = []
    seen: set[str] = set()
    for part in normalized:
        candidate = None
        if isinstance(part, ImageContentPart):
            candidate = _pick_image_path(part.source_path, part.image_url.url)
        elif isinstance(part, ImageReferenceContentPart):
            candidate = _pick_image_path(part.source_path, None)
        if candidate is None:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        results.append(candidate)
    return results


def downgrade_message_content_for_history(
    content: Any,
) -> MessageContent | list[dict[str, Any]]:
    try:
        normalized = normalize_message_content(content)
    except Exception:
        return content

    if isinstance(normalized, str):
        return normalized

    downgraded: list[MessageContentPart] = []
    changed = False
    for part in normalized:
        if isinstance(part, TextContentPart):
            downgraded.append(part)
            continue
        if isinstance(part, ImageReferenceContentPart):
            downgraded.append(part)
            continue
        if isinstance(part, ImageContentPart):
            changed = True
            downgraded.append(
                ImageReferenceContentPart(
                    source_path=_pick_image_path(part.source_path, part.image_url.url)
                )
            )

    if not changed:
        return dump_message_content(normalized)
    return dump_message_content(downgraded)


def build_content_signature(content: Any) -> str | None:
    if isinstance(content, str):
        return f"str:{content}"
    if not isinstance(content, list):
        return None

    canonical_parts: list[dict[str, Any]] = []
    for item in content:
        if isinstance(item, str):
            canonical_parts.append({"type": "text", "text": item})
            continue
        if not isinstance(item, dict):
            canonical_parts.append({"type": "unknown", "value": str(item)})
            continue

        item_type = item.get("type")
        if item_type == "text":
            canonical_parts.append({"type": "text", "text": str(item.get("text") or "")})
            continue

        if item_type in {"image_url", "image_reference"}:
            image_url = item.get("image_url")
            raw_url = None
            if isinstance(image_url, dict):
                raw_url = image_url.get("url")
            elif image_url is not None:
                raw_url = str(image_url)
            source_path = _pick_image_path(item.get("source_path"), raw_url)
            canonical_parts.append(
                {
                    "type": "image_url",
                    "source_path": source_path or "__image__",
                }
            )
            continue

        canonical_parts.append(
            {
                "type": str(item_type or "unknown"),
                "value": json.dumps(item, ensure_ascii=False, sort_keys=True),
            }
        )

    return json.dumps(canonical_parts, ensure_ascii=False, sort_keys=True)


def build_attachment_content_parts(
    *,
    attachments: list[str] | None,
    workspace_dir: Path,
    detail: str = "auto",
) -> AttachmentContentParts:
    transport_parts: list[dict[str, Any]] = []
    display_parts: list[dict[str, Any]] = []
    image_paths: list[str] = []

    for raw_attachment in attachments or []:
        normalized_workspace_path = normalize_workspace_attachment_path(raw_attachment)
        mime_type = guess_supported_image_mime_type(Path(normalized_workspace_path))
        if mime_type is None:
            continue

        host_path, workspace_path = resolve_workspace_attachment_path(
            workspace_dir=workspace_dir,
            raw_path=raw_attachment,
        )

        size_bytes = host_path.stat().st_size
        if size_bytes > MAX_INLINE_IMAGE_BYTES:
            raise ValueError(
                f"图片 `{workspace_path}` 过大（{size_bytes} bytes），当前内联上限为 {MAX_INLINE_IMAGE_BYTES} bytes。"
            )

        transport_parts.append(
            dump_message_content(
                [
                    ImageContentPart(
                        image_url=ImageURLValue(
                            url=f"file://{workspace_path}",
                            detail=detail,
                        ),
                        source_path=workspace_path,
                    )
                ]
            )[0]
        )
        display_parts.append(
            dump_message_content(
                [
                    ImageContentPart(
                        image_url=ImageURLValue(
                            url=workspace_path,
                            detail=detail,
                        ),
                        source_path=workspace_path,
                    )
                ]
            )[0]
        )
        image_paths.append(workspace_path)

    return AttachmentContentParts(
        transport_parts=transport_parts,
        display_parts=display_parts,
        image_paths=image_paths,
    )


def message_content_to_openai_input(content: Any) -> Any:
    normalized = normalize_message_content(content)
    if isinstance(normalized, str):
        return normalized

    blocks: list[dict[str, Any]] = []
    for part in normalized:
        if isinstance(part, TextContentPart):
            blocks.append({"type": "text", "text": part.text})
            continue
        if isinstance(part, ImageReferenceContentPart):
            blocks.append({"type": "text", "text": render_image_reference_text(part.source_path)})
            continue
        if isinstance(part, ImageContentPart):
            payload = part.image_url.model_dump(mode="json", exclude_none=True)
            blocks.append({"type": "image_url", "image_url": payload})
    return blocks


def message_content_to_anthropic_input(content: Any) -> Any:
    normalized = normalize_message_content(content)
    if isinstance(normalized, str):
        return normalized

    blocks: list[dict[str, Any]] = []
    for part in normalized:
        if isinstance(part, TextContentPart):
            blocks.append({"type": "text", "text": part.text})
            continue
        if isinstance(part, ImageReferenceContentPart):
            blocks.append({"type": "text", "text": render_image_reference_text(part.source_path)})
            continue
        if isinstance(part, ImageContentPart):
            mime_type, data = split_data_url(part.image_url.url)
            if mime_type is None or data is None:
                raise ValueError("Anthropic image input 仅支持 data URL。")
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": data,
                    },
                }
            )
    return blocks


def message_content_to_responses_input(content: Any) -> Any:
    normalized = normalize_message_content(content)
    if isinstance(normalized, str):
        return normalized

    blocks: list[dict[str, Any]] = []
    for part in normalized:
        if isinstance(part, TextContentPart):
            blocks.append({"type": "input_text", "text": part.text})
            continue
        if isinstance(part, ImageReferenceContentPart):
            blocks.append(
                {
                    "type": "input_text",
                    "text": render_image_reference_text(part.source_path),
                }
            )
            continue
        if isinstance(part, ImageContentPart):
            blocks.append(
                {
                    "type": "input_image",
                    "image_url": part.image_url.url,
                }
            )
    return blocks


def resolve_workspace_attachment_path(
    *,
    workspace_dir: Path,
    raw_path: str,
) -> tuple[Path, str]:
    normalized_workspace_path = normalize_workspace_attachment_path(raw_path)
    agent_path = PurePosixPath(normalized_workspace_path)
    relative = agent_path.relative_to(_WORKSPACE_ROOT)
    host_path = (workspace_dir / Path(*relative.parts)).resolve()
    workspace_root = workspace_dir.resolve()
    try:
        host_path.relative_to(workspace_root)
    except ValueError as exc:
        raise PermissionError(f"`{normalized_workspace_path}` 越出了当前任务工作区。") from exc

    if not host_path.exists() or not host_path.is_file():
        raise FileNotFoundError(f"附件 `{normalized_workspace_path}` 不存在。")
    return host_path, normalized_workspace_path


def normalize_workspace_attachment_path(raw_path: str) -> str:
    candidate = str(raw_path or "").strip().replace("\\", "/")
    if not candidate:
        raise ValueError("附件路径不能为空。")
    if candidate.startswith("workspace:/"):
        candidate = candidate[len("workspace:") :]
    if candidate.startswith("/workspace/"):
        return candidate
    return f"/workspace/{candidate.lstrip('/')}"


def guess_supported_image_mime_type(path: Path) -> str | None:
    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type in _SUPPORTED_IMAGE_MIME_TYPES:
        return mime_type
    return None


def to_data_url(mime_type: str, data: bytes) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"{_DATA_URL_PREFIX}{mime_type};base64,{encoded}"


def hydrate_message_images(
    messages: list[dict[str, Any]],
    *,
    workspace_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """把消息列表中 file:// URI 的图片临时 hydrate 成 data URL。

    返回新的消息列表，不修改原始列表。
    """
    if not messages:
        return messages

    result: list[dict[str, Any]] = []
    for msg in messages:
        new_msg = dict(msg)
        content = new_msg.get("content")

        if isinstance(content, list):
            new_parts: list[dict[str, Any]] = []
            for part in content:
                if not isinstance(part, dict):
                    new_parts.append(part)
                    continue
                if part.get("type") == "image_url":
                    image_url = part.get("image_url")
                    if isinstance(image_url, dict):
                        url = image_url.get("url", "")
                        if isinstance(url, str) and url.startswith("file://"):
                            try:
                                host_path = _resolve_hydratable_image_path(
                                    url=url,
                                    source_path=part.get("source_path"),
                                    workspace_dir=workspace_dir,
                                )
                                if host_path is None:
                                    new_parts.append(part)
                                    continue
                                mime_type = guess_supported_image_mime_type(host_path)
                                if mime_type:
                                    data = host_path.read_bytes()
                                    new_url = to_data_url(mime_type, data)
                                    new_part = dict(part)
                                    new_image_url = dict(image_url)
                                    new_image_url["url"] = new_url
                                    new_part["image_url"] = new_image_url
                                    new_parts.append(new_part)
                                    continue
                            except Exception:
                                pass  # fallback: 保留原始
                new_parts.append(part)
            new_msg["content"] = new_parts

        result.append(new_msg)

    return result


def _resolve_hydratable_image_path(
    *,
    url: str,
    source_path: Any,
    workspace_dir: Path | None,
) -> Path | None:
    candidates: list[str] = []
    if isinstance(source_path, str) and source_path.strip():
        candidates.append(source_path)
    if url.startswith("file://"):
        candidates.append(unquote(url[len("file://") :]))

    seen: set[str] = set()
    for raw_candidate in candidates:
        raw_path = raw_candidate.strip()
        if not raw_path or raw_path in seen:
            continue
        seen.add(raw_path)

        is_workspace_reference = _is_workspace_reference(raw_path)
        if workspace_dir is not None and is_workspace_reference:
            try:
                host_path, _ = resolve_workspace_attachment_path(
                    workspace_dir=workspace_dir,
                    raw_path=raw_path,
                )
                return host_path
            except (FileNotFoundError, PermissionError, ValueError):
                continue

        if is_workspace_reference:
            continue

        try:
            host_path = Path(raw_path)
        except (TypeError, ValueError):
            continue
        if host_path.is_absolute() and host_path.exists() and host_path.is_file():
            return host_path

    return None


def _is_workspace_reference(raw_path: str) -> bool:
    candidate = str(raw_path or "").strip().replace("\\", "/")
    return candidate.startswith("workspace:/") or candidate.startswith("/workspace/")


def split_data_url(value: str) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or not value.startswith(_DATA_URL_PREFIX):
        return None, None
    header, _, encoded = value.partition(",")
    if not header or not encoded:
        return None, None
    mime_section = header[len(_DATA_URL_PREFIX) :]
    mime_type, _, suffix = mime_section.partition(";")
    if suffix != "base64" or not mime_type:
        return None, None
    return mime_type, encoded


def _extract_image_paths_from_untyped(content: Any) -> list[str]:
    if not isinstance(content, list):
        return []
    results: list[str] = []
    seen: set[str] = set()
    for item in content:
        if not isinstance(item, dict) or item.get("type") not in {
            "image_url",
            "image_reference",
        }:
            continue
        image_url = item.get("image_url")
        raw_url = None
        if isinstance(image_url, dict):
            raw_url = image_url.get("url")
        elif image_url is not None:
            raw_url = str(image_url)
        candidate = _pick_image_path(item.get("source_path"), raw_url)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        results.append(candidate)
    return results


def _pick_image_path(
    source_path: Any,
    image_url: Any,
) -> str | None:
    if isinstance(source_path, str) and source_path.startswith("/workspace/"):
        return source_path
    if isinstance(image_url, str) and image_url.startswith("/workspace/"):
        return image_url
    return None


def render_image_reference_text(source_path: str | None) -> str:
    if source_path:
        return (
            f"[历史图片引用已降级，未自动继续携带图片内容：{source_path}。"
            "如果需要重新查看这张图，请让用户重新附带该图片。]"
        )
    return (
        "[历史图片引用已降级，未自动继续携带图片内容。如果需要重新查看，请让用户重新附带该图片。]"
    )

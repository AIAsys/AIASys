from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


def _extract_text_from_content(content: str | list[dict[str, Any]]) -> str:
    """从结构化 content 中提取纯文本，用于错误信息和日志展示。"""
    if isinstance(content, str):
        return content
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


class ToolResult(BaseModel):
    """AIASys-native tool 返回结构。"""

    model_config = ConfigDict(extra="allow")

    content: str | list[dict[str, Any]] = ""
    is_error: bool = False
    artifacts: list[dict[str, Any]] | None = None

    @property
    def output(self) -> Any:
        return self.content

    @property
    def message(self) -> str | None:
        if self.is_error:
            return _extract_text_from_content(self.content)
        return None

    @property
    def brief(self) -> str | None:
        if self.is_error:
            return _extract_text_from_content(self.content)
        return None

    @classmethod
    def from_value(cls, value: Any) -> "ToolResult":
        if isinstance(value, cls):
            return value

        if value is None:
            return cls()

        if isinstance(value, str):
            return cls(content=value)

        if isinstance(value, dict):
            if any(key in value for key in ("content", "is_error", "artifacts")):
                return cls.model_validate(value)

            output = value.get("output")
            message = value.get("message")
            brief = value.get("brief")
            artifacts = value.get("artifacts")
            if artifacts is not None and not isinstance(artifacts, list):
                artifacts = None
            is_error = bool(value.get("is_error"))
            if not is_error and message and not output:
                is_error = True
            return cls(
                content=(
                    output
                    if isinstance(output, list)
                    else str(output or message or brief or "")
                ),
                is_error=is_error,
                artifacts=artifacts,
            )

        if isinstance(value, BaseModel):
            return cls.from_value(value.model_dump())

        output = getattr(value, "content", None)
        if output in (None, ""):
            output = getattr(value, "output", None)
        message = getattr(value, "message", None)
        brief = getattr(value, "brief", None)
        artifacts = getattr(value, "artifacts", None)
        if artifacts is not None and not isinstance(artifacts, list):
            artifacts = None

        is_error = bool(getattr(value, "is_error", False))
        if not is_error and type(value).__name__.lower().endswith("error"):
            is_error = True

        return cls(
            content=(
                output
                if isinstance(output, list)
                else str(output or message or brief or "")
            ),
            is_error=is_error,
            artifacts=artifacts,
        )

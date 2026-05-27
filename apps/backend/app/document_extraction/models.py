"""共享文档提取模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence


class DocumentExtractionMode(str, Enum):
    """文档提取模式。"""

    BASIC = "basic"
    ENHANCED = "enhanced"
    DOCLING = "docling"

    @classmethod
    def parse(cls, value: Optional[str | "DocumentExtractionMode"]) -> "DocumentExtractionMode":
        if isinstance(value, cls):
            return value
        normalized = (value or cls.ENHANCED.value).strip().lower()
        try:
            return cls(normalized)
        except ValueError as exc:
            allowed = ", ".join(mode.value for mode in cls)
            raise ValueError(f"不支持的 extraction_mode: {value}，允许值: {allowed}") from exc

    @classmethod
    def parse_many(
        cls,
        values: Optional[Sequence[str | "DocumentExtractionMode"]],
    ) -> tuple["DocumentExtractionMode", ...]:
        if not values:
            return ()

        resolved: list[DocumentExtractionMode] = []
        for value in values:
            mode = cls.parse(value)
            if mode not in resolved:
                resolved.append(mode)
        return tuple(resolved)


@dataclass(frozen=True)
class DocumentExtractionSettings:
    """共享文档提取配置。"""

    default_mode: DocumentExtractionMode = DocumentExtractionMode.ENHANCED
    fallback_modes: tuple[DocumentExtractionMode, ...] = (DocumentExtractionMode.BASIC,)
    pdf_password: Optional[str] = None

    @classmethod
    def from_values(
        cls,
        *,
        default_mode: Optional[str | DocumentExtractionMode] = None,
        fallback_modes: Optional[Sequence[str | DocumentExtractionMode]] = None,
        pdf_password: Optional[str] = None,
    ) -> "DocumentExtractionSettings":
        return cls(
            default_mode=DocumentExtractionMode.parse(default_mode),
            fallback_modes=DocumentExtractionMode.parse_many(fallback_modes),
            pdf_password=pdf_password,
        )


@dataclass
class DocumentExtractionResult:
    """文档提取结果。"""

    text: str
    mode_used: DocumentExtractionMode
    requested_mode: DocumentExtractionMode
    file_type: str
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "mode_used": self.mode_used.value,
            "requested_mode": self.requested_mode.value,
            "file_type": self.file_type,
            "warnings": list(self.warnings),
        }

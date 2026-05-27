"""共享文档提取模块。"""

from .models import (
    DocumentExtractionMode,
    DocumentExtractionResult,
    DocumentExtractionSettings,
)
from .service import (
    DOCX_EXTENSIONS,
    PDF_EXTENSIONS,
    SPREADSHEET_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    TEXT_EXTENSIONS,
    DocumentExtractionService,
    get_document_extraction_service,
)

__all__ = [
    "DOCX_EXTENSIONS",
    "PDF_EXTENSIONS",
    "SPREADSHEET_EXTENSIONS",
    "SUPPORTED_EXTENSIONS",
    "TEXT_EXTENSIONS",
    "DocumentExtractionMode",
    "DocumentExtractionResult",
    "DocumentExtractionSettings",
    "DocumentExtractionService",
    "get_document_extraction_service",
]

"""知识库文档解析入口。"""

from pathlib import Path
from typing import List, Tuple

from app.document_extraction import (
    SUPPORTED_EXTENSIONS,
    DocumentExtractionResult,
    get_document_extraction_service,
)


class DocumentParser:
    """知识库服务使用的文档解析包装层。"""

    SUPPORTED_EXTENSIONS = SUPPORTED_EXTENSIONS

    @classmethod
    def parse(
        cls,
        file_path: Path,
        file_bytes: bytes | None = None,
        mode: str | None = None,
    ) -> str:
        return cls.parse_result(file_path, file_bytes=file_bytes, mode=mode).text

    @classmethod
    def parse_result(
        cls,
        file_path: Path,
        file_bytes: bytes | None = None,
        mode: str | None = None,
    ) -> DocumentExtractionResult:
        return get_document_extraction_service().extract(file_path, file_bytes, mode=mode)


class TextChunker:
    """
    文本分块器

    支持多种分块方式
    """

    def __init__(
        self, chunk_size: int = 512, chunk_overlap: int = 50, separators: List[str] = None
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", "。", "，", " ", ""]

    def split(self, text: str) -> List[Tuple[int, int, str]]:
        """
        分块

        Returns:
            List[Tuple[start_idx, end_idx, chunk_text]]
        """
        if not text:
            return []

        chunks = []
        current_pos = 0
        text_length = len(text)

        while current_pos < text_length:
            # 计算当前块的结束位置
            end_pos = min(current_pos + self.chunk_size, text_length)

            # 尝试在分隔符处断开
            if end_pos < text_length:
                for sep in self.separators:
                    # 从后往前找分隔符
                    sep_pos = text.rfind(sep, current_pos, end_pos)
                    if sep_pos != -1 and sep_pos > current_pos:
                        end_pos = sep_pos + len(sep)
                        break

            chunk_text = text[current_pos:end_pos].strip()
            if chunk_text:
                chunks.append((current_pos, end_pos, chunk_text))

            # 移动位置，考虑重叠
            current_pos = end_pos - self.chunk_overlap if end_pos < text_length else end_pos

            # 防止无限循环
            if current_pos <= chunks[-1][0] if chunks else False:
                current_pos = end_pos

        return chunks

    def split_with_metadata(self, text: str, doc_metadata: dict = None) -> List[dict]:
        """
        分块并返回带元数据的结果

        Returns:
            List[{
                "content": str,
                "start": int,
                "end": int,
                "index": int,
                "metadata": dict
            }]
        """
        chunks = self.split(text)
        results = []

        for idx, (start, end, content) in enumerate(chunks):
            metadata = {
                "chunk_index": idx,
                "char_start": start,
                "char_end": end,
                **(doc_metadata or {}),
            }
            results.append(
                {"content": content, "start": start, "end": end, "index": idx, "metadata": metadata}
            )

        return results


# 便捷函数


def parse_document(file_path: Path, file_bytes: bytes = None, mode: str | None = None) -> str:
    """便捷函数：解析文档"""
    return DocumentParser.parse(file_path, file_bytes, mode=mode)


def chunk_text(
    text: str, chunk_size: int = 512, chunk_overlap: int = 50, metadata: dict = None
) -> List[dict]:
    """便捷函数：分块文本"""
    chunker = TextChunker(chunk_size, chunk_overlap)
    return chunker.split_with_metadata(text, metadata)

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core.subprocess_utils import subprocess_kwargs

MARKDOWN_EXTENSIONS = {".md", ".markdown"}
PDF_ENGINE_CANDIDATES = (
    "weasyprint",
    "wkhtmltopdf",
    "tectonic",
    "xelatex",
    "lualatex",
    "pdflatex",
    "typst",
)


class MarkdownExportError(RuntimeError):
    """Raised when markdown export fails."""


class MarkdownExportDependencyError(MarkdownExportError):
    """Raised when required export dependencies are unavailable."""


@dataclass(frozen=True)
class ExportedArtifact:
    filename: str
    media_type: str
    content: bytes


def export_markdown_file_to_path(
    source_path: Path, output_format: str
) -> tuple[str, str, str]:
    """导出 Markdown 到磁盘临时文件。

    返回 (output_file_path, filename, media_type)。
    调用方负责在响应完成后删除临时文件。
    """
    if source_path.suffix.lower() not in MARKDOWN_EXTENSIONS:
        raise MarkdownExportError("仅支持导出 Markdown 文件")

    pandoc = _require_binary("pandoc", "Pandoc")
    source = source_path.resolve()
    normalized_format = output_format.lower()

    media_types = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
    }
    if normalized_format not in media_types:
        raise MarkdownExportError(f"不支持的导出格式: {output_format}")

    temp_dir = tempfile.mkdtemp(prefix="aiasys-md-export-")
    try:
        output_path = Path(temp_dir) / f"{source.stem}.{normalized_format}"
        command = [
            pandoc,
            str(source),
            "--standalone",
            "--from=markdown",
            "--resource-path",
            str(source.parent),
            "--output",
            str(output_path),
        ]
        if normalized_format == "pdf":
            command.extend(["--pdf-engine", _select_pdf_engine()])

        result = subprocess.run(
            command,
            cwd=source.parent,
            capture_output=True,
            timeout=120,
            check=False,
            **subprocess_kwargs(),
        )
        if result.returncode != 0:
            from app.core.encoding_utils import smart_decode

            stderr = smart_decode(result.stderr).strip() if result.stderr else ""
            stdout = smart_decode(result.stdout).strip() if result.stdout else ""
            detail = stderr or stdout or "Pandoc 未返回具体错误"
            raise MarkdownExportError(f"Pandoc 导出失败: {detail}")

        if not output_path.exists():
            raise MarkdownExportError("导出结果不存在")

        # 将结果移到独立的临时文件，便于调用方直接返回并清理
        fd, final_path = tempfile.mkstemp(suffix=f".{normalized_format}")
        os.close(fd)
        shutil.move(str(output_path), final_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return final_path, output_path.name, media_types[normalized_format]
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _binary_candidates(command: str) -> list[str]:
    candidates: list[str] = []
    which_result = shutil.which(command)
    if which_result:
        candidates.append(which_result)

    venv_roots = []
    if os.environ.get("VIRTUAL_ENV"):
        venv_roots.append(Path(os.environ["VIRTUAL_ENV"]))
    venv_roots.append(Path(sys.prefix))
    venv_roots.append(Path(sys.executable).resolve().parent)

    script_names = _binary_script_names(command)

    for root in venv_roots:
        script_dirs = [root / "bin", root / "Scripts"]
        for script_dir in script_dirs:
            for script_name in script_names:
                candidate = script_dir / script_name
                if candidate.exists():
                    candidates.append(str(candidate))

    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique


def _binary_script_names(command: str) -> list[str]:
    script_names = [command]
    if os.name == "nt":
        script_names.extend([f"{command}.exe", f"{command}.cmd", f"{command}.bat"])
    return script_names


def _require_binary(command: str, label: str) -> str:
    candidates = _binary_candidates(command)
    if candidates:
        return candidates[0]
    raise MarkdownExportDependencyError(f"{label} 未安装，请先安装后再重试")


def _select_pdf_engine() -> str:
    for engine in PDF_ENGINE_CANDIDATES:
        candidates = _binary_candidates(engine)
        if candidates:
            return candidates[0]
    raise MarkdownExportDependencyError(
        "未找到可用的 PDF 引擎，请安装 weasyprint、wkhtmltopdf、tectonic、xelatex、lualatex、pdflatex 或 typst"
    )


def export_markdown_file(source_path: Path, output_format: str) -> ExportedArtifact:
    """导出 Markdown 文件并返回内存中的内容（小文件场景，向后兼容）。"""
    output_path, filename, media_type = export_markdown_file_to_path(
        source_path, output_format
    )
    try:
        content = Path(output_path).read_bytes()
        return ExportedArtifact(filename=filename, media_type=media_type, content=content)
    finally:
        try:
            os.unlink(output_path)
        except OSError:
            pass

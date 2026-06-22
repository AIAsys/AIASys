"""文件管理核心端点（上传、创建、下载、删除、导出、内容读写）。"""

from __future__ import annotations

import asyncio
import io
import logging
import mimetypes
import os
import shutil
import zipfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.core.auth import require_auth, require_role
from app.models.user import UserInfo
from app.services.export import (
    MarkdownExportDependencyError,
    MarkdownExportError,
    export_markdown_file_to_path,
)
from app.utils.file_utils import sanitize_content_disposition_filename
from app.utils.path_utils import as_system_path

from .files_utils import (
    EDITABLE_EXTENSIONS,
    CsvPageUpdateRequest,
    CsvPreviewResponse,
    FileContentRequest,
    FileContentResponse,
    FileCopyRequest,
    FileCopyResponse,
    FileCreateRequest,
    FileCreateResponse,
    FileMoveRequest,
    FileMoveResponse,
    _check_user_access,
    _copyfileobj_with_limit,
    _get_logical_workspace_root,
    _get_notebook_edit_lock_reason,
    _get_session_owner_user_id,
    _get_work_dir,
    _is_editable_file,
    _is_markdown_file,
    _is_notebook_file_name,
    _is_notebook_relative_path,
    _is_workspace_memory_mirror_path,
    _iter_visible_workspace_files,
    _normalize_relative_path,
    _read_csv_preview_page,
    _resolve_workspace_path,
    _resolve_workspace_path_for_write,
    _sync_workspace_memory_from_mirror,
    _update_csv_preview_page,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _save_upload_file_sync(file: UploadFile, file_path: Path) -> int:
    """在线程池中完成上传文件的落盘与大小校验，避免阻塞事件循环。"""
    Path(as_system_path(file_path.parent)).mkdir(parents=True, exist_ok=True)
    with open(as_system_path(file_path), "wb") as f:
        size = _copyfileobj_with_limit(file.file, f)
    return size


@router.post("/upload/{user_id}/{session_id}")
async def upload_file(
    user_id: str,
    session_id: str,
    file: UploadFile = File(...),
    current_user: UserInfo = Depends(require_auth()),
):
    """
    上传文件到会话工作区

    只能上传到自己的目录，管理员可以上传到任意目录
    """
    # 检查权限
    _check_user_access(current_user, user_id)

    try:
        # 清理文件名，防止路径遍历
        safe_filename = Path(file.filename).name
        if (
            not safe_filename
            or safe_filename == "."
            or ".." in safe_filename
            or safe_filename in {"metadata.json", "history.json", "file_snapshots.json"}
        ):
            raise HTTPException(status_code=400, detail="Invalid filename")

        # notebook 默认按当前会话私有，其他文件写入工作区 uploads/ 目录，
        # 避免上传文件污染工作区根目录。
        if _is_notebook_file_name(safe_filename):
            work_dir = _get_work_dir(user_id, session_id)
            relative_dir = ""
        else:
            work_dir = _get_logical_workspace_root(user_id, session_id)
            relative_dir = "uploads"

        # 统一保存到对应目录，对应容器内 /workspace/uploads/{filename}
        if relative_dir:
            file_path = work_dir / relative_dir / safe_filename
        else:
            file_path = work_dir / safe_filename
        size = await asyncio.to_thread(_save_upload_file_sync, file, file_path)

        workspace_path = (
            f"/workspace/{relative_dir}/{safe_filename}"
            if relative_dir
            else f"/workspace/{safe_filename}"
        )
        logger.info(
            f"文件上传: {user_id}/{session_id}/{relative_dir}/{safe_filename} by {current_user.user_id}"
        )

        return {
            "success": True,
            "filename": safe_filename,
            "path": workspace_path,
            "size": size,
            "uploaded_by": current_user.user_id,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Operation failed") from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail="Operation failed") from e
    except Exception as e:
        logger.error(f"上传失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Operation failed") from e


@router.post(
    "/create/{user_id}/{session_id}",
    response_model=FileCreateResponse,
)
async def create_file(
    user_id: str,
    session_id: str,
    request: FileCreateRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """在当前会话可见的工作区中新建文本文件"""
    _check_user_access(current_user, user_id)

    try:
        normalized_path = _normalize_relative_path(request.path.strip())
        if not _is_editable_file(normalized_path.name):
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型，只允许: {', '.join(sorted(EDITABLE_EXTENSIONS))}",
            )

        if _is_notebook_file_name(normalized_path.name):
            edit_lock_reason = _get_notebook_edit_lock_reason(user_id, session_id)
            if edit_lock_reason:
                raise HTTPException(status_code=409, detail=edit_lock_reason)

        content_bytes = request.content.encode("utf-8")

        existing_path = _resolve_workspace_path(
            user_id,
            session_id,
            normalized_path.as_posix(),
        )
        visible_file_exists = existing_path.exists()
        if visible_file_exists and not request.overwrite:
            raise HTTPException(status_code=409, detail="文件已存在")

        file_path = _resolve_workspace_path_for_write(
            user_id,
            session_id,
            normalized_path,
        )
        overwritten = file_path.exists()
        Path(as_system_path(file_path.parent)).mkdir(parents=True, exist_ok=True)
        Path(as_system_path(file_path)).write_bytes(content_bytes)

        if _is_workspace_memory_mirror_path(normalized_path):
            _sync_workspace_memory_from_mirror(
                user_id=user_id,
                session_id=session_id,
                relative_path=normalized_path,
                content=request.content,
            )

        logger.info(
            "文件新建: %s/%s/%s by %s",
            user_id,
            session_id,
            normalized_path.as_posix(),
            current_user.user_id,
        )

        return FileCreateResponse(
            success=True,
            filename=normalized_path.as_posix(),
            path=f"/workspace/{normalized_path.as_posix()}",
            size=len(content_bytes),
            overwritten=overwritten,
            created_by=current_user.user_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("新建文件失败: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create file") from e


@router.get("/download/{user_id}/{session_id}/{filename:path}")
async def download_file(
    user_id: str,
    session_id: str,
    filename: str,
    disposition: str = Query(default="attachment"),
    current_user: UserInfo = Depends(require_auth()),
):
    """
    下载文件

    只能下载自己的文件，管理员可以下载任意文件
    """
    # 首先尝试从 session metadata 获取真实的 owner user_id
    # 这解决了前端 user_id 与 session 实际 owner 不一致的问题
    actual_user_id = _get_session_owner_user_id(user_id, session_id)
    if actual_user_id:
        # 使用真实的 owner user_id 进行权限检查
        target_user_id = actual_user_id
    else:
        # 如果无法读取 metadata，回退到 URL 参数
        target_user_id = user_id

    # 检查权限
    _check_user_access(current_user, target_user_id)

    try:
        file_path = _resolve_workspace_path(target_user_id, session_id, filename)

        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="文件不存在")

        logger.info(f"文件下载: {target_user_id}/{session_id}/{filename} by {current_user.user_id}")

        media_type = mimetypes.guess_type(file_path.name)[0]
        if disposition == "inline":
            return FileResponse(
                file_path,
                media_type=media_type,
                headers={
                    "Content-Disposition": f'inline; filename="{sanitize_content_disposition_filename(file_path.name)}"'
                },
            )

        return FileResponse(
            file_path,
            filename=file_path.name,
            media_type=media_type,
            content_disposition_type="attachment",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Operation failed") from e


@router.delete("/delete/{user_id}/{session_id}/{filename:path}")
async def delete_file(
    user_id: str,
    session_id: str,
    filename: str,
    recursive: bool = Query(default=False, description="递归删除目录"),
    current_user: UserInfo = Depends(require_auth()),
):
    """
    删除文件。目录删除需显式传入 recursive=true。

    只能删除自己的文件，管理员可以删除任意文件
    """
    # 检查权限
    _check_user_access(current_user, user_id)

    try:
        normalized_path = _normalize_relative_path(filename)
        file_path = _resolve_workspace_path(user_id, session_id, filename)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        if _is_notebook_file_name(file_path.name):
            edit_lock_reason = _get_notebook_edit_lock_reason(user_id, session_id)
            if edit_lock_reason:
                raise HTTPException(status_code=409, detail=edit_lock_reason)

        if _is_workspace_memory_mirror_path(normalized_path):
            from .files_utils import _clear_workspace_memory_from_mirror

            _clear_workspace_memory_from_mirror(
                user_id=user_id,
                session_id=session_id,
                relative_path=normalized_path,
            )

        if file_path.is_dir():
            if not recursive:
                raise HTTPException(
                    status_code=400,
                    detail="目标是一个目录，需要传入 recursive=true 才能删除",
                )
            shutil.rmtree(as_system_path(file_path))
        else:
            Path(as_system_path(file_path)).unlink()
        logger.info(f"文件删除: {user_id}/{session_id}/{filename} by {current_user.user_id}")

        return {"success": True, "deleted_by": current_user.user_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Operation failed") from e


def _build_workspace_zip_sync(
    user_id: str,
    session_id: str,
) -> tuple[io.BytesIO, list[tuple[str, Path]], str]:
    """同步构建工作区 ZIP（在独立线程中运行，避免阻塞事件循环）。"""
    work_dir = _get_logical_workspace_root(user_id, session_id)

    if not Path(as_system_path(work_dir)).exists():
        raise HTTPException(status_code=404, detail="工作区不存在")

    files: list[tuple[str, Path]] = []
    for relative_path, file_path in _iter_visible_workspace_files(
        user_id,
        session_id,
    ):
        files.append((relative_path, file_path))

    if not files:
        raise HTTPException(status_code=404, detail="工作区没有文件")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for relative_path, file_path in files:
            zip_file.write(as_system_path(file_path), relative_path)

    zip_buffer.seek(0)
    download_filename = f"workspace_{session_id}.zip"
    return zip_buffer, files, download_filename


@router.get("/export/{user_id}/{session_id}")
async def export_workspace(
    user_id: str,
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """
    导出会话工作区中的所有文件为 ZIP 压缩包

    只能导出自己的工作区，管理员可以导出任意工作区
    """
    # 检查权限
    _check_user_access(current_user, user_id)

    try:
        zip_buffer, files, download_filename = await asyncio.to_thread(
            _build_workspace_zip_sync, user_id, session_id
        )

        logger.info(
            f"工作区导出: {user_id}/{session_id} ({len(files)} 文件) by {current_user.user_id}"
        )

        def _zip_chunks(buffer: io.BytesIO, chunk_size: int = 64 * 1024):
            buffer.seek(0)
            while True:
                chunk = buffer.read(chunk_size)
                if not chunk:
                    break
                yield chunk

        return StreamingResponse(
            _zip_chunks(zip_buffer),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{sanitize_content_disposition_filename(download_filename)}"'
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Operation failed") from e


@router.get("/export-document/{user_id}/{session_id}/{filename:path}")
async def export_markdown_document(
    user_id: str,
    session_id: str,
    filename: str,
    format: str = "md",
    current_user: UserInfo = Depends(require_auth()),
):
    """
    导出单个 Markdown 文件。

    - format=md: 下载原始 Markdown 文件
    - format=docx|pdf: 通过 Pandoc 转换后下载
    """
    _check_user_access(current_user, user_id)

    normalized_format = format.lower()
    if normalized_format not in {"md", "docx", "pdf"}:
        raise HTTPException(status_code=400, detail="Unsupported export format")

    try:
        file_path = _resolve_workspace_path(user_id, session_id, filename)
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="文件不存在")
        if not _is_markdown_file(file_path.name):
            raise HTTPException(status_code=400, detail="仅支持导出 Markdown 文件")

        if normalized_format == "md":
            logger.info(
                "Markdown 原文导出: %s/%s/%s by %s",
                user_id,
                session_id,
                filename,
                current_user.user_id,
            )
            return FileResponse(
                file_path,
                media_type="text/markdown; charset=utf-8",
                filename=f"{file_path.stem}.md",
            )

        output_path, download_filename, media_type = await asyncio.to_thread(
            export_markdown_file_to_path, file_path, normalized_format
        )
        logger.info(
            "Markdown 转换导出: %s/%s/%s -> %s by %s",
            user_id,
            session_id,
            filename,
            normalized_format,
            current_user.user_id,
        )
        background_tasks = BackgroundTasks()
        background_tasks.add_task(os.unlink, output_path)
        return FileResponse(
            output_path,
            media_type=media_type,
            filename=sanitize_content_disposition_filename(download_filename),
            background=background_tasks,
        )

    except HTTPException:
        raise
    except MarkdownExportDependencyError as e:
        logger.warning("Markdown 导出依赖缺失: %s", e)
        raise HTTPException(status_code=503, detail="Operation failed") from e
    except MarkdownExportError as e:
        logger.error("Markdown 导出失败: %s", e)
        raise HTTPException(status_code=500, detail="Operation failed") from e
    except Exception as e:
        logger.error(f"Markdown 导出失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Operation failed") from e


def _read_text_file_sync(file_path: Path) -> tuple[str, int]:
    """在线程中同步读取文本文件内容与大小。"""
    content = Path(as_system_path(file_path)).read_text(encoding="utf-8")
    file_size = file_path.stat().st_size
    return content, file_size


def _backup_file_sync(file_path: Path, backup_path: Path) -> None:
    """在线程中同步备份文件内容。"""
    Path(as_system_path(backup_path)).write_text(
        Path(as_system_path(file_path)).read_text(encoding="utf-8"),
        encoding="utf-8",
    )


@router.get("/content/{user_id}/{session_id}/{filename:path}", response_model=FileContentResponse)
async def get_file_content(
    user_id: str,
    session_id: str,
    filename: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """
    获取工作区文本文件内容

    支持读取 .md, .txt, .json, .yaml, .ipynb 等文本文件
    """
    # 检查权限
    _check_user_access(current_user, user_id)

    try:
        file_path = _resolve_workspace_path(user_id, session_id, filename)

        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="文件不存在")

        # 检查是否可编辑
        editable = _is_editable_file(file_path.name)
        edit_lock_reason = None
        if editable and _is_notebook_file_name(file_path.name):
            edit_lock_reason = _get_notebook_edit_lock_reason(user_id, session_id)
            if edit_lock_reason:
                editable = False

        # 读取文件内容
        try:
            content, file_size = await asyncio.to_thread(_read_text_file_sync, file_path)
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="文件不是有效的文本文件")

        return FileContentResponse(
            filename=filename,
            content=content,
            size=file_size,
            editable=editable,
            edit_lock_reason=edit_lock_reason,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"读取文件内容失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to read file") from e


@router.get(
    "/csv-preview/{user_id}/{session_id}/{filename:path}",
    response_model=CsvPreviewResponse,
)
async def get_csv_preview(
    user_id: str,
    session_id: str,
    filename: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    column_offset: int = Query(default=0, ge=0),
    column_limit: int = Query(default=50, ge=1, le=200),
    current_user: UserInfo = Depends(require_auth()),
):
    """按页读取当前会话可见 CSV 文件，避免前端全量解析大文件。"""
    _check_user_access(current_user, user_id)

    try:
        file_path = _resolve_workspace_path(user_id, session_id, filename)
        return _read_csv_preview_page(
            file_path,
            filename=filename,
            page=page,
            page_size=page_size,
            column_offset=column_offset,
            column_limit=column_limit,
            editable=_is_editable_file(file_path.name),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("读取 CSV 预览失败: %s", e)
        raise HTTPException(status_code=500, detail="Failed to read CSV preview") from e


@router.put(
    "/csv-preview/{user_id}/{session_id}/{filename:path}",
)
async def update_csv_preview(
    user_id: str,
    session_id: str,
    filename: str,
    request: CsvPageUpdateRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """保存当前页 CSV 单元格修改。"""
    _check_user_access(current_user, user_id)

    try:
        normalized_path = _normalize_relative_path(filename)
        file_path = _resolve_workspace_path_for_write(
            user_id,
            session_id,
            normalized_path,
        )
        if not _is_editable_file(file_path.name):
            raise HTTPException(status_code=400, detail="当前文件不可编辑")

        updated_rows = _update_csv_preview_page(
            file_path,
            rows=request.rows,
            page=request.page,
            page_size=request.page_size,
            column_offset=request.column_offset,
            column_limit=request.column_limit,
        )
        logger.info(
            "CSV 当前页更新: %s/%s/%s by %s",
            user_id,
            session_id,
            filename,
            current_user.user_id,
        )
        return {
            "success": True,
            "filename": filename,
            "updated_rows": updated_rows,
            "size": file_path.stat().st_size,
            "updated_by": current_user.user_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("更新 CSV 当前页失败: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save CSV page") from e


@router.put("/content/{user_id}/{session_id}/{filename:path}")
async def update_file_content(
    user_id: str,
    session_id: str,
    filename: str,
    request: FileContentRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """
    更新工作区文本文件内容

    只能编辑文本文件（.md, .txt, .json, .yaml, .ipynb 等）
    """
    # 检查权限
    _check_user_access(current_user, user_id)

    try:
        normalized_path = _normalize_relative_path(filename)
        file_path = _resolve_workspace_path_for_write(
            user_id,
            session_id,
            normalized_path,
        )

        if not _is_editable_file(file_path.name):
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型，只允许: {', '.join(sorted(EDITABLE_EXTENSIONS))}",
            )

        if _is_notebook_file_name(file_path.name):
            edit_lock_reason = _get_notebook_edit_lock_reason(user_id, session_id)
            if edit_lock_reason:
                raise HTTPException(status_code=409, detail=edit_lock_reason)

        content_bytes = request.content.encode("utf-8")

        # 确保目录存在
        Path(as_system_path(file_path.parent)).mkdir(parents=True, exist_ok=True)

        # 备份原文件（如果存在）
        if file_path.exists():
            backup_path = file_path.with_suffix(f"{file_path.suffix}.backup")
            try:
                await asyncio.to_thread(_backup_file_sync, file_path, backup_path)
            except Exception:
                pass  # 备份失败不影响主流程

        # 写入新内容
        await asyncio.to_thread(Path(as_system_path(file_path)).write_bytes, content_bytes)

        if _is_workspace_memory_mirror_path(normalized_path):
            _sync_workspace_memory_from_mirror(
                user_id=user_id,
                session_id=session_id,
                relative_path=normalized_path,
                content=request.content,
            )

        logger.info(f"文件更新: {user_id}/{session_id}/{filename} by {current_user.user_id}")

        return {
            "success": True,
            "filename": filename,
            "size": len(content_bytes),
            "updated_by": current_user.user_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新文件内容失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save file") from e


# 管理员端点
@router.put("/move/{user_id}/{session_id}", response_model=FileMoveResponse)
async def move_file(
    user_id: str,
    session_id: str,
    request: FileMoveRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """
    移动/重命名工作区中的文件或文件夹

    将 source 路径的文件/文件夹移动到 target 路径。
    若 target 父目录不存在会自动创建。
    """
    _check_user_access(current_user, user_id)

    try:
        source_path = _resolve_workspace_path(user_id, session_id, request.source)
        if not source_path.exists():
            raise HTTPException(status_code=404, detail="源文件不存在")

        # notebook 禁止移动
        if _is_notebook_file_name(source_path.name):
            edit_lock_reason = _get_notebook_edit_lock_reason(user_id, session_id)
            if edit_lock_reason:
                raise HTTPException(status_code=409, detail=edit_lock_reason)

        normalized_target = _normalize_relative_path(request.target)
        target_path = _resolve_workspace_path_for_write(user_id, session_id, normalized_target)

        # 禁止移动到自身子目录下
        try:
            target_path.relative_to(source_path.resolve())
            raise HTTPException(status_code=400, detail="不能将文件夹移动到自身内部")
        except ValueError:
            pass

        # 确保目标父目录存在
        Path(as_system_path(target_path.parent)).mkdir(parents=True, exist_ok=True)

        shutil.move(str(as_system_path(source_path)), str(as_system_path(target_path)))

        logger.info(
            "文件移动: %s/%s %s -> %s by %s",
            user_id,
            session_id,
            request.source,
            request.target,
            current_user.user_id,
        )

        return FileMoveResponse(
            success=True,
            source=request.source,
            target=request.target,
            moved_by=current_user.user_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("移动文件失败: %s", e)
        raise HTTPException(status_code=500, detail="Failed to move file") from e


@router.post("/copy/{user_id}/{session_id}", response_model=FileCopyResponse)
async def copy_file(
    user_id: str,
    session_id: str,
    request: FileCopyRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """复制工作区中的文件或文件夹。"""
    _check_user_access(current_user, user_id)

    try:
        normalized_source = _normalize_relative_path(request.source)
        normalized_target = _normalize_relative_path(request.target)
        source_path = _resolve_workspace_path(
            user_id,
            session_id,
            normalized_source.as_posix(),
        )
        if not source_path.exists():
            raise HTTPException(status_code=404, detail="源文件不存在")

        if _is_notebook_relative_path(normalized_source) or _is_notebook_relative_path(
            normalized_target
        ):
            edit_lock_reason = _get_notebook_edit_lock_reason(user_id, session_id)
            if edit_lock_reason:
                raise HTTPException(status_code=409, detail=edit_lock_reason)

        target_path = _resolve_workspace_path_for_write(
            user_id,
            session_id,
            normalized_target,
        )
        if target_path.exists():
            raise HTTPException(status_code=409, detail="目标已存在")

        if source_path.is_dir():
            try:
                target_path.resolve().relative_to(source_path.resolve())
                raise HTTPException(status_code=400, detail="不能将文件夹复制到自身内部")
            except ValueError:
                pass

        Path(as_system_path(target_path.parent)).mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            shutil.copytree(
                str(as_system_path(source_path)), str(as_system_path(target_path)), symlinks=True
            )
        else:
            shutil.copy2(str(as_system_path(source_path)), str(as_system_path(target_path)))

        logger.info(
            "文件复制: %s/%s %s -> %s by %s",
            user_id,
            session_id,
            request.source,
            request.target,
            current_user.user_id,
        )

        return FileCopyResponse(
            success=True,
            source=request.source,
            target=request.target,
            copied_by=current_user.user_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("复制文件失败: %s", e)
        raise HTTPException(status_code=500, detail="Failed to copy file") from e


def _list_all_files_sync(admin_user_id: str) -> dict[str, object]:
    """同步遍历所有用户文件（在独立线程中运行，避免阻塞事件循环）。"""
    all_files: list[dict[str, object]] = []

    from app.core.config import WORKSPACE_DIR

    from .files_utils import _iter_session_files

    workspace_dir = Path(as_system_path(WORKSPACE_DIR))
    if workspace_dir.exists():
        for user_dir in workspace_dir.iterdir():
            if user_dir.name.startswith(".") or not user_dir.is_dir():
                continue
            for session_dir in user_dir.iterdir():
                if session_dir.name.startswith(".") or not session_dir.is_dir():
                    continue
                for relative_path, file_path in _iter_session_files(session_dir):
                    stat = Path(as_system_path(file_path)).stat()
                    all_files.append(
                        {
                            "user_id": user_dir.name,
                            "session_id": session_dir.name,
                            "name": relative_path,
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                            "absolute_path": str(Path(as_system_path(file_path)).absolute()),
                        }
                    )

    return {
        "files": all_files,
        "total": len(all_files),
        "admin": admin_user_id,
    }


@router.get("/admin/list-all", tags=["admin"])
async def list_all_files(
    current_user: UserInfo = Depends(require_role("admin")),
):
    """
    列出所有用户的所有文件（仅管理员）
    """
    try:
        return await asyncio.to_thread(_list_all_files_sync, current_user.user_id)
    except Exception as e:
        logger.error(f"列所有文件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Operation failed") from e

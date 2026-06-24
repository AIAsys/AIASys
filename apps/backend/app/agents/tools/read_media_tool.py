"""Docker-safe ReadMediaFile implementation for session-scoped workspaces."""

import base64
import mimetypes
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any, Final, override

from pydantic import BaseModel, Field

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.history import current_workspace
from app.utils.path_utils import as_system_path

MAX_MEDIA_MEGABYTES = 100
_CONTAINER_WORKSPACE_ROOT: Final = PurePosixPath("/workspace")
_FALLBACK_MEDIA_SNIFF_BYTES: Final = 8192


def _load_skip_this_tool() -> type[Exception]:
    return type("SkipThisTool", (Exception,), {})


def _render_capability_section(capabilities: set[str]) -> str:
    if "image_in" in capabilities and "video_in" in capabilities:
        return "**Capabilities**\n- This tool supports image and video files for the current model."
    if "image_in" in capabilities:
        return (
            "**Capabilities**\n"
            "- This tool supports image files for the current model.\n"
            "- Video files are not supported by the current model."
        )
    if "video_in" in capabilities:
        return (
            "**Capabilities**\n"
            "- This tool supports video files for the current model.\n"
            "- Image files are not supported by the current model."
        )
    return "**Capabilities**\n- The current model does not support image or video input."


def _load_desc_text(capabilities: set[str]) -> str:
    description_path = Path(__file__).with_name("read_media_tool.md")
    raw_description = description_path.read_text(encoding="utf-8")
    static_prefix = raw_description.split("**Capabilities**", 1)[0].strip()
    return (
        static_prefix.replace("${MAX_MEDIA_MEGABYTES}", str(MAX_MEDIA_MEGABYTES))
        + "\n\n"
        + _render_capability_section(capabilities)
    )


def _looks_like_text(header: bytes) -> bool:
    if not header:
        return False
    if b"\x00" in header:
        return False
    try:
        header.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _detect_file_type(path: str, *, header: bytes) -> "_DetectedFileType":
    suffix = Path(path).suffix.lower()

    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return _DetectedFileType(kind="image", mime_type="image/png")
    if header.startswith(b"\xff\xd8\xff"):
        return _DetectedFileType(kind="image", mime_type="image/jpeg")
    if header.startswith((b"GIF87a", b"GIF89a")):
        return _DetectedFileType(kind="image", mime_type="image/gif")
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return _DetectedFileType(kind="image", mime_type="image/webp")

    mime_type = mimetypes.guess_type(path)[0]
    if not mime_type and suffix == ".webm":
        mime_type = "video/webm"

    if isinstance(mime_type, str):
        if mime_type.startswith("image/"):
            return _DetectedFileType(kind="image", mime_type=mime_type)
        if mime_type.startswith("video/"):
            return _DetectedFileType(kind="video", mime_type=mime_type)
        if mime_type.startswith("text/"):
            return _DetectedFileType(kind="text", mime_type=mime_type)

    if _looks_like_text(header):
        return _DetectedFileType(kind="text", mime_type="text/plain")

    return _DetectedFileType(kind="unknown", mime_type=mime_type or "application/octet-stream")


class _DetectedFileType:
    kind: str
    mime_type: str

    def __init__(self, *, kind: str, mime_type: str) -> None:
        self.kind = kind
        self.mime_type = mime_type


def _wrap_media_payload(kind: str, data_url: str, visible_path: str) -> str:
    return f"[{kind}:{visible_path}]\n![]({data_url})"


def _to_data_url(mime_type: str, data: bytes) -> str:
    """Encode raw bytes as a data URL."""
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_image_size(data: bytes) -> tuple[int, int] | None:
    """Best-effort image dimension detection."""
    try:
        from PIL import Image
    except Exception:
        return None

    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            return image.size
    except Exception:
        return None


class Params(BaseModel):
    path: str = Field(
        description=(
            "The container-visible path to the image or video file. "
            "Docker mode only accepts relative paths or paths under `/workspace`."
        )
    )


class ReadMediaFile(AiasysTool):
    """Load image or video files from the current Docker workspace."""

    name: str = "ReadMediaFile"
    params: type[Params] = Params

    def __init__(self, model_capabilities: set[str] | None = None) -> None:
        SkipThisTool = _load_skip_this_tool()
        capabilities = set(model_capabilities or [])
        if "image_in" not in capabilities and "video_in" not in capabilities:
            raise SkipThisTool()

        self.description = _load_desc_text(capabilities)
        self._capabilities = capabilities

    @staticmethod
    def _get_workspace_root() -> Path:
        workspace = current_workspace.get()
        if workspace is None:
            raise RuntimeError("Current workspace is not set for this session.")

        workspace_root = workspace.resolve()
        if not workspace_root.exists() or not workspace_root.is_dir():
            raise RuntimeError(f"Current workspace is unavailable: {workspace_root}")
        return workspace_root

    def _translate_workspace_path(self, raw_path: str) -> tuple[Path, str]:
        """Translate a container-visible path into the host workspace path."""
        if not raw_path:
            raise ValueError("File path cannot be empty.")

        workspace_root = self._get_workspace_root()
        agent_path = PurePosixPath(raw_path)

        if agent_path.is_absolute():
            if agent_path == _CONTAINER_WORKSPACE_ROOT:
                relative_path = PurePosixPath(".")
            else:
                try:
                    relative_path = agent_path.relative_to(_CONTAINER_WORKSPACE_ROOT)
                except ValueError as exc:
                    raise ValueError(
                        "Docker mode only allows relative paths or paths under `/workspace`."
                    ) from exc
        else:
            relative_path = agent_path

        host_path = (workspace_root / Path(*relative_path.parts)).resolve()
        try:
            workspace_relative = host_path.relative_to(workspace_root)
        except ValueError as exc:
            raise PermissionError(
                f"`{raw_path}` escapes the current workspace and cannot be read."
            ) from exc

        visible_path = "/workspace"
        if workspace_relative != Path("."):
            visible_path = f"/workspace/{workspace_relative.as_posix()}"
        return host_path, visible_path

    @staticmethod
    def _ensure_readable_file(host_path: Path, visible_path: str) -> None:
        if not host_path.exists():
            raise FileNotFoundError(f"`{visible_path}` does not exist.")
        if not host_path.is_file():
            raise IsADirectoryError(f"`{visible_path}` is not a file.")

    @staticmethod
    def _read_header(path: Path) -> bytes:
        with Path(as_system_path(path)).open("rb") as file:
            return file.read(_FALLBACK_MEDIA_SNIFF_BYTES)

    def _validate_file_type(
        self,
        file_type: Any,
        visible_path: str,
    ) -> ToolResult | None:
        if file_type.kind == "text":
            return ToolResult(
                content=(
                    f"`{visible_path}` is a text file. "
                    "Use the current runtime's text / notebook / workspace tool instead."
                ),
                is_error=True,
            )
        if file_type.kind == "unknown":
            return ToolResult(
                content=(
                    f"`{visible_path}` seems not readable as an image or video file. "
                    "Use Python or another file-aware tool if you need custom decoding."
                ),
                is_error=True,
            )
        if file_type.kind == "image" and "image_in" not in self._capabilities:
            return ToolResult(
                content=(
                    "The current model does not support image input. "
                    "Tell the user to use a model with image input capability."
                ),
                is_error=True,
            )
        if file_type.kind == "video" and "video_in" not in self._capabilities:
            return ToolResult(
                content=(
                    "The current model does not support video input. "
                    "Tell the user to use a model with video input capability."
                ),
                is_error=True,
            )
        return None

    async def _read_media(
        self,
        host_path: Path,
        visible_path: str,
        file_type: Any,
    ) -> ToolResult:
        assert file_type.kind in {"image", "video"}

        size = host_path.stat().st_size
        if size == 0:
            return ToolResult(
                content=f"`{visible_path}` is empty.",
                is_error=True,
            )
        if size > (MAX_MEDIA_MEGABYTES << 20):
            return ToolResult(
                content=(
                    f"`{visible_path}` is {size} bytes, which exceeds the max "
                    f"{MAX_MEDIA_MEGABYTES}MB for media files."
                ),
                is_error=True,
            )

        if file_type.kind == "image":
            data = Path(as_system_path(host_path)).read_bytes()
            data_url = _to_data_url(file_type.mime_type, data)
            content_parts: list[dict[str, Any]] = [
                {"type": "text", "text": f"[image:{visible_path}]"},
                {
                    "type": "image_url",
                    "image_url": {"url": data_url},
                    "source_path": visible_path,
                },
            ]
            return ToolResult(content=content_parts)

        data = Path(as_system_path(host_path)).read_bytes()
        data_url = _to_data_url(file_type.mime_type, data)
        wrapped = _wrap_media_payload("video", data_url, visible_path)
        return ToolResult(content=wrapped)

    @staticmethod
    def _build_expected_error(exc: Exception) -> ToolResult:
        if isinstance(exc, ValueError):
            _brief = "Invalid path"
        elif isinstance(exc, PermissionError):
            _brief = "Permission denied"
        elif isinstance(exc, FileNotFoundError):
            _brief = "File not found"
        elif isinstance(exc, IsADirectoryError):
            _brief = "Invalid path"
        elif isinstance(exc, RuntimeError):
            _brief = "Workspace unavailable"
        else:
            _brief = "Failed to read file"
        return ToolResult(content=str(exc), is_error=True)

    @override
    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = Params.model_validate(kwargs)
        if not params.path:
            return ToolResult(
                content="File path cannot be empty.",
                is_error=True,
            )

        try:
            host_path, visible_path = self._translate_workspace_path(params.path)
            self._ensure_readable_file(host_path, visible_path)
            file_type = _detect_file_type(
                visible_path,
                header=self._read_header(host_path),
            )
            if err := self._validate_file_type(file_type, visible_path):
                return err
            return await self._read_media(host_path, visible_path, file_type)
        except (
            FileNotFoundError,
            IsADirectoryError,
            PermissionError,
            RuntimeError,
            ValueError,
        ) as exc:
            return self._build_expected_error(exc)
        except Exception as exc:
            return ToolResult(
                content=f"Failed to read {params.path}. Error: {exc}",
                is_error=True,
            )

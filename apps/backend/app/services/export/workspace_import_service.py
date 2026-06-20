"""工作区导入服务。

从 ZIP 包解析并重建工作区，生成新 ID，隔离原环境。
"""

from __future__ import annotations

import io
import json
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

from app.core.config import WORKSPACE_DIR
from app.services.workspace_registry import WorkspaceRegistryService
from app.utils.ids import generate_workspace_id
from app.utils.path_utils import as_system_path


class WorkspaceImportError(ValueError):
    """导入格式或内容错误。"""


class WorkspaceImportService:
    """从 ZIP 包导入工作区。"""

    def __init__(
        self,
        workspace_root: Path | None = None,
        registry: WorkspaceRegistryService | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root or WORKSPACE_DIR)
        self.registry = registry

    def _get_user_dir(self, user_id: str) -> Path:
        return self.workspace_root / user_id

    def _generate_workspace_id(self, user_id: str) -> str:
        try:
            return generate_workspace_id(self._get_user_dir(user_id))
        except RuntimeError as exc:
            raise WorkspaceImportError("无法生成可用的工作区 ID") from exc

    def _ensure_unique_title(
        self,
        user_id: str,
        title: str,
    ) -> str:
        """确保标题不重复，必要时追加"（导入）"。"""
        # 收集现有工作区标题
        existing_titles: set[str] = set()
        user_dir = self._get_user_dir(user_id)
        if os.path.exists(as_system_path(user_dir)):
            for candidate in user_dir.iterdir():
                if not os.path.isdir(as_system_path(candidate)):
                    continue
                meta_path = candidate / ".aiasys" / "workspace" / "workspace.json"
                if os.path.exists(as_system_path(meta_path)):
                    try:
                        data = json.loads(Path(as_system_path(meta_path)).read_text(encoding="utf-8"))
                        existing_titles.add(str(data.get("title") or ""))
                    except Exception:
                        pass

        base_title = title
        suffix = "（导入）"
        result = base_title
        if result in existing_titles:
            result = base_title + suffix
            counter = 1
            while result in existing_titles:
                result = f"{base_title}{suffix} ({counter})"
                counter += 1
        return result

    def _validate_manifest(self, manifest: dict[str, Any]) -> None:
        feature = manifest.get("feature")
        version = manifest.get("version")
        if feature != "workspace_export":
            raise WorkspaceImportError(f"不支持的导出格式: {feature}")
        if version != 1:
            raise WorkspaceImportError(f"不支持的版本: {version}")

    def import_from_zip(
        self,
        *,
        user_id: str,
        zip_bytes: bytes,
    ) -> Tuple[str, Dict[str, Any]]:
        """从 ZIP 字节导入工作区。

        返回 (新 workspace_id, workspace_meta)。
        """
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
                return self._import_from_zipfile(user_id, zf)
        except zipfile.BadZipFile as exc:
            raise WorkspaceImportError("无效的 ZIP 文件") from exc

    def _import_from_zipfile(
        self,
        user_id: str,
        zf: zipfile.ZipFile,
    ) -> Tuple[str, Dict[str, Any]]:
        # 读取并验证 manifest
        try:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        except KeyError:
            raise WorkspaceImportError("ZIP 中缺少 manifest.json")
        except json.JSONDecodeError as exc:
            raise WorkspaceImportError("manifest.json 格式错误") from exc

        self._validate_manifest(manifest)

        # 读取 workspace.json
        try:
            workspace_meta = json.loads(zf.read("workspace.json").decode("utf-8"))
        except KeyError:
            raise WorkspaceImportError("ZIP 中缺少 workspace.json")
        except json.JSONDecodeError as exc:
            raise WorkspaceImportError("workspace.json 格式错误") from exc

        # 读取 conversations.json（可选，兼容早期导出）
        conversations_payload: dict[str, Any] = {"_schema_version": 1, "conversations": []}
        try:
            conversations_payload = json.loads(zf.read("conversations.json").decode("utf-8"))
        except KeyError:
            pass
        except json.JSONDecodeError as exc:
            raise WorkspaceImportError("conversations.json 格式错误") from exc

        # 生成新 ID 和标题
        new_workspace_id = self._generate_workspace_id(user_id)
        original_title = str(workspace_meta.get("title") or "导入的工作区")
        new_title = self._ensure_unique_title(user_id, original_title)

        now = datetime.now().isoformat()
        workspace_meta["workspace_id"] = new_workspace_id
        workspace_meta["title"] = new_title
        workspace_meta["created_at"] = now
        workspace_meta["updated_at"] = now
        workspace_meta["current_conversation_id"] = None
        workspace_meta["status"] = "active"
        workspace_meta["_schema_version"] = workspace_meta.get("_schema_version", 1)

        # 清空 conversations 中的 session 绑定（第一阶段不恢复历史）
        conversations = conversations_payload.get("conversations") or []
        if isinstance(conversations, list):
            for conv in conversations:
                if isinstance(conv, dict):
                    conv["session_id"] = None
                    conv["conversation_id"] = None

        # 创建工作区目录并恢复文件
        workspace_dir = self._get_user_dir(user_id) / new_workspace_id
        os.makedirs(as_system_path(workspace_dir), exist_ok=True)

        try:
            # 恢复 workspace_files/
            prefix = "workspace_files/"
            for name in zf.namelist():
                if name.startswith(prefix) and not name.endswith("/"):
                    relative = name[len(prefix) :]
                    target = workspace_dir / relative
                    os.makedirs(as_system_path(target.parent), exist_ok=True)
                    with zf.open(name) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(as_system_path(str(src)), as_system_path(str(dst)))

            # 写 workspace.json
            meta_dir = workspace_dir / ".aiasys" / "workspace"
            os.makedirs(as_system_path(meta_dir), exist_ok=True)
            meta_path = meta_dir / "workspace.json"
            Path(as_system_path(meta_path)).write_text(
                json.dumps(workspace_meta, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            # 写 conversations.json
            conv_path = meta_dir / "conversations.json"
            Path(as_system_path(conv_path)).write_text(
                json.dumps(
                    {"_schema_version": 1, "conversations": conversations},
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            # 确保基本上下文文件存在
            if self.registry:
                self.registry._ensure_workspace_context_files(
                    workspace_dir,
                    title=new_title,
                    description=workspace_meta.get("description"),
                )

        except Exception as exc:
            # 清理失败的半成品
            if os.path.exists(as_system_path(workspace_dir)):
                shutil.rmtree(as_system_path(str(workspace_dir)), ignore_errors=True)
            raise WorkspaceImportError(f"恢复工作区文件失败: {exc}") from exc

        return new_workspace_id, workspace_meta

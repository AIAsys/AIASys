"""工作区导出服务。

支持 .exportignore 排除配置，敏感信息自动脱敏。
支持选项覆盖：排除规则、文件选择、对话记录包含。
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Optional

from app.core.config import WORKSPACE_DIR

DEFAULT_EXPORT_EXCLUDE_PATTERNS: list[str] = [
    # 运行时状态
    ".aiasys/session",
    ".aiasys/session/**",
    ".aiasys/file-history",
    ".aiasys/file-history/**",
    # 敏感配置文件
    ".env",
    ".env.*",
    "llm_config.json",
    "mcp_config.json",
    "mcp.json",
    "mcp.yaml",
    "mcp.yml",
    "channels.toml",
    # 密钥文件
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
    "*.crt",
    "*.cer",
    # SQLite 临时文件
    "*-shm",
    "**/*-shm",
    "*-wal",
    "**/*-wal",
    "*-journal",
    "**/*-journal",
    # 其他
    ".exportignore",
]

SENSITIVE_NAME_TOKENS = {
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "credential",
    "private_key",
    "id_rsa",
}

_EXPORTIGNORE_FILENAME = ".exportignore"


def _load_exportignore(workspace_dir: Path) -> list[str]:
    """读取 .aiasys/.exportignore 中的用户自定义排除规则。"""
    path = workspace_dir / ".aiasys" / _EXPORTIGNORE_FILENAME
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    except Exception:
        return []


def _is_excluded(relative_path: str, patterns: list[str]) -> bool:
    """检查 relative_path 是否匹配任一排除模式。"""
    posix_path = relative_path
    for pattern in patterns:
        # 支持 **/ 前缀的递归匹配
        if pattern.startswith("**/"):
            suffix = pattern[3:]
            if fnmatch(posix_path, suffix) or any(
                fnmatch(part, suffix) for part in posix_path.split("/")
            ):
                return True
        # 目录匹配：模式无后缀且路径以此开头
        if not pattern.endswith("*") and not pattern.endswith("/"):
            if posix_path == pattern or posix_path.startswith(pattern + "/"):
                return True
        if fnmatch(posix_path, pattern):
            return True
        # 匹配路径中的任一目录层级
        parts = posix_path.split("/")
        for i in range(len(parts)):
            subpath = "/".join(parts[: i + 1])
            if fnmatch(subpath, pattern):
                return True
    return False


def _is_sensitive_file(relative_path: str) -> bool:
    """检查文件名是否含敏感关键词。"""
    file_name = Path(relative_path).name.lower()
    return any(token in file_name for token in SENSITIVE_NAME_TOKENS)


def _sanitize_workspace_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """脱敏工作区元数据：清空 env_vars。"""
    sanitized = dict(meta)
    runtime_binding = sanitized.get("runtime_binding")
    if isinstance(runtime_binding, dict):
        runtime_binding = dict(runtime_binding)
        if runtime_binding.get("env_vars"):
            runtime_binding["env_vars"] = {}
        sanitized["runtime_binding"] = runtime_binding
    return sanitized


class WorkspaceExportService:
    """构建工作区导出 ZIP 包。"""

    def __init__(self, workspace_root: Path | None = None) -> None:
        self.workspace_root = Path(workspace_root or WORKSPACE_DIR)

    def _get_workspace_dir(self, user_id: str, workspace_id: str) -> Path:
        return self.workspace_root / user_id / workspace_id

    def _collect_conversation_histories(
        self,
        user_id: str,
        conversation_payloads: list[dict[str, Any]],
    ) -> list[tuple[str, list[dict[str, Any]]]]:
        """按 conversation_payloads 中的 session_id 读取完整对话历史。

        返回 [(conversation_id, messages), ...]。
        """
        results: list[tuple[str, list[dict[str, Any]]]] = []
        for payload in conversation_payloads:
            session_id = payload.get("session_id")
            conversation_id = payload.get("conversation_id")
            if not session_id or not conversation_id:
                continue

            messages = self._read_conversation_history(user_id, session_id)
            if messages:
                results.append((conversation_id, messages))
        return results

    def _read_conversation_history(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        """读取单个 session 的完整对话历史（context.jsonl）。

        过滤内部 SDK 消息和 system-reminder。
        """
        session_dir = self.workspace_root / user_id / session_id
        context_file = session_dir / ".aiasys" / "session" / session_id / "context.jsonl"
        if not context_file.exists():
            return []

        messages: list[dict[str, Any]] = []
        try:
            with open(context_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    role = msg.get("role")
                    if role in ("_checkpoint", "_usage", "_system_prompt"):
                        continue

                    # 过滤 system-reminder（user 消息中以 <system-reminder> 开头）
                    if role == "user":
                        content = msg.get("content")
                        if isinstance(content, str) and content.strip().startswith(
                            "<system-reminder>"
                        ):
                            continue

                    messages.append(msg)
        except Exception:
            pass

        return messages

    def _collect_files(
        self,
        workspace_dir: Path,
        *,
        exclude_rules: list[str] | None = None,
        selected_files: list[str] | None = None,
    ) -> tuple[list[tuple[str, Path]], list[str]]:
        """收集工作区文件，返回 (文件列表, 跳过的敏感文件列表)。

        文件列表每项为 (相对路径, 绝对路径)。

        Args:
            exclude_rules: 覆盖默认和 .exportignore 的排除规则。
            selected_files: 如果提供，只导出这些相对路径的文件。
        """
        if exclude_rules is not None:
            patterns = list(exclude_rules)
        else:
            user_patterns = _load_exportignore(workspace_dir)
            patterns = list(DEFAULT_EXPORT_EXCLUDE_PATTERNS) + user_patterns

        files: list[tuple[str, Path]] = []
        skipped_sensitive: list[str] = []
        seen: set[str] = set()

        for file_path in workspace_dir.rglob("*"):
            if not file_path.is_file():
                continue

            relative = file_path.relative_to(workspace_dir).as_posix()
            if relative in seen:
                continue

            # selected_files 优先级最高：如果提供，只保留列表中的文件
            if selected_files is not None and relative not in selected_files:
                continue

            if _is_excluded(relative, patterns):
                continue

            if _is_sensitive_file(relative):
                skipped_sensitive.append(relative)
                continue

            seen.add(relative)
            files.append((relative, file_path))

        return files, skipped_sensitive

    def build_archive(
        self,
        *,
        user_id: str,
        workspace_id: str,
        workspace_meta: dict[str, Any],
        conversation_payloads: list[dict[str, Any]],
        exported_by: Optional[str] = None,
        include_conversations: bool = False,
        selected_files: list[str] | None = None,
        exclude_rules: list[str] | None = None,
    ) -> tuple[io.BytesIO, str]:
        """构建工作区导出 ZIP 包。

        返回 (zip_buffer, download_filename)。
        """
        workspace_dir = self._get_workspace_dir(user_id, workspace_id)
        if not workspace_dir.exists():
            raise FileNotFoundError(f"工作区不存在: {user_id}/{workspace_id}")

        files, skipped_sensitive = self._collect_files(
            workspace_dir,
            exclude_rules=exclude_rules,
            selected_files=selected_files,
        )

        # 脱敏元数据
        sanitized_meta = _sanitize_workspace_meta(workspace_meta)

        entries = ["manifest.json", "workspace.json", "conversations.json"]
        entries.extend(f"workspace_files/{r}" for r, _ in files)

        conversation_exports: list[tuple[str, list[dict[str, Any]]]] = []
        if include_conversations:
            conversation_exports = self._collect_conversation_histories(
                user_id, conversation_payloads
            )
            for conv_id, _ in conversation_exports:
                entries.append(f"conversations/{conv_id}.json")

        manifest: dict[str, Any] = {
            "feature": "workspace_export",
            "version": 1,
            "exported_at": datetime.now().isoformat(),
            "exported_by": exported_by,
            "workspace": {
                "workspace_id": workspace_id,
                "title": str(sanitized_meta.get("title") or ""),
                "workspace_kind": str(sanitized_meta.get("workspace_kind") or "task"),
            },
            "options": {
                "include_conversations": include_conversations,
                "selected_files_count": len(selected_files) if selected_files else None,
                "exclude_rules_count": len(exclude_rules) if exclude_rules else None,
            },
            "counts": {
                "files": len(files),
                "skipped_sensitive_files": len(skipped_sensitive),
            },
            "guards": {
                "excluded_sensitive_files": skipped_sensitive,
                "env_vars_cleared": True,
            },
            "entries": entries,
        }

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            zf.writestr("workspace.json", json.dumps(sanitized_meta, indent=2, ensure_ascii=False))
            zf.writestr(
                "conversations.json",
                json.dumps(
                    {"_schema_version": 1, "conversations": conversation_payloads},
                    indent=2,
                    ensure_ascii=False,
                ),
            )

            for relative_path, abs_path in files:
                zf.write(abs_path, f"workspace_files/{relative_path}")

            if conversation_exports:
                for conv_id, messages in conversation_exports:
                    zf.writestr(
                        f"conversations/{conv_id}.json",
                        json.dumps(
                            {
                                "_schema_version": 1,
                                "conversation_id": conv_id,
                                "message_count": len(messages),
                                "messages": messages,
                            },
                            indent=2,
                            ensure_ascii=False,
                        ),
                    )

        zip_buffer.seek(0)
        safe_title = "".join(
            c if c.isascii() and (c.isalnum() or c in "_-") else "_"
            for c in str(sanitized_meta.get("title") or workspace_id)
        )
        filename = f"workspace_{safe_title}_{workspace_id}.zip"
        return zip_buffer, filename

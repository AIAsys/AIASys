"""工作区 Node.js 运行环境管理服务（基于 fnm）。"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.subprocess_utils import subprocess_kwargs
from app.utils.path_utils import as_system_path

if TYPE_CHECKING:
    from app.services.workspace_registry import WorkspaceRegistryService

from app.core.config import WORKSPACE_DIR
from app.core.encoding_utils import smart_decode
from app.models.runtime_environment import (
    NodeRuntimeEnv,
    NodeRuntimeEnvRegistryResponse,
    RuntimeEnvCommandResult,
    RuntimeEnvPackage,
)
from app.models.workspace import ExecutionResourceGroup, WorkspaceRuntimeBinding

logger = logging.getLogger(__name__)

DEFAULT_NODE_ENV_ID = "node-default"
WORKSPACE_RUNTIME_DIR_NAME = ".env"
_REGISTRY_FILE = "node-environments.json"
_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_VERSION_PATTERN = re.compile(r"^v?\d+(\.\d+)*(\.\d+)?$")


def _now_iso() -> str:
    return datetime.now().isoformat()


def _ensure_valid_id(value: str, field_name: str) -> None:
    if not value or not _ID_PATTERN.match(value):
        raise ValueError(f"无效的 {field_name}")


def _normalize_env_id(value: str | None, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    _ensure_valid_id(text, "env_id")
    return text


def _safe_tail(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _parse_fnm_list_versions(stdout: str) -> list[str]:
    """从 fnm list 输出中提取已安装的版本号。

    支持输出格式如：
      * v22.15.0 default
      * v20.15.1
      v18.20.4
    返回的版本号不带前导 'v'，与 _normalize_node_version 保持一致。
    """
    versions = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.search(r"v?\d+\.\d+\.\d+", line)
        if match:
            versions.append(match.group(0).lstrip("v"))
    return versions


# 危险字符：可能引发 shell 注入或破坏命令行解析
_INVALID_PACKAGE_CHARS = set(";|&$`\"'\n\r\x00")


def _validate_npm_package_names(packages: list[str]) -> None:
    """校验 npm 包名/版本规范，防止命令行选项注入或 shell 元字符注入。"""
    for package in packages:
        if not package or not isinstance(package, str):
            raise ValueError("依赖包名不能为空")
        if package.startswith("-"):
            raise ValueError(f"非法的依赖包名（不能以 '-' 开头）: {package}")
        if any(ch in _INVALID_PACKAGE_CHARS for ch in package):
            raise ValueError(f"非法的依赖包名（包含危险字符）: {package}")


def resolve_workspace_runtime_dir(workspace_dir: Path, *, create: bool = False) -> Path:
    runtime_dir = workspace_dir / WORKSPACE_RUNTIME_DIR_NAME
    if create:
        os.makedirs(as_system_path(runtime_dir), exist_ok=True)
    return runtime_dir


def _normalize_node_version(version: str) -> str:
    """Normalize a Node.js version string to fnm-compatible form."""
    text = str(version or "").strip()
    if not text:
        raise ValueError("Node.js 版本不能为空")
    # fnm accepts "20", "20.11", "20.11.0", "lts/*", "lts-iron", etc.
    # Strip leading 'v' if present; fnm handles both forms.
    # Windows  bundled fnm 1.39.0 不识别裸 "lts" 别名，统一归一化为 "lts/*"。
    text = text.lstrip("v")
    if text == "lts":
        text = "lts/*"
    if not text:
        raise ValueError(f"无效的 Node.js 版本: {version}")
    return text


class NodeRuntimeService:
    """工作区 Node.js 运行环境管理服务。

    通过 fnm（Fast Node Manager）管理 Node.js 版本，支持安装、切换、
    列出远程版本等操作。每个工作区的环境信息持久化在 .env/environments.json 中。
    """

    def __init__(
        self,
        workspace_root: Path = WORKSPACE_DIR,
        workspace_registry: "WorkspaceRegistryService" | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        if workspace_registry is not None:
            self.workspace_registry = workspace_registry
        else:
            from app.services.workspace_registry import WorkspaceRegistryService

            self.workspace_registry = WorkspaceRegistryService(self.workspace_root)

    # ------------------------------------------------------------------
    # Registry management
    # ------------------------------------------------------------------

    def list_node_envs(
        self,
        user_id: str,
        workspace_id: str,
    ) -> NodeRuntimeEnvRegistryResponse:
        """列出工作区所有 Node.js 运行环境。"""
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        registry = self._read_registry(workspace_dir)
        envs = [
            NodeRuntimeEnv.model_validate(env)
            for env in registry.get("envs", [])
            if isinstance(env, dict)
        ]
        envs.sort(key=lambda item: (0 if item.active else 1, item.kind, item.env_id))
        return NodeRuntimeEnvRegistryResponse(
            workspace_id=workspace_id,
            default_env_id=registry.get("default_env_id"),
            active_env_id=registry.get("active_env_id"),
            registry_path=str(self._registry_path(workspace_dir)),
            fnm_available=self.is_fnm_available(),
            envs=envs,
            total=len(envs),
        )

    def get_node_env(
        self,
        user_id: str,
        workspace_id: str,
        env_id: str,
    ) -> NodeRuntimeEnv:
        """获取单个 Node.js 环境详情（不刷新）。"""
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        env = self._find_env(workspace_dir, env_id)
        if env is None:
            raise FileNotFoundError(f"Node.js 环境不存在: {env_id}")
        return env

    # ------------------------------------------------------------------
    # Node version management via fnm
    # ------------------------------------------------------------------

    def install_node_version(
        self,
        user_id: str,
        workspace_id: str,
        *,
        version: str,
        env_id: str = DEFAULT_NODE_ENV_ID,
        display_name: str | None = None,
    ) -> tuple[NodeRuntimeEnv, RuntimeEnvCommandResult | None]:
        """安装指定 Node.js 版本并注册到工作区。

        如果版本已安装则视为幂等操作，直接更新环境信息。
        """
        if not self.is_fnm_available():
            self._raise_fnm_not_found()

        normalized_version = _normalize_node_version(version)
        env_id = _normalize_env_id(env_id, DEFAULT_NODE_ENV_ID)
        workspace_dir = self._workspace_dir(user_id, workspace_id)

        # 先安装 Node.js 版本（首次下载可能耗时较长，给予更宽裕的超时）
        result = self._run_fnm(
            ["install", normalized_version],
            workspace_dir=workspace_dir,
            timeout=600,
        )
        if not result.ok:
            raise RuntimeError(
                result.stderr or result.error or f"fnm install {normalized_version} 失败"
            )

        # 获取已安装版本列表以确认
        list_result = self._run_fnm(
            ["list"],
            workspace_dir=workspace_dir,
        )
        installed_versions = _parse_fnm_list_versions(list_result.stdout or "")
        actual_version = normalized_version

        if installed_versions:
            if _VERSION_PATTERN.match(normalized_version):
                # 具体版本号：查找前缀匹配的已安装版本（如 20 匹配 20.15.0）
                matched = next(
                    (v for v in installed_versions if v.startswith(normalized_version)),
                    None,
                )
                if matched:
                    actual_version = matched
                    version_installed = True
                else:
                    version_installed = False
            else:
                # 别名（如 lts / lts-iron）：取已安装的第一个版本作为实际版本
                actual_version = installed_versions[0]
                version_installed = True
                logger.info(
                    "将 Node.js 别名 %s 解析为实际版本 %s",
                    normalized_version,
                    actual_version,
                )
        else:
            # 解析失败时回退到原始字符串匹配
            version_installed = normalized_version in (list_result.stdout or "")

        if not version_installed:
            # fnm install 返回 0 但版本不在列表中，可能是安装实际未完成
            logger.warning(
                "fnm install returned success but version %s not found in list",
                normalized_version,
            )

        # 构建环境记录
        now = _now_iso()
        existing = self._find_env(workspace_dir, env_id)

        env = NodeRuntimeEnv(
            env_id=env_id,
            kind="fnm",
            display_name=display_name or f"Node.js {actual_version}",
            status="ready" if version_installed else "registered",
            active=bool(existing.active if existing else False),
            node_version=actual_version,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            metadata={
                **(existing.metadata if existing else {}),
                "manager": "fnm",
                "install_source": "fnm",
            },
        )

        # 刷新 npm 版本和包列表
        inspected = self._inspect_node_env(workspace_dir, env)
        self._upsert_env(workspace_dir, inspected)
        return inspected, result

    def use_node_version(
        self,
        user_id: str,
        workspace_id: str,
        env_id: str,
        version: str,
    ) -> tuple[NodeRuntimeEnv, RuntimeEnvCommandResult | None]:
        """切换工作区 Node.js 版本（fnm use）。

        不安装新版本，仅切换已安装的版本。如果版本未安装会报错。
        """
        if not self.is_fnm_available():
            self._raise_fnm_not_found()

        normalized_version = _normalize_node_version(version)
        workspace_dir = self._workspace_dir(user_id, workspace_id)

        result = self._run_fnm(
            ["use", normalized_version],
            workspace_dir=workspace_dir,
        )
        if not result.ok:
            raise RuntimeError(
                result.stderr or result.error or f"fnm use {normalized_version} 失败"
            )

        # 获取当前激活的版本
        current_result = self._run_fnm(
            ["current"],
            workspace_dir=workspace_dir,
        )
        current_version = (current_result.stdout or "").strip()

        env_id = _normalize_env_id(env_id, DEFAULT_NODE_ENV_ID)
        now = _now_iso()
        existing = self._find_env(workspace_dir, env_id)

        env = NodeRuntimeEnv(
            env_id=env_id,
            kind="fnm",
            display_name=existing.display_name if existing else f"Node.js {normalized_version}",
            status="ready",
            active=True,
            node_version=current_version or normalized_version,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            metadata={
                **(existing.metadata if existing else {}),
                "manager": "fnm",
            },
        )

        # 更新注册表中的活跃状态
        registry = self._read_registry(workspace_dir)
        registry["active_env_id"] = env_id
        updated_envs = []
        for item in registry.get("envs", []):
            if not isinstance(item, dict):
                continue
            item = dict(item)
            item["active"] = item.get("env_id") == env_id
            updated_envs.append(item)
        registry["envs"] = updated_envs
        registry["updated_at"] = now
        self._write_registry(workspace_dir, registry)

        inspected = self._inspect_node_env(workspace_dir, env)
        self._upsert_env(workspace_dir, inspected)
        return inspected, result

    def set_default_node_version(
        self,
        user_id: str,
        workspace_id: str,
        version: str,
    ) -> RuntimeEnvCommandResult:
        """设置 fnm 全局默认 Node.js 版本。"""
        if not self.is_fnm_available():
            self._raise_fnm_not_found()

        normalized_version = _normalize_node_version(version)
        workspace_dir = self._workspace_dir(user_id, workspace_id)

        result = self._run_fnm(
            ["default", normalized_version],
            workspace_dir=workspace_dir,
        )
        if not result.ok:
            raise RuntimeError(
                result.stderr or result.error or f"fnm default {normalized_version} 失败"
            )
        return result

    def get_current_node_version(
        self,
        user_id: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        """获取当前工作区使用的 Node.js 版本。"""
        if not self.is_fnm_available():
            self._raise_fnm_not_found()

        workspace_dir = self._workspace_dir(user_id, workspace_id)

        result = self._run_fnm(
            ["current"],
            workspace_dir=workspace_dir,
        )
        if not result.ok:
            raise RuntimeError(result.stderr or result.error or "fnm current 失败")

        version = (result.stdout or "").strip()
        if not version:
            return {"version": None, "source": None}

        # 尝试从 .node-version 文件读取
        node_version_file = resolve_workspace_runtime_dir(workspace_dir) / ".node-version"
        source = "file" if os.path.exists(as_system_path(node_version_file)) else "fnm-default"

        return {
            "version": version,
            "source": source,
            "command_result": result.model_dump(mode="json"),
        }

    def uninstall_node_version(
        self,
        user_id: str,
        workspace_id: str,
        version: str,
    ) -> RuntimeEnvCommandResult:
        """卸载指定 Node.js 版本。"""
        if not self.is_fnm_available():
            self._raise_fnm_not_found()

        normalized_version = _normalize_node_version(version)
        workspace_dir = self._workspace_dir(user_id, workspace_id)

        result = self._run_fnm(
            ["uninstall", normalized_version],
            workspace_dir=workspace_dir,
        )
        if not result.ok:
            raise RuntimeError(
                result.stderr or result.error or f"fnm uninstall {normalized_version} 失败"
            )

        # 清理注册表中引用该版本的环境
        registry = self._read_registry(workspace_dir)
        updated_envs = []
        for item in registry.get("envs", []):
            if not isinstance(item, dict):
                continue
            if item.get("node_version") == normalized_version:
                # 移除引用该版本的环境
                continue
            updated_envs.append(item)
        registry["envs"] = updated_envs
        registry["updated_at"] = _now_iso()
        self._write_registry(workspace_dir, registry)

        return result

    # ------------------------------------------------------------------
    # Workspace-level binding
    # ------------------------------------------------------------------

    def ensure_workspace_node_env(
        self,
        user_id: str,
        workspace_id: str,
        *,
        env_id: str = DEFAULT_NODE_ENV_ID,
        node_version: str | None = None,
        create_if_missing: bool = False,
    ) -> NodeRuntimeEnv:
        """确保工作区存在指定 Node.js 环境，不存在时按参数创建。"""
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        existing = self._find_env(workspace_dir, env_id)
        if existing is not None:
            return existing

        if not create_if_missing:
            raise FileNotFoundError(f"Node.js 环境不存在: {env_id}")

        if not self.is_fnm_available():
            self._raise_fnm_not_found()

        target_version = _normalize_node_version(node_version or "lts")
        inspected, _ = self.install_node_version(
            user_id,
            workspace_id,
            version=target_version,
            env_id=env_id,
            display_name=f"Node.js {target_version}",
        )
        return inspected

    def bind_workspace_node_env(
        self,
        user_id: str,
        workspace_id: str,
        env_id: str,
    ) -> NodeRuntimeEnv:
        """将指定 Node.js 环境设为工作区当前 Node 环境。"""
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        env = self._find_env(workspace_dir, env_id)
        if env is None:
            raise FileNotFoundError(f"Node.js 环境不存在: {env_id}")

        registry = self._read_registry(workspace_dir)
        registry["active_env_id"] = env_id
        updated_envs = []
        for item in registry.get("envs", []):
            if not isinstance(item, dict):
                continue
            item = dict(item)
            item["active"] = item.get("env_id") == env_id
            updated_envs.append(item)
        registry["envs"] = updated_envs
        registry["updated_at"] = _now_iso()
        self._write_registry(workspace_dir, registry)

        # 同步更新工作区 runtime_binding，保留 Python/Docker 资源
        workspace = self.workspace_registry.get_workspace(
            user_id,
            workspace_id,
            include_conversations=False,
        )
        current_binding = workspace.runtime_binding
        updated_resources = ExecutionResourceGroup(
            python_env_id=current_binding.resources.python_env_id,
            node_env_id=env.env_id,
            docker_resource_id=current_binding.resources.docker_resource_id,
        )
        self.workspace_registry.update_workspace(
            user_id=user_id,
            workspace_id=workspace_id,
            runtime_binding=WorkspaceRuntimeBinding(
                env_vars=current_binding.env_vars,
                resources=updated_resources,
            ),
        )

        env.active = True
        return self._inspect_node_env(workspace_dir, env)

    def list_remote_versions(
        self,
        user_id: str,
        workspace_id: str,
        *,
        filter_expr: str = "",
    ) -> dict[str, Any]:
        """列出 fnm 可用的远程 Node.js 版本。"""
        if not self.is_fnm_available():
            self._raise_fnm_not_found()

        workspace_dir = self._workspace_dir(user_id, workspace_id)

        args = ["list-remote"]
        if filter_expr:
            args.append(filter_expr)

        result = self._run_fnm(
            args,
            workspace_dir=workspace_dir,
        )
        if not result.ok:
            raise RuntimeError(result.stderr or result.error or "fnm list-remote 失败")

        versions = []
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                versions.append(line)

        return {
            "versions": versions,
            "filter": filter_expr or None,
            "command_result": result.model_dump(mode="json"),
        }

    # ------------------------------------------------------------------
    # Project-level
    # ------------------------------------------------------------------

    def set_node_version_file(
        self,
        user_id: str,
        workspace_id: str,
        version: str,
    ) -> dict[str, Any]:
        """在工作区 .env/.node-version 中锁定 Node.js 版本。

        这是项目级别的版本锁定，类似于 .nvmrc 或 .node-version。
        """
        normalized_version = _normalize_node_version(version)
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        env_dir = resolve_workspace_runtime_dir(workspace_dir, create=True)

        version_file = env_dir / ".node-version"
        Path(as_system_path(version_file)).write_text(f"{normalized_version}\n", encoding="utf-8")

        # 更新注册表
        registry = self._read_registry(workspace_dir)
        registry["default_env_id"] = registry.get("default_env_id") or DEFAULT_NODE_ENV_ID
        registry["updated_at"] = _now_iso()
        self._write_registry(workspace_dir, registry)

        return {
            "version": normalized_version,
            "file": str(version_file),
            "updated_at": registry["updated_at"],
        }

    # ------------------------------------------------------------------
    # 环境生命周期：ensure + bind
    # ------------------------------------------------------------------

    def ensure_node_env(
        self,
        user_id: str,
        workspace_id: str,
        env_id: str = DEFAULT_NODE_ENV_ID,
        display_name: str = "Workspace Node",
        node_version: str | None = None,
        npm_packages: list[str] | None = None,
    ) -> tuple[NodeRuntimeEnv, RuntimeEnvCommandResult | None]:
        """创建或刷新工作区 Node 环境。

        如果 fnm 不可用则尝试自动安装。写入 package.json 和 .node-version，
        可选安装 npm 包。
        """
        if not self.is_fnm_available():
            raise RuntimeError(
                "fnm 不可用，无法管理 Node.js 运行时。"
                "请安装 fnm：https://fnm.vercel.app/ 或 https://github.com/Schniz/fnm"
            )

        env_id = _normalize_env_id(env_id, DEFAULT_NODE_ENV_ID)
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        env_dir = self._env_dir(workspace_dir)
        os.makedirs(as_system_path(env_dir), exist_ok=True)
        now = _now_iso()

        # 写入 package.json（如果不存在）
        package_json = env_dir / "package.json"
        if not os.path.exists(as_system_path(package_json)):
            project_name = f"aiasys-workspace-{workspace_id}"
            Path(as_system_path(package_json)).write_text(
                json.dumps(
                    {
                        "name": project_name,
                        "version": "0.1.0",
                        "private": True,
                        "dependencies": {},
                        "devDependencies": {},
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

        # 写入 .node-version
        if node_version:
            normalized = _normalize_node_version(node_version)
            version_file = env_dir / ".node-version"
            Path(as_system_path(version_file)).write_text(f"{normalized}\n", encoding="utf-8")

        # 安装 npm 包
        if npm_packages:
            _validate_npm_package_names(npm_packages)
        result: RuntimeEnvCommandResult | None = None
        if npm_packages:
            result = self._run_fnm(
                ["npm", "install", "--save", *npm_packages],
                cwd=str(env_dir),
            )
            if not result.ok:
                raise RuntimeError(result.stderr or result.error or "npm install 失败")

        # 读取现有环境或创建新的
        existing = self._find_env(workspace_dir, env_id)
        env = NodeRuntimeEnv(
            env_id=env_id,
            kind="fnm",
            display_name=display_name.strip() or "Workspace Node",
            status="registered",
            active=bool(existing.active if existing else False),
            node_version=node_version or self._read_node_version(env_dir),
            npm_version=self._read_npm_version(),
            created_at=existing.created_at if existing else now,
            updated_at=now,
            metadata={
                **(existing.metadata if existing else {}),
                "manager": "fnm",
                "package_json": str(package_json),
            },
        )
        inspected = self._inspect_node_env(workspace_dir, env)
        self._upsert_env(workspace_dir, inspected)
        return inspected, result

    def bind_node_env(
        self,
        user_id: str,
        workspace_id: str,
        env_id: str,
    ) -> NodeRuntimeEnv:
        """将 Node 环境设为工作区默认。"""
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        env = self._inspect_node_env(
            workspace_dir,
            self._find_env(workspace_dir, env_id)
            or NodeRuntimeEnv(env_id=env_id, display_name="Node", kind="fnm"),
        )
        registry = self._read_registry(workspace_dir)
        registry["active_env_id"] = env.env_id
        updated_envs = []
        for item in registry.get("envs", []):
            if not isinstance(item, dict):
                continue
            item = dict(item)
            item["active"] = item.get("env_id") == env.env_id
            updated_envs.append(item)
        registry["envs"] = updated_envs
        registry["updated_at"] = _now_iso()
        self._write_registry(workspace_dir, registry)

        env.active = True
        return env

    # ------------------------------------------------------------------
    # Utility / introspection
    # ------------------------------------------------------------------

    def _read_node_version(self, env_dir: Path) -> str | None:
        """从 .node-version 文件读取版本。"""
        version_file = env_dir / ".node-version"
        if not os.path.exists(as_system_path(version_file)):
            return None
        text = Path(as_system_path(version_file)).read_text(encoding="utf-8").strip()
        return text or None

    def _read_npm_version(self) -> str | None:
        """读取当前 npm 版本。"""
        try:
            fnm_bin = self._find_fnm_binary()
            if not fnm_bin:
                return None
            completed = subprocess.run(
                [fnm_bin, "env", "--json"],
                capture_output=True,
                timeout=10,
                **subprocess_kwargs(),
            )
            if completed.returncode == 0:
                import json as _json

                _json.loads(smart_decode(completed.stdout or b""))
                # fnm env --json 包含 PATH，从中提取 npm 版本
                # 这里简化处理，返回 None 让调用方自行检测
        except Exception:
            pass
        return None

    def is_fnm_available(self) -> bool:
        """检查 fnm 是否可用。"""
        return self._find_fnm_binary() is not None

    def _find_fnm_binary(self) -> str | None:
        """查找 fnm 可执行文件路径。

        查找顺序：
        1. AIASYS_BUNDLED_FNM_PATH 环境变量（桌面版设置）
        2. shutil.which("fnm")
        3. ~/.fnm/fnm（fnm 默认安装位置）
        """
        # 1. 环境变量（桌面版由 service-manager 设置）
        bundled = os.environ.get("AIASYS_BUNDLED_FNM_PATH")
        if bundled:
            p = Path(bundled)
            if p.is_file():
                return str(p)

        # 2. PATH 查找
        fnm_in_path = shutil.which("fnm")
        if fnm_in_path:
            return fnm_in_path

        # 3. ~/.fnm/fnm（fnm 默认安装位置）
        home = Path.home()
        candidates = [
            home / ".fnm" / "fnm",
        ]
        if os.name == "nt":
            candidates.append(home / ".fnm" / "fnm.exe")

        for p in candidates:
            if p.is_file():
                return str(p)

        return None

    def _run_fnm(
        self,
        args: list[str],
        *,
        workspace_dir: Path,
        timeout: int = 300,
    ) -> RuntimeEnvCommandResult:
        """执行 fnm 命令。

        自动设置 FNM_DIR 环境变量（优先使用桌面版指定的 AIASYS_FNM_DIR，
        否则回退到 fnm 二进制同级目录），并在 PATH 中添加 fnm 所在目录。
        """
        fnm_binary = self._find_fnm_binary()
        if not fnm_binary:
            return RuntimeEnvCommandResult(
                ok=False,
                command=[fnm_binary] + args if fnm_binary else ["fnm"] + args,
                cwd=str(workspace_dir),
                error="fnm 二进制未找到，请安装 fnm 或设置 AIASYS_BUNDLED_FNM_PATH",
            )

        fnm_dir = str(Path(fnm_binary).parent)
        fnm_data_dir = os.environ.get("AIASYS_FNM_DIR") or fnm_dir

        env = dict(os.environ)
        env.setdefault("FNM_LOGLEVEL", "quiet")
        env["FNM_DIR"] = fnm_data_dir

        # 确保 fnm 所在目录在 PATH 中
        path_env = env.get("PATH", "")
        path_parts = path_env.split(os.pathsep) if path_env else []
        if fnm_dir not in path_parts:
            env["PATH"] = fnm_dir + os.pathsep + path_env if path_env else fnm_dir

        command = [fnm_binary] + args

        try:
            completed = subprocess.run(
                command,
                cwd=str(workspace_dir),
                env=env,
                capture_output=True,
                timeout=timeout,
                check=False,
                **subprocess_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            return RuntimeEnvCommandResult(
                ok=False,
                command=command,
                cwd=str(workspace_dir),
                error=f"fnm 命令执行超时（{timeout}s），通常是首次下载 Node.js 二进制时网络较慢。",
                stdout=_safe_tail(smart_decode(exc.stdout or b"")),
                stderr=_safe_tail(smart_decode(exc.stderr or b"")),
            )
        except Exception as exc:
            return RuntimeEnvCommandResult(
                ok=False,
                command=command,
                cwd=str(workspace_dir),
                error=str(exc),
            )

        return RuntimeEnvCommandResult(
            ok=completed.returncode == 0,
            command=command,
            cwd=str(workspace_dir),
            returncode=completed.returncode,
            stdout=_safe_tail(smart_decode(completed.stdout or b"")),
            stderr=_safe_tail(smart_decode(completed.stderr or b"")),
        )

    # ------------------------------------------------------------------
    # Internal helpers — registry
    # ------------------------------------------------------------------

    def _workspace_dir(self, user_id: str, workspace_id: str) -> Path:
        return self.workspace_registry.get_workspace_root(user_id, workspace_id)

    def _env_dir(self, workspace_dir: Path) -> Path:
        return resolve_workspace_runtime_dir(workspace_dir, create=True)

    def _env_dir_path(self, workspace_dir: Path) -> Path:
        return resolve_workspace_runtime_dir(workspace_dir)

    def _registry_path(self, workspace_dir: Path) -> Path:
        return self._env_dir_path(workspace_dir) / _REGISTRY_FILE

    def _read_registry(self, workspace_dir: Path) -> dict[str, Any]:
        path = self._registry_path(workspace_dir)
        if not os.path.exists(as_system_path(path)):
            return {
                "_schema_version": 1,
                "default_env_id": DEFAULT_NODE_ENV_ID,
                "active_env_id": None,
                "envs": [],
                "updated_at": None,
            }
        try:
            data = json.loads(Path(as_system_path(path)).read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        envs = data.get("envs")
        return {
            "_schema_version": 1,
            "default_env_id": data.get("default_env_id") or DEFAULT_NODE_ENV_ID,
            "active_env_id": data.get("active_env_id"),
            "envs": envs if isinstance(envs, list) else [],
            "updated_at": data.get("updated_at"),
        }

    def _write_registry(self, workspace_dir: Path, data: dict[str, Any]) -> None:
        path = self._registry_path(workspace_dir)
        os.makedirs(as_system_path(path.parent), exist_ok=True)
        Path(as_system_path(path)).write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _find_env(self, workspace_dir: Path, env_id: str) -> NodeRuntimeEnv | None:
        registry = self._read_registry(workspace_dir)
        for item in registry.get("envs", []):
            if isinstance(item, dict) and item.get("env_id") == env_id:
                return NodeRuntimeEnv.model_validate(item)
        return None

    def _upsert_env(self, workspace_dir: Path, env: NodeRuntimeEnv) -> None:
        registry = self._read_registry(workspace_dir)
        envs: list[dict[str, Any]] = []
        found = False
        for item in registry.get("envs", []):
            if not isinstance(item, dict):
                continue
            if item.get("env_id") == env.env_id:
                envs.append(env.model_dump(mode="json"))
                found = True
            else:
                envs.append(item)
        if not found:
            envs.append(env.model_dump(mode="json"))
        registry["envs"] = envs
        registry["default_env_id"] = registry.get("default_env_id") or env.env_id
        if env.active:
            registry["active_env_id"] = env.env_id
        registry["updated_at"] = _now_iso()
        self._write_registry(workspace_dir, registry)

    # ------------------------------------------------------------------
    # Internal helpers — inspection
    # ------------------------------------------------------------------

    def _inspect_node_env(self, workspace_dir: Path, env: NodeRuntimeEnv) -> NodeRuntimeEnv:
        """刷新 Node.js 环境信息：版本、npm 版本、已安装包。"""
        self._env_dir_path(workspace_dir)

        # 获取当前 Node 版本
        version_result = self._run_fnm(
            ["current"],
            workspace_dir=workspace_dir,
        )
        if version_result.ok:
            current_version = (version_result.stdout or "").strip()
            if current_version and current_version != "none":
                env.node_version = current_version

        # 获取 npm 版本
        npm_result = self._run_fnm(
            ["env", "--use-on-cd"],
            workspace_dir=workspace_dir,
        )
        if npm_result.ok:
            # 从环境变量输出中解析 NPM 版本
            for line in (npm_result.stdout or "").splitlines():
                if line.startswith("NPM_VERSION="):
                    env.npm_version = line.split("=", 1)[1].strip()
                    break

        # 列出已安装包
        env.packages = self._list_node_packages(workspace_dir)
        env.package_count = len(env.packages)

        # 根据信息判断状态
        if env.node_version:
            env.status = "ready"
        else:
            env.status = "registered"

        env.updated_at = _now_iso()
        return env

    def _list_node_packages(self, workspace_dir: Path) -> list[RuntimeEnvPackage]:
        """列出当前工作区 node_modules 中的已安装包。"""
        node_modules = workspace_dir / "node_modules"
        if not node_modules.is_dir():
            return []

        packages: list[RuntimeEnvPackage] = []
        try:
            for entry in node_modules.iterdir():
                if not entry.is_dir():
                    continue
                name = entry.name
                # 跳过以 @ 开头的 scope 包目录（需要读取子目录）
                if name.startswith("@"):
                    for scope_dir in entry.iterdir():
                        if scope_dir.is_dir():
                            pkg_json = scope_dir / "package.json"
                            if pkg_json.is_file():
                                version = self._read_package_version(pkg_json)
                                if version:
                                    packages.append(
                                        RuntimeEnvPackage(
                                            name=f"{name}/{scope_dir.name}",
                                            version=version,
                                        )
                                    )
                else:
                    pkg_json = entry / "package.json"
                    if pkg_json.is_file():
                        version = self._read_package_version(pkg_json)
                        if version:
                            packages.append(RuntimeEnvPackage(name=name, version=version))
        except (OSError, PermissionError):
            pass

        packages.sort(key=lambda item: item.name.lower())
        return packages

    def _read_package_version(self, package_json: Path) -> str | None:
        try:
            data = json.loads(Path(as_system_path(package_json)).read_text(encoding="utf-8"))
            version = str(data.get("version") or "").strip()
            return version or None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Error helpers
    # ------------------------------------------------------------------

    def _raise_fnm_not_found(self) -> FileNotFoundError:
        install_hint = (
            "请安装 fnm：curl -fsSL https://fnm.vercel.app/install | bash\n"
            "或从 https://github.com/Schniz/fnm 下载二进制。"
        )
        if sys.platform == "win32":
            install_hint = (
                "请安装 fnm：winget install Schniz.fnm\n或从 https://github.com/Schniz/fnm 下载。"
            )
        return FileNotFoundError(f"fnm 不可用，无法管理 Node.js 运行时。{install_hint}")


_node_runtime_service: NodeRuntimeService | None = None


def get_node_runtime_service() -> NodeRuntimeService:
    global _node_runtime_service
    if _node_runtime_service is None:
        _node_runtime_service = NodeRuntimeService(WORKSPACE_DIR)
    return _node_runtime_service

"""工作区模板管理。

模板存放在 apps/backend/templates/ 目录下，每个模板是一个子目录，包含：
- template.toml: 模板元数据和预置文件声明（优先）
- template.json: 兼容旧格式
- 可选的其他预置文件

模板内容在创建工作区时通过 WorkspaceRegistryService.create_workspace 应用。
"""

from __future__ import annotations

import json
import logging
import secrets
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

from app.capabilities.models import CapabilityDeclaration, CapabilityKind
from app.core.config import get_user_global_workspace_dir
from app.models.workspace import ExecutionResourceGroup

logger = logging.getLogger(__name__)

# 模板根目录（相对于 backend 包）
_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


@dataclass(frozen=True)
class TemplateFileSpec:
    relative_path: str
    content: str
    source_path: str | None = None


@dataclass(frozen=True)
class WorkspaceTemplate:
    template_id: str
    name: str
    description: str
    icon: str
    category: str
    default_title: str
    default_description: str
    initial_conversation_title: str
    env_kind: str  # "none" | "uv" | "registered"（兼容字段，优先使用 runtime_resources）
    files: list[TemplateFileSpec]
    source_dir: Path  # 模板源目录，用于复制 workspace_memory.md 等额外文件
    recommended_skills: list[str]  # 兼容旧格式
    recommended_mcps: list[str]  # 兼容旧格式
    recommended_capabilities: list[CapabilityDeclaration]
    env_vars: dict[str, str] = field(default_factory=dict)
    runtime_resources: ExecutionResourceGroup = field(default_factory=ExecutionResourceGroup)


def _list_template_dirs() -> list[Path]:
    try:
        if not _TEMPLATES_DIR.exists() or not _TEMPLATES_DIR.is_dir():
            return []
        return [p for p in _TEMPLATES_DIR.iterdir() if p.is_dir()]
    except OSError:
        logger.warning("无法读取系统模板目录: %s", _TEMPLATES_DIR)
        return []


def _load_template(template_dir: Path) -> WorkspaceTemplate | None:
    toml_path = template_dir / "template.toml"
    json_path = template_dir / "template.json"

    raw: dict[str, Any] | None = None
    if toml_path.exists():
        if tomllib is None:
            logger.warning("Python 版本低于 3.11，无法解析 TOML 模板: %s", toml_path)
            return None
        try:
            raw = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("模板 TOML 解析失败: %s - %s", toml_path, exc)
            return None
    elif json_path.exists():
        try:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("模板 JSON 解析失败: %s", json_path)
            return None
    else:
        return None

    if not isinstance(raw, dict):
        return None

    template_id = str(raw.get("template_id", "")).strip()
    if not template_id:
        return None

    files: list[TemplateFileSpec] = []
    for item in raw.get("files") or []:
        if isinstance(item, dict):
            rel_path = str(item.get("relative_path", "")).strip()
            content = str(item.get("content", ""))
            src_path = str(item.get("source_path", "")).strip() or None
            if rel_path:
                # 如果提供了 source_path，从模板目录读取内容
                if src_path:
                    if not _is_safe_relative_path(src_path):
                        logger.warning("模板 source_path 包含非法路径，跳过: %s", src_path)
                        continue
                    src_file = (template_dir / src_path).resolve()
                    template_dir_resolved = template_dir.resolve()
                    try:
                        src_file.relative_to(template_dir_resolved)
                    except ValueError:
                        logger.warning("模板 source_path 解析后超出模板目录，跳过: %s", src_path)
                        continue
                    try:
                        if src_file.exists() and src_file.is_file():
                            content = src_file.read_text(encoding="utf-8")
                        else:
                            logger.warning("模板 source_path 文件不存在，跳过该文件: %s", src_file)
                            continue
                    except OSError as exc:
                        logger.warning("读取模板 source_path 文件失败，跳过: %s: %s", src_file, exc)
                        continue
                files.append(
                    TemplateFileSpec(relative_path=rel_path, content=content, source_path=src_path)
                )

    env_kind = str(raw.get("env_kind", "none")).strip().lower()
    runtime_resources = _parse_runtime_resources(
        raw.get("runtime_contract") or raw.get("runtime_resources")
    )
    # 兼容旧 env_kind：如果 runtime_resources 为空但 env_kind 是 uv/registered，则映射为 Python 资源
    if not runtime_resources.python_env_id and env_kind in ("uv", "registered"):
        runtime_resources = ExecutionResourceGroup(python_env_id="workspace-default")

    return WorkspaceTemplate(
        template_id=template_id,
        name=str(raw.get("name", template_id)).strip(),
        description=str(raw.get("description", "")).strip(),
        icon=str(raw.get("icon", "file")).strip(),
        category=str(raw.get("category", "通用")).strip(),
        default_title=str(raw.get("default_title", "新任务")).strip(),
        default_description=str(raw.get("default_description", "")).strip(),
        initial_conversation_title=str(raw.get("initial_conversation_title", "新对话")).strip(),
        env_kind=env_kind,
        files=files,
        source_dir=template_dir,
        recommended_skills=[
            str(s).strip() for s in (raw.get("recommended_skills") or []) if str(s).strip()
        ],
        recommended_mcps=[
            str(s).strip() for s in (raw.get("recommended_mcps") or []) if str(s).strip()
        ],
        recommended_capabilities=_parse_recommended_capabilities(
            raw.get("recommended_capabilities")
        ),
        env_vars=_parse_env_vars(raw.get("env_vars")),
        runtime_resources=runtime_resources,
    )


def _parse_env_vars(raw: Any) -> dict[str, str]:
    """解析模板中的 env_vars 字段。"""
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if isinstance(k, (str, int, float))}


def _parse_runtime_resources(raw: Any) -> ExecutionResourceGroup:
    """解析模板中的 runtime_contract / runtime_resources 字段。"""
    if not isinstance(raw, dict):
        return ExecutionResourceGroup()
    resources_raw = raw.get("resources") or {}
    if not isinstance(resources_raw, dict):
        resources_raw = {}
    # 兼容旧字段：env_id / python_env_id 都映射到 python_env_id
    python_env_id = (
        resources_raw.get("python_env_id")
        or resources_raw.get("env_id")
        or raw.get("env_id")
        or None
    )
    return ExecutionResourceGroup(
        python_env_id=python_env_id,
        node_env_id=resources_raw.get("node_env_id") or None,
        docker_resource_id=resources_raw.get("docker_resource_id") or None,
    )


def _parse_recommended_capabilities(raw: Any) -> list[CapabilityDeclaration]:
    """解析模板中的 recommended_capabilities 字段。"""
    results: list[CapabilityDeclaration] = []
    if not isinstance(raw, list):
        return results
    for item in raw:
        if not isinstance(item, dict):
            continue
        cap_id = str(item.get("capability_id", "")).strip()
        if not cap_id:
            continue
        kind_str = str(item.get("kind", "skill_pack")).strip()
        try:
            kind = CapabilityKind(kind_str)
        except ValueError:
            kind = CapabilityKind.SKILL_PACK
        config = item.get("config") or {}
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                config = {}
        if not isinstance(config, dict):
            config = {}
        results.append(
            CapabilityDeclaration(
                capability_id=cap_id,
                kind=kind,
                required=bool(item.get("required", True)),
                auto_activate=bool(item.get("auto_activate", True)),
                config=config,
            )
        )
    return results


def _dump_template_toml(data: dict[str, Any]) -> str:
    """将模板数据序列化为 TOML 字符串（使用 tomli-w）。"""
    import tomli_w

    # 过滤掉空值和已废弃字段，减少序列化噪音
    payload: dict[str, Any] = {}
    for key in [
        "template_id",
        "name",
        "description",
        "icon",
        "category",
        "default_title",
        "default_description",
        "initial_conversation_title",
        "env_kind",
    ]:
        if key in data:
            payload[key] = data[key]

    skills = data.get("recommended_skills") or []
    if skills:
        payload["recommended_skills"] = skills

    mcps = data.get("recommended_mcps") or []
    if mcps:
        payload["recommended_mcps"] = mcps

    files = data.get("files") or []
    if files:
        payload["files"] = [
            {k: v for k, v in f.items() if v is not None and v != ""} for f in files
        ]

    env_vars = data.get("env_vars") or {}
    if env_vars:
        payload["env_vars"] = env_vars

    runtime_resources = data.get("runtime_resources") or {}
    if runtime_resources:
        payload["runtime_resources"] = {k: v for k, v in runtime_resources.items() if v is not None}

    caps = data.get("recommended_capabilities") or []
    if caps:
        payload["recommended_capabilities"] = [
            {k: v for k, v in cap.items() if v is not None} for cap in caps
        ]

    result = tomli_w.dumps(payload)
    # 确保生成的 TOML 有效（防御 tomli-w 潜在转义问题）
    if tomllib is not None:
        try:
            tomllib.loads(result)
        except Exception as exc:
            raise ValueError(f"模板 TOML 序列化失败，内容包含非法字符: {exc}")
    return result


def _get_user_templates_dir(user_id: str) -> Path:
    """返回用户自定义模板目录。"""
    return get_user_global_workspace_dir(user_id) / ".aiasys" / "templates"


def _list_user_template_dirs(user_id: str) -> list[Path]:
    """扫描用户自定义模板目录。"""
    user_dir = _get_user_templates_dir(user_id)
    if not user_dir.exists() or not user_dir.is_dir():
        return []
    try:
        return [p for p in user_dir.iterdir() if p.is_dir()]
    except OSError:
        logger.warning("无法读取用户模板目录: %s", user_dir)
        return []


def _default_template_sort_key(t: WorkspaceTemplate) -> tuple[int, str]:
    """默认模板排序键：official-default → blank-workspace → 其余按名称。"""
    if t.template_id == "official-default":
        return (0, "")
    if t.template_id == "blank-workspace":
        return (1, "")
    return (2, t.name)


def apply_template_order(
    templates: list[WorkspaceTemplate],
    order: list[str] | None,
) -> list[WorkspaceTemplate]:
    """按用户自定义顺序重排模板。

    - order 中存在的模板按 order 中的位置排列
    - order 中不存在的模板按默认规则排在后面
    """
    if not order:
        return templates

    order_map = {tid: idx for idx, tid in enumerate(order)}
    mentioned = [t for t in templates if t.template_id in order_map]
    mentioned.sort(key=lambda t: order_map[t.template_id])
    unmentioned = [t for t in templates if t.template_id not in order_map]
    unmentioned.sort(key=_default_template_sort_key)
    return mentioned + unmentioned


def list_workspace_templates(
    user_id: str | None = None,
    installed_only: bool = False,
    template_order: list[str] | None = None,
) -> list[WorkspaceTemplate]:
    """扫描并返回模板列表。

    Args:
        user_id: 用户 ID，用于扫描用户自定义模板。
        installed_only: 为 True 时只返回用户目录中的模板（已安装）。
                        为 False 时返回系统内置 + 用户自定义（用户自定义覆盖同名）。
        template_order: 用户自定义模板顺序列表，可选。

    返回列表默认按 official-default → blank-workspace → 其余按名称排序。
    传入 template_order 时，order 中存在的模板按 order 排列，其余保持默认顺序追加到末尾。
    """
    by_id: dict[str, WorkspaceTemplate] = {}

    if not installed_only:
        # 先扫描系统内置
        for template_dir in _list_template_dirs():
            tmpl = _load_template(template_dir)
            if tmpl is not None:
                by_id[tmpl.template_id] = tmpl

    # 再扫描用户自定义（覆盖同名）
    if user_id:
        for template_dir in _list_user_template_dirs(user_id):
            tmpl = _load_template(template_dir)
            if tmpl is not None:
                by_id[tmpl.template_id] = tmpl

    templates = list(by_id.values())
    templates.sort(key=_default_template_sort_key)

    if template_order:
        templates = apply_template_order(templates, template_order)

    return templates


def get_workspace_template(
    template_id: str, user_id: str | None = None
) -> WorkspaceTemplate | None:
    """按 ID 获取单个模板（用户自定义优先）。"""
    if user_id:
        for template_dir in _list_user_template_dirs(user_id):
            tmpl = _load_template(template_dir)
            if tmpl is not None and tmpl.template_id == template_id:
                return tmpl
    for template_dir in _list_template_dirs():
        tmpl = _load_template(template_dir)
        if tmpl is not None and tmpl.template_id == template_id:
            return tmpl
    return None


def _is_safe_relative_path(path: str) -> bool:
    """检查 relative_path 是否安全（不包含路径穿越或隐藏路径）。"""
    if not path or not path.strip():
        return False
    # 禁止绝对路径
    if path.startswith("/"):
        return False
    # 禁止控制字符
    if any(ord(c) < 32 for c in path):
        return False
    parts = path.replace("\\", "/").split("/")
    # 禁止 .. 或空组件导致的异常路径
    if ".." in parts or "" in parts:
        return False
    # 禁止以 . 开头的隐藏文件/目录（如 .git/config、.aiasys/workspace/workspace.json）
    for part in parts:
        if part.startswith("."):
            return False
    return True


def _is_safe_template_id(template_id: str) -> bool:
    """检查 template_id 是否安全（不包含路径穿越）。"""
    if not template_id or not template_id.strip():
        return False
    # 禁止绝对路径
    if template_id.startswith("/"):
        return False
    # 禁止路径分隔符和穿越
    if "/" in template_id or "\\" in template_id or ".." in template_id:
        return False
    # 禁止 . 和隐藏名称
    if template_id.startswith(".") or template_id == ".":
        return False
    return True


def apply_template_to_workspace(
    workspace_dir: Path,
    template: WorkspaceTemplate,
    user_id: str | None = None,
    install_capabilities: list[str] | None = None,
    template_files: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """将模板预置文件写入工作区目录，并安装推荐能力。

    返回 (能力安装结果列表, 警告信息列表)。
    能力安装结果每项包含 capability_id、success、required、message。
    """
    warnings: list[str] = []

    # 1. 应用 template.json 中声明的文件
    allowed_files = set(template_files) if template_files is not None else None
    for spec in template.files:
        if allowed_files is not None and spec.relative_path not in allowed_files:
            continue
        if not _is_safe_relative_path(spec.relative_path):
            logger.warning("跳过不安全的模板文件路径: %s", spec.relative_path)
            continue
        file_path = workspace_dir / spec.relative_path
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(spec.content, encoding="utf-8")
        except OSError as exc:
            logger.warning("写入模板文件失败 %s: %s", file_path, exc)

    # 2. 复制 workspace_memory.md（如果模板目录存在该文件）
    memory_src = template.source_dir / "workspace_memory.md"
    if memory_src.exists():
        memory_dst = workspace_dir / ".aiasys" / "memory" / "workspace_memory.md"
        try:
            memory_dst.parent.mkdir(parents=True, exist_ok=True)
            memory_dst.write_text(memory_src.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError as exc:
            logger.warning("复制模板 memory 文件失败 %s: %s", memory_dst, exc)

    # 3. 应用模板环境变量
    if template.env_vars and user_id is not None:
        try:
            from app.services.workspace_registry import get_workspace_registry_service

            registry = get_workspace_registry_service()
            workspace_id = workspace_dir.name
            existing = registry.get_workspace_env_vars(user_id, workspace_id)
            merged = {**existing, **template.env_vars}
            registry.set_workspace_env_vars(user_id, workspace_id, merged)
        except Exception:
            logger.warning("应用模板环境变量失败", exc_info=True)
            warnings.append("模板环境变量应用失败")

    # 4. 安装模板推荐的能力（统一能力层）
    declarations = list(template.recommended_capabilities)

    # 兼容旧格式：把 recommended_skills / recommended_mcps 转为统一声明
    if not declarations:
        for skill_name in template.recommended_skills:
            declarations.append(
                CapabilityDeclaration(
                    capability_id=skill_name,
                    kind=CapabilityKind.SKILL_PACK,
                    required=True,
                    auto_activate=True,
                )
            )
        for mcp_name in template.recommended_mcps:
            declarations.append(
                CapabilityDeclaration(
                    capability_id=mcp_name,
                    kind=CapabilityKind.MCP_SERVER,
                    required=True,
                    auto_activate=True,
                )
            )

    # 过滤用户取消勾选的能力
    if install_capabilities is not None:
        declarations = [d for d in declarations if d.capability_id in install_capabilities]

    results: list[dict[str, Any]] = []
    if declarations:
        try:
            from app.capabilities import get_capability_manager

            mgr = get_capability_manager()
            install_results = mgr.apply_template_declaration(workspace_dir, declarations)
            for result in install_results:
                results.append(
                    {
                        "capability_id": result.capability_id,
                        "success": result.success,
                        "required": next(
                            (
                                d.required
                                for d in declarations
                                if d.capability_id == result.capability_id
                            ),
                            True,
                        ),
                        "message": result.message,
                    }
                )
                if not result.success:
                    logger.warning("能力安装失败: %s - %s", result.capability_id, result.message)
        except Exception:
            logger.warning("模板能力安装异常", exc_info=True)
            for decl in declarations:
                results.append(
                    {
                        "capability_id": decl.capability_id,
                        "success": False,
                        "required": decl.required,
                        "message": "能力安装过程中发生异常",
                    }
                )

    return results, warnings


def build_template_payload(template: WorkspaceTemplate) -> dict[str, Any]:
    """序列化为 API 响应字典。

    统一能力层优先：把旧格式的 recommended_skills / recommended_mcps
    转成 CapabilityDeclaration 并入 recommended_capabilities，
    前端只认 recommended_capabilities 一个字段即可。
    """
    # 判断是否为系统内置模板
    try:
        is_builtin = (
            _TEMPLATES_DIR in template.source_dir.parents or template.source_dir == _TEMPLATES_DIR
        )
    except ValueError:
        is_builtin = False

    # 统一归并：旧格式 skills/mcps → capabilities
    capabilities = list(template.recommended_capabilities)
    if not capabilities:
        for skill_name in template.recommended_skills:
            capabilities.append(
                CapabilityDeclaration(
                    capability_id=skill_name,
                    kind=CapabilityKind.SKILL_PACK,
                    required=True,
                    auto_activate=True,
                )
            )
        for mcp_name in template.recommended_mcps:
            capabilities.append(
                CapabilityDeclaration(
                    capability_id=mcp_name,
                    kind=CapabilityKind.MCP_SERVER,
                    required=True,
                    auto_activate=True,
                )
            )

    return {
        "template_id": template.template_id,
        "name": template.name,
        "description": template.description,
        "icon": template.icon,
        "category": template.category,
        "default_title": template.default_title,
        "default_description": template.default_description,
        "initial_conversation_title": template.initial_conversation_title,
        "env_kind": template.env_kind,
        "is_builtin": is_builtin,
        "recommended_skills": [],  # 旧格式字段，已归并入 recommended_capabilities
        "recommended_mcps": [],  # 旧格式字段，已归并入 recommended_capabilities
        "recommended_capabilities": [
            {
                "capability_id": d.capability_id,
                "kind": d.kind.value,
                "required": d.required,
                "auto_activate": d.auto_activate,
                "config": d.config,
            }
            for d in capabilities
        ],
        "files": [
            {
                "relative_path": f.relative_path,
                "content": f.content,
                "source_path": f.source_path,
            }
            for f in template.files
        ],
        "env_vars": template.env_vars,
        "runtime_resources": template.runtime_resources.model_dump(mode="json"),
    }


def _generate_template_id(name: str) -> str:
    """基于名称生成模板 ID，避免冲突。"""
    base = "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")
    if not base:
        base = "custom"
    suffix = secrets.token_hex(3)
    return f"{base}-{suffix}"


def delete_user_template(template_id: str, user_id: str) -> bool:
    """删除用户目录中的模板。支持卸载已安装的内置模板。

    系统内置模板（未安装到用户目录的）不可删除。
    如果用户目录中存在该模板（包括从市场安装的内置模板副本），则删除。

    返回 True 表示删除成功，False 表示模板不存在或无法删除。
    """
    if not _is_safe_template_id(template_id):
        logger.warning("拒绝删除不安全的模板 ID: %s", template_id)
        return False

    # 优先检查用户目录：已安装模板（含从市场安装的内置模板副本）可删除
    user_dir = _get_user_templates_dir(user_id)
    target_dir = user_dir / template_id
    if target_dir.exists() and target_dir.is_dir():
        try:
            shutil.rmtree(target_dir)
            return True
        except OSError as exc:
            logger.warning("删除用户模板失败 %s: %s", target_dir, exc)
            return False

    # 用户目录不存在，检查是否是系统内置模板（未安装）
    for template_dir in _list_template_dirs():
        tmpl = _load_template(template_dir)
        if tmpl is not None and tmpl.template_id == template_id:
            # 系统内置且未安装到用户目录，不可删除
            return False

    return False


def export_workspace_as_template(
    workspace_dir: Path,
    user_id: str,
    *,
    name: str,
    description: str = "",
    icon: str = "file",
    category: str = "自定义",
    template_id: str | None = None,
    files: list[str] | None = None,
    include_env_vars: bool = False,
) -> WorkspaceTemplate:
    """从工作区导出为自定义模板，保存到用户全局模板目录。"""
    # 读取工作区 meta
    meta_path = workspace_dir / ".aiasys" / "workspace" / "workspace.json"
    meta: dict[str, Any] = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # 推断 env_kind 和 runtime_resources
    runtime_binding = meta.get("runtime_binding") or {}
    env_id = runtime_binding.get("env_id")
    sandbox_mode = runtime_binding.get("sandbox_mode")
    resources_raw = runtime_binding.get("resources") or {}
    if not isinstance(resources_raw, dict):
        resources_raw = {}
    runtime_resources = ExecutionResourceGroup(
        python_env_id=resources_raw.get("python_env_id") or env_id or None,
        node_env_id=resources_raw.get("node_env_id") or None,
        docker_resource_id=resources_raw.get("docker_resource_id") or None,
    )
    if sandbox_mode == "docker":
        env_kind = "docker"
    elif env_id == "workspace-default":
        env_kind = "uv"
    elif env_id:
        env_kind = "registered"
    else:
        env_kind = "none"

    # 读取文件
    template_files: list[TemplateFileSpec] = []
    file_paths = files if files is not None else ["README.md", "AGENTS.md"]
    for rel_path in file_paths:
        if not _is_safe_relative_path(rel_path):
            logger.warning("跳过不安全的模板文件路径: %s", rel_path)
            continue
        file_path = workspace_dir / rel_path
        if file_path.exists() and file_path.is_file():
            try:
                template_files.append(
                    TemplateFileSpec(
                        relative_path=rel_path,
                        content=file_path.read_text(encoding="utf-8"),
                    )
                )
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("读取工作区文件失败 %s: %s", file_path, exc)

    # 读取环境变量
    env_vars: dict[str, str] = {}
    if include_env_vars:
        try:
            from app.services.workspace_registry import get_workspace_registry_service

            registry = get_workspace_registry_service()
            env_vars = registry.get_workspace_env_vars(user_id, workspace_dir.name)
        except Exception:
            logger.warning("读取工作区环境变量失败", exc_info=True)

    # 读取统一能力声明
    recommended_capabilities: list[CapabilityDeclaration] = []
    try:
        from app.capabilities import get_capability_manager

        mgr = get_capability_manager()
        caps = mgr._read_declarations(workspace_dir)
        for cap_id, cap in caps.items():
            if cap.enabled:
                recommended_capabilities.append(
                    CapabilityDeclaration(
                        capability_id=cap_id,
                        kind=cap.kind,
                        required=True,
                        auto_activate=True,
                        config=cap.config,
                    )
                )
    except Exception:
        logger.warning("读取统一能力声明失败", exc_info=True)

    # 兼容旧格式：从 skills 目录和 mcp_config 读取
    skills_dir = workspace_dir / ".aiasys" / "skills"
    recommended_skills: list[str] = []
    if skills_dir.exists() and skills_dir.is_dir():
        for entry in skills_dir.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                recommended_skills.append(entry.name)

    mcp_path = workspace_dir / ".aiasys" / "mcp_config.json"
    recommended_mcps: list[str] = []
    if mcp_path.exists():
        try:
            mcp_data = json.loads(mcp_path.read_text(encoding="utf-8"))
            servers = mcp_data.get("servers") or {}
            disabled = set(mcp_data.get("disabled_servers") or [])
            recommended_mcps = [srv_name for srv_name in servers if srv_name not in disabled]
        except (json.JSONDecodeError, OSError):
            pass

    # 生成/校验 template_id
    resolved_id = (template_id or "").strip() or _generate_template_id(name)
    if not _is_safe_template_id(resolved_id):
        raise ValueError(f"不安全的模板 ID: {resolved_id}")

    # 构建 template.json
    template_data = {
        "template_id": resolved_id,
        "name": name,
        "description": description,
        "icon": icon,
        "category": category,
        "default_title": meta.get("title") or name,
        "default_description": meta.get("description") or description,
        "initial_conversation_title": "新对话",
        "env_kind": env_kind,
        "files": [
            {
                "relative_path": f.relative_path,
                "content": f.content,
                "source_path": f.source_path,
            }
            for f in template_files
        ],
        "env_vars": env_vars,
        "runtime_resources": runtime_resources.model_dump(mode="json"),
        "recommended_skills": recommended_skills,
        "recommended_mcps": recommended_mcps,
        "recommended_capabilities": [
            {
                "capability_id": d.capability_id,
                "kind": d.kind.value,
                "required": d.required,
                "auto_activate": d.auto_activate,
                "config": d.config,
            }
            for d in recommended_capabilities
        ],
    }

    # 保存到用户全局模板目录
    user_templates_dir = _get_user_templates_dir(user_id)
    target_dir = user_templates_dir / resolved_id
    if target_dir.exists():
        raise ValueError(f"模板已存在: {resolved_id}")
    target_dir.mkdir(parents=True, exist_ok=True)

    # 写入 template.toml
    (target_dir / "template.toml").write_text(
        _dump_template_toml(template_data),
        encoding="utf-8",
    )

    # 复制 workspace_memory.md
    memory_src = workspace_dir / ".aiasys" / "memory" / "workspace_memory.md"
    if memory_src.exists():
        shutil.copy2(memory_src, target_dir / "workspace_memory.md")

    return WorkspaceTemplate(
        template_id=resolved_id,
        name=name,
        description=description,
        icon=icon,
        category=category,
        default_title=template_data["default_title"],
        default_description=template_data["default_description"],
        initial_conversation_title=template_data["initial_conversation_title"],
        env_kind=env_kind,
        files=template_files,
        source_dir=target_dir,
        recommended_skills=recommended_skills,
        recommended_mcps=recommended_mcps,
        recommended_capabilities=recommended_capabilities,
        env_vars=env_vars,
        runtime_resources=runtime_resources,
    )

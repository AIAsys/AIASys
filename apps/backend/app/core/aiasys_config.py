"""
AIASys 用户级 TOML 配置加载器与保存器

配置文件路径: data/workspaces/{user_id}/global_workspace/.aiasys/config.toml

作用域：用户默认层。每个用户在全局工作区目录下有一份独立配置，
与 ~/.aiasys/ 解耦，和用户其他全局资源放在同一目录下管理。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import get_user_global_config_dir

logger = logging.getLogger(__name__)

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None  # type: ignore


class LlmTomlSection(BaseModel):
    """TOML 配置中 [llm] 段"""

    default_model: str = ""
    task_models: dict[str, str] = Field(default_factory=dict)


class CompactionTomlSection(BaseModel):
    """TOML 配置中 [compaction] 段"""

    tool_snip_max_chars: int = 0  # 0 表示未配置，使用 LoopControl 默认值


class MemoryTomlSection(BaseModel):
    """TOML 配置中 [memory] 段"""

    enabled: bool = True  # memory 总开关，false 时关闭所有 memory 功能
    model: str = ""  # memory pipeline 专用模型 ID，空字符串表示复用 default_chat_model
    stage1_max_records: int = 20
    stage1_max_chars: int = 12000
    stage1_summary_tokens: int = 1800
    stage1_retention_days: int = 30
    max_stage1_outputs: int = 128
    stage2_max_input_chars: int = 24000
    stage2_max_tokens: int = 2400
    max_snapshots: int = 50
    max_memory_versions: int = 20
    max_memory_size: int = 10000
    max_summary_size: int = 3000
    max_workspace_memory_size: int = 5000


class UvTomlSection(BaseModel):
    """TOML 配置中 [uv] 段 — uv 安装器镜像配置

    PyPI 包镜像和 Python 二进制镜像由 uv 自身的 ~/.config/uv/config.toml
    和 UV_PYTHON_INSTALL_MIRROR 环境变量处理，不在 AIASys 侧重复配置。
    """

    installer_mirror: str = ""  # uv 安装脚本镜像基 URL（用于替换 astral.sh）


class AiasysTomlConfig(BaseModel):
    """完整的用户级 config.toml 配置模型"""

    llm: LlmTomlSection = Field(default_factory=LlmTomlSection)
    compaction: CompactionTomlSection = Field(default_factory=CompactionTomlSection)
    memory: MemoryTomlSection = Field(default_factory=MemoryTomlSection)
    uv: UvTomlSection = Field(default_factory=UvTomlSection)


def _get_user_config_path(user_id: str) -> Path:
    """获取指定用户的 config.toml 物理路径。"""
    return get_user_global_config_dir(user_id) / "config.toml"


def _get_default_config_template() -> str:
    """返回默认 config.toml 模板内容。"""
    template_path = Path(__file__).with_name("default_config.toml")
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    return ""


def load_aiasys_config(user_id: str | None = None) -> AiasysTomlConfig:
    """加载用户级 config.toml，文件不存在时自动从模板创建。

    Args:
        user_id: 用户 ID。为 None 时返回空配置（不再回退到全局默认）。
    """
    if tomllib is None:
        logger.warning("Python 版本低于 3.11，无法使用 tomllib 读取 TOML 配置")
        return AiasysTomlConfig()

    if not user_id:
        return AiasysTomlConfig()

    config_path = _get_user_config_path(user_id)
    if not config_path.exists():
        template = _get_default_config_template()
        if template:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(template, encoding="utf-8")
            logger.info("为用户 %s 自动创建默认 config.toml", user_id)
        try:
            with config_path.open("rb") as f:
                raw: dict[str, Any] = tomllib.load(f)
            return AiasysTomlConfig.model_validate(raw)
        except Exception as exc:
            logger.warning("首次加载 %s 失败: %s", config_path, exc)
            return AiasysTomlConfig()

    try:
        with config_path.open("rb") as f:
            raw: dict[str, Any] = tomllib.load(f)
        return AiasysTomlConfig.model_validate(raw)
    except Exception as exc:
        logger.warning("加载 %s 失败: %s", config_path, exc)
        return AiasysTomlConfig()


def save_aiasys_task_models(user_id: str, task_models: dict[str, str]) -> None:
    """更新指定用户 config.toml 中的 [llm.task_models] 段。"""
    config_path = _get_user_config_path(user_id)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    existing_lines: list[str] = []
    if config_path.exists():
        existing_lines = config_path.read_text(encoding="utf-8").splitlines()

    # 构建新的 [llm.task_models] 段
    new_section_lines: list[str] = ["[llm.task_models]"]
    if task_models:
        for key, value in sorted(task_models.items()):
            new_section_lines.append(f'{key} = "{value}"')
    else:
        new_section_lines.append("# 未配置任务级模型路由")

    # 查找并替换 [llm.task_models] 段
    result_lines: list[str] = []
    in_task_models_section = False
    section_replaced = False

    for line in existing_lines:
        stripped = line.strip()
        if stripped == "[llm.task_models]":
            in_task_models_section = True
            if not section_replaced:
                result_lines.extend(new_section_lines)
                section_replaced = True
            continue
        if in_task_models_section:
            # 如果下一行是新的 section，退出当前 section
            if stripped.startswith("[") and stripped != "[llm.task_models]":
                in_task_models_section = False
                result_lines.append(line)
            # 否则跳过当前 section 的内容（已替换）
            continue
        result_lines.append(line)

    if not section_replaced:
        # 文件末尾追加
        if result_lines and result_lines[-1].strip():
            result_lines.append("")
        result_lines.extend(new_section_lines)
        result_lines.append("")

    config_path.write_text("\n".join(result_lines) + "\n", encoding="utf-8")


def save_aiasys_uv_config(user_id: str, uv_config: UvTomlSection) -> None:
    """更新指定用户 config.toml 中的 [uv] 段。"""
    config_path = _get_user_config_path(user_id)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    existing_lines: list[str] = []
    if config_path.exists():
        existing_lines = config_path.read_text(encoding="utf-8").splitlines()

    new_section_lines: list[str] = ["[uv]"]
    if uv_config.installer_mirror:
        new_section_lines.append(f'installer_mirror = "{uv_config.installer_mirror}"')
    else:
        new_section_lines.append("# installer_mirror = \"\"")

    result_lines: list[str] = []
    in_uv_section = False
    section_replaced = False

    for line in existing_lines:
        stripped = line.strip()
        if stripped == "[uv]":
            in_uv_section = True
            if not section_replaced:
                result_lines.extend(new_section_lines)
                section_replaced = True
            continue
        if in_uv_section:
            if stripped.startswith("[") and stripped != "[uv]":
                in_uv_section = False
                result_lines.append(line)
            continue
        result_lines.append(line)

    if not section_replaced:
        if result_lines and result_lines[-1].strip():
            result_lines.append("")
        result_lines.extend(new_section_lines)
        result_lines.append("")

    config_path.write_text("\n".join(result_lines) + "\n", encoding="utf-8")

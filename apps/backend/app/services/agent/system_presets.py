from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.runtime_tooling import (
    NATIVE_AGENT_TOOL_PATH,
    NATIVE_TASK_TOOL_PATH,
    READ_MEDIA_TOOL_PATH,
    canonicalize_runtime_tool_name,
)

logger = logging.getLogger(__name__)

AGENTS_ROOT = Path(__file__).resolve().parents[2] / "agents"
LOCAL_CONFIG_DIR = AGENTS_ROOT / "local_sandbox_agent_config"
LOCAL_PRESET_SUFFIX = ".preset"
GET_ENV_VAR_TOOL_PATH = "app.agents.tools.env_vars_tool:GetEnvVar"
SET_ENV_VAR_TOOL_PATH = "app.agents.tools.env_vars_tool:SetEnvVar"
DELETE_ENV_VAR_TOOL_PATH = "app.agents.tools.env_vars_tool:DeleteEnvVar"
RUNTIME_ENVIRONMENT_TOOL_PATH = "app.agents.tools.runtime_environment_tool:RuntimeEnvironment"
NOTEBOOK_LIST_TOOL_PATHS: tuple[str, ...] = (
    "app.agents.tools.notebook_session_tool:ListSessionNotebooks",
)
NOTEBOOK_READ_ONLY_TOOL_PATHS: tuple[str, ...] = (
    *NOTEBOOK_LIST_TOOL_PATHS,
    "app.agents.tools.notebook_file_tool:ReadNotebook",
    "app.agents.tools.notebook_session_tool:ReadNotebookOutputs",
)
SESSION_TASK_PLAN_TOOL_PATHS: tuple[str, ...] = (
    "app.agents.tools.task_plan_tools:TaskCreateTool",
    "app.agents.tools.task_plan_tools:TaskUpdateTool",
    "app.agents.tools.task_plan_tools:TaskListTool",
    "app.agents.tools.task_plan_tools:SetTodoList",
    "app.agents.tools.task_plan_tools:EnterPlanModeTool",
    "app.agents.tools.task_plan_tools:ExitPlanModeTool",
)
AUTO_TASK_TOOL_PATHS: tuple[str, ...] = (
    "app.agents.tools.auto_task_signal_tool:AutoTaskSignal",
    "app.agents.tools.auto_task_tool:CreateAutoTask",
    "app.agents.tools.auto_task_tool:ListAutoTasks",
    "app.agents.tools.auto_task_tool:UpdateAutoTask",
    "app.agents.tools.auto_task_tool:ControlAutoTask",
)
KNOWLEDGE_GRAPH_TOOL_PATHS: tuple[str, ...] = (
    "app.agents.tools.graphrag_tool:SearchKnowledgeGraphEntities",
    "app.agents.tools.graphrag_tool:GetKnowledgeGraphEntityDetail",
    "app.agents.tools.graphrag_tool:ListKnowledgeGraphs",
    "app.agents.tools.graphrag_tool:CreateKnowledgeGraph",
    "app.agents.tools.graphrag_tool:DeleteKnowledgeGraph",
    "app.agents.tools.graphrag_tool:CreateGraphEntity",
    "app.agents.tools.graphrag_tool:UpdateGraphEntity",
    "app.agents.tools.graphrag_tool:DeleteGraphEntity",
    "app.agents.tools.graphrag_tool:CreateGraphRelation",
    "app.agents.tools.graphrag_tool:QueryEntityRelations",
    "app.agents.tools.graphrag_tool:GetCommunityReport",
    "app.agents.tools.graphrag_tool:UploadDocumentsToGraph",
)
KNOWLEDGE_GRAPH_READ_TOOL_PATHS: tuple[str, ...] = (
    "app.agents.tools.graphrag_tool:SearchKnowledgeGraphEntities",
    "app.agents.tools.graphrag_tool:GetKnowledgeGraphEntityDetail",
    "app.agents.tools.graphrag_tool:ListKnowledgeGraphs",
)
KNOWLEDGE_BASE_TOOL_PATHS: tuple[str, ...] = (
    "app.agents.tools.knowledge_tool:KnowledgeBaseQuery",
    "app.agents.tools.knowledge_tool:ListKnowledgeBases",
    "app.agents.tools.knowledge_tool:CreateKnowledgeBase",
    "app.agents.tools.knowledge_tool:UpdateKnowledgeBase",
    "app.agents.tools.knowledge_tool:UploadDocumentsToKnowledgeBase",
    "app.agents.tools.knowledge_tool:ListKnowledgeBaseDocuments",
    "app.agents.tools.knowledge_tool:DeleteDocumentsFromKnowledgeBase",
    "app.agents.tools.knowledge_tool:DeleteKnowledgeBase",
)
KNOWLEDGE_BASE_READ_TOOL_PATHS: tuple[str, ...] = (
    "app.agents.tools.knowledge_tool:KnowledgeBaseQuery",
    "app.agents.tools.knowledge_tool:ListKnowledgeBases",
    "app.agents.tools.knowledge_tool:ListKnowledgeBaseDocuments",
)
DATA_TABLE_TOOL_PATHS: tuple[str, ...] = (
    "app.agents.tools.data_table_tool:CreateDataTable",
    "app.agents.tools.data_table_tool:ReadDataTableSchema",
    "app.agents.tools.data_table_tool:QueryDataTable",
    "app.agents.tools.data_table_tool:InsertDataTableRecords",
    "app.agents.tools.data_table_tool:UpdateDataTableRecord",
    "app.agents.tools.data_table_tool:DeleteDataTableRecord",
    "app.agents.tools.data_table_tool:AddDataTableColumn",
    "app.agents.tools.data_table_tool:UpdateDataTableColumn",
    "app.agents.tools.data_table_tool:RemoveDataTableColumn",
)
CANVAS_TOOL_PATHS: tuple[str, ...] = (
    "app.agents.tools.canvas_tool:ReadCanvas",
    "app.agents.tools.canvas_tool:WriteCanvas",
    "app.agents.tools.canvas_tool:BatchCanvasOperations",
)


def get_local_system_preset_virtual_path(profile_basename: str) -> Path:
    """返回 local system preset 的虚拟路径标识，不依赖物理 YAML 文件存在。"""
    return LOCAL_CONFIG_DIR / f"{profile_basename}{LOCAL_PRESET_SUFFIX}"


def _canonical_tool_names(items: list[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        canonical_name = canonicalize_runtime_tool_name(text)
        if canonical_name in seen:
            continue
        normalized.append(canonical_name)
        seen.add(canonical_name)
    return tuple(normalized)


def _string_list(items: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized


# 子 Agent 运行时工具映射表（按角色类型自动分配工具集）
_ROLE_TYPE_TOOL_MAP: dict[str, tuple[str, ...]] = {
    "worker": _canonical_tool_names(
        [
            READ_MEDIA_TOOL_PATH,
            *NOTEBOOK_READ_ONLY_TOOL_PATHS,
            "app.agents.tools.code_execution_tool:RunCode",
            "app.agents.tools.code_execution_tool:ListKernelEnvsTool",
            "app.agents.tools.code_execution_tool:RegisterKernelEnvTool",
            "app.agents.tools.code_execution_tool:RemoveKernelEnvTool",
            GET_ENV_VAR_TOOL_PATH,
            SET_ENV_VAR_TOOL_PATH,
            DELETE_ENV_VAR_TOOL_PATH,
            # 知识图谱工具
            *KNOWLEDGE_GRAPH_TOOL_PATHS,
            # 知识库工具
            *KNOWLEDGE_BASE_TOOL_PATHS,
            *DATA_TABLE_TOOL_PATHS,
            *CANVAS_TOOL_PATHS,
            "app.agents.tools.skill_tools:ListSkills",
            "app.agents.tools.skill_tools:LoadSkill",
            "app.agents.tools.skill_tools:SearchStoreSkills",
            "app.agents.tools.skill_tools:EnableSkill",
            "app.agents.tools.skill_tools:DisableSkill",
        ]
    ),
    "coder": _canonical_tool_names(
        [
            READ_MEDIA_TOOL_PATH,
            *NOTEBOOK_READ_ONLY_TOOL_PATHS,
            "app.agents.tools.code_execution_tool:RunCode",
            "app.agents.tools.code_execution_tool:ListKernelEnvsTool",
            "app.agents.tools.code_execution_tool:RegisterKernelEnvTool",
            "app.agents.tools.code_execution_tool:RemoveKernelEnvTool",
            "app.agents.tools.file_tools:ReadFile",
            "app.agents.tools.file_tools:WriteFile",
            "app.agents.tools.file_tools:StrReplaceFile",
            GET_ENV_VAR_TOOL_PATH,
            SET_ENV_VAR_TOOL_PATH,
            DELETE_ENV_VAR_TOOL_PATH,
            "app.agents.tools.shell_tool:Shell",
            "app.agents.tools.skill_tools:ListSkills",
            "app.agents.tools.skill_tools:LoadSkill",
            "app.agents.tools.skill_tools:SearchStoreSkills",
            "app.agents.tools.skill_tools:EnableSkill",
            "app.agents.tools.skill_tools:DisableSkill",
        ]
    ),
    "researcher": _canonical_tool_names(
        [
            READ_MEDIA_TOOL_PATH,
            *NOTEBOOK_READ_ONLY_TOOL_PATHS,
            "app.agents.tools.file_tools:ReadFile",
            *KNOWLEDGE_BASE_READ_TOOL_PATHS,
            *KNOWLEDGE_GRAPH_READ_TOOL_PATHS,
            "app.agents.tools.skill_tools:ListSkills",
            "app.agents.tools.skill_tools:LoadSkill",
            "app.agents.tools.skill_tools:SearchStoreSkills",
        ]
    ),
    "reviewer": _canonical_tool_names(
        [
            READ_MEDIA_TOOL_PATH,
            *NOTEBOOK_READ_ONLY_TOOL_PATHS,
            "app.agents.tools.file_tools:ReadFile",
            *KNOWLEDGE_BASE_READ_TOOL_PATHS,
            "app.agents.tools.skill_tools:ListSkills",
            "app.agents.tools.skill_tools:LoadSkill",
            "app.agents.tools.skill_tools:SearchStoreSkills",
        ]
    ),
    "data_analyst": _canonical_tool_names(
        [
            READ_MEDIA_TOOL_PATH,
            *NOTEBOOK_READ_ONLY_TOOL_PATHS,
            "app.agents.tools.notebook_tool:ManageNotebook",
            "app.agents.tools.code_execution_tool:RunCode",
            "app.agents.tools.code_execution_tool:ListKernelEnvsTool",
            "app.agents.tools.code_execution_tool:RegisterKernelEnvTool",
            "app.agents.tools.code_execution_tool:RemoveKernelEnvTool",
            "app.agents.tools.file_tools:ReadFile",
            "app.agents.tools.file_tools:WriteFile",
            "app.agents.tools.file_tools:StrReplaceFile",
            GET_ENV_VAR_TOOL_PATH,
            SET_ENV_VAR_TOOL_PATH,
            DELETE_ENV_VAR_TOOL_PATH,
            RUNTIME_ENVIRONMENT_TOOL_PATH,
            "app.agents.tools.shell_tool:Shell",
            # 知识图谱工具
            *KNOWLEDGE_GRAPH_TOOL_PATHS,
            # 知识库工具
            *KNOWLEDGE_BASE_TOOL_PATHS,
            # 多维表和 Canvas 工具
            *DATA_TABLE_TOOL_PATHS,
            *CANVAS_TOOL_PATHS,
            # Skill 工具
            "app.agents.tools.skill_tools:ListSkills",
            "app.agents.tools.skill_tools:LoadSkill",
            "app.agents.tools.skill_tools:SearchStoreSkills",
            "app.agents.tools.skill_tools:EnableSkill",
            "app.agents.tools.skill_tools:DisableSkill",
            # MCP 工具
            "app.agents.tools.mcp_tools:ListMCPServers",
            "app.agents.tools.mcp_tools:SearchMCPMarket",
            "app.agents.tools.mcp_tools:InstallMCPServer",
            # 数据库工具
            "app.agents.tools.database_query_tool:DatabaseQuery",
            "app.agents.tools.database_query_tool:ListDatabaseConnectors",
            "app.agents.tools.database_query_tool:ListDatabaseTables",
            "app.agents.tools.database_query_tool:DescribeDatabaseTable",
        ]
    ),
}

# 所有子 Agent 统一排除的工具（一级禁用）
_SUBAGENT_UNIVERSAL_EXCLUDES: tuple[str, ...] = _canonical_tool_names(
    [
        NATIVE_TASK_TOOL_PATH,
        NATIVE_AGENT_TOOL_PATH,
        "app.agents.tools.ask_user.tool:AskUser",
        *SESSION_TASK_PLAN_TOOL_PATHS,
        "app.services.agent.runtime_backends.aiasys.tools.monitor_tool:SpawnMonitorTool",
        "app.services.agent.runtime_backends.aiasys.tools.monitor_tool:ManageMonitorTool",
    ]
)


def get_role_type_default_tools(role_type: str) -> tuple[str, ...]:
    """根据角色类型获取默认工具集。"""
    return _ROLE_TYPE_TOOL_MAP.get(role_type, ())


def get_subagent_universal_excludes() -> tuple[str, ...]:
    """获取所有子 Agent 统一排除的工具列表。"""
    return _SUBAGENT_UNIVERSAL_EXCLUDES


@dataclass(frozen=True, slots=True)
class SystemSubagentBinding:
    baseline_id: str
    description: str


@dataclass(frozen=True, slots=True)
class SystemAgentBaseline:
    baseline_id: str
    label: str
    agent_name: str
    model: str | None
    prompt_template_path: Path
    # 工具策略: inherit | allowlist | denylist | none
    # 注：子 Agent 的 tools/allowed_tools/exclude_tools 不再硬编码，
    # 由运行时通过 _ROLE_TYPE_TOOL_MAP 动态注入。
    # 主控 baseline 仍可通过 tools 字段声明工具列表。
    tools: tuple[str, ...] = ()
    tool_policy: str | None = None
    allowed_tools: tuple[str, ...] = ()
    exclude_tools: tuple[str, ...] = ()
    # MCP 继承策略: inherit | allowlist | denylist | none
    mcp_policy: str | None = None
    mcp_servers: tuple[str, ...] = ()
    # Skill 继承策略: inherit | allowlist | denylist | none
    skill_policy: str | None = None
    skills: tuple[str, ...] = ()
    when_to_use: str | None = None
    expert_profile: dict[str, Any] | None = None
    subagents: dict[str, SystemSubagentBinding] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResolvedSystemPreset:
    sandbox_mode: str
    profile_basename: str
    config_ref: str
    baseline: SystemAgentBaseline
    subagent_baselines: dict[str, SystemAgentBaseline]


DATA_ANALYST_BASELINE = SystemAgentBaseline(
    baseline_id="data_analyst",
    label="数据分析专家",
    agent_name="aiasys_local_data_analyst",
    model=None,
    when_to_use="当任务需要执行数据分析、代码实验、Python 脚本运行、notebook 操作、数据可视化或数据库查询时使用。",
    prompt_template_path=LOCAL_CONFIG_DIR / "subagent_data_analyst_prompt.md",
    tool_policy="allowlist",
    mcp_policy="inherit",
    skill_policy="inherit",
    skills=(
        "aiasys-notebook-first-skill",
        "aiasys-data-viz-guide-skill",
        "aiasys-data-tools-guide-skill",
    ),
    expert_profile={
        "display_name": "数据分析专家",
        "description": "负责执行数据分析、代码实验、notebook 操作、数据可视化和数据库查询的专业协作节点。",
        "permissions": _string_list(
            ["file_write", "shell", "python", "notebook", "knowledge", "memory", "database"]
        ),
        "capabilities": _string_list(
            [
                "数据分析",
                "代码实验",
                "notebook 操作",
                "数据可视化",
                "数据库查询",
                "知识检索",
                "图谱检索",
            ]
        ),
        "supports_background": True,
    },
)

CODER_BASELINE = SystemAgentBaseline(
    baseline_id="coder",
    label="代码专家",
    agent_name="aiasys_local_coder",
    model=None,
    when_to_use="当任务需要在主控明确授权范围内实现、修改、调试代码，运行构建或测试，并回传可复核结果时使用；不负责 notebook 写入和运行。",
    prompt_template_path=LOCAL_CONFIG_DIR / "subagent_coder_prompt.md",
    tool_policy="allowlist",
    mcp_policy="none",
    skill_policy="inherit",
    expert_profile={
        "display_name": "代码专家",
        "description": "专注在主控授权范围内实现、修改、调试代码并运行验证，可只读回看 notebook 输出。",
        "permissions": _string_list(["file_write", "shell", "python", "notebook_read"]),
        "capabilities": _string_list(
            ["代码实现", "代码调试", "最小修改", "构建测试", "notebook 输出回看"]
        ),
        "supports_background": True,
    },
)

RESEARCHER_BASELINE = SystemAgentBaseline(
    baseline_id="researcher",
    label="研究专家",
    agent_name="aiasys_local_researcher",
    model=None,
    when_to_use="当任务需要检索资料、阅读文档、提炼证据、回看 notebook 输出并给主控提供研究结论时使用。",
    prompt_template_path=LOCAL_CONFIG_DIR / "subagent_researcher_prompt.md",
    tool_policy="allowlist",
    mcp_policy="inherit",
    skill_policy="inherit",
    expert_profile={
        "display_name": "研究专家",
        "description": "专注检索资料、阅读文档、回看 notebook 输出、提炼证据并向主控回传研究结论。",
        "permissions": _string_list(["read_only", "web", "knowledge", "notebook_read"]),
        "capabilities": _string_list(["联网检索", "资料阅读", "证据归纳", "notebook 输出回看"]),
        "supports_background": True,
    },
)

REVIEWER_BASELINE = SystemAgentBaseline(
    baseline_id="reviewer",
    label="审查专家",
    agent_name="aiasys_local_reviewer",
    model=None,
    when_to_use="当任务需要核对结果、比对差异、回看 notebook 输出、做质量审查或输出风险结论时使用。",
    prompt_template_path=LOCAL_CONFIG_DIR / "subagent_reviewer_prompt.md",
    tool_policy="allowlist",
    mcp_policy="none",
    skill_policy="inherit",
    expert_profile={
        "display_name": "审查专家",
        "description": "专注核对结果、比对差异、回看 notebook 输出、归纳风险并给主控清晰结论。",
        "permissions": _string_list(["read_only", "web", "notebook_read"]),
        "capabilities": _string_list(["结果审查", "差异比对", "风险归纳", "证据回看"]),
        "supports_background": True,
    },
)

DATA_ANALYSIS_BASELINE = SystemAgentBaseline(
    baseline_id="data_analysis",
    label="通用主控",
    agent_name="aiasys_local_host",
    model=None,
    prompt_template_path=LOCAL_CONFIG_DIR / "general_host_prompt.md",
    tools=_canonical_tool_names(
        [
            NATIVE_TASK_TOOL_PATH,
            READ_MEDIA_TOOL_PATH,
            "app.agents.tools.notebook_session_tool:ListSessionNotebooks",
            "app.agents.tools.notebook_tool:ManageNotebook",
            "app.agents.tools.code_execution_tool:RunCode",
            "app.agents.tools.code_execution_tool:ListKernelEnvsTool",
            "app.agents.tools.code_execution_tool:RegisterKernelEnvTool",
            "app.agents.tools.code_execution_tool:RemoveKernelEnvTool",
            "app.agents.tools.ask_user.tool:AskUser",
            *SESSION_TASK_PLAN_TOOL_PATHS,
            *AUTO_TASK_TOOL_PATHS,
            *KNOWLEDGE_GRAPH_TOOL_PATHS,
            # 知识库工具
            *KNOWLEDGE_BASE_TOOL_PATHS,
            *DATA_TABLE_TOOL_PATHS,
            *CANVAS_TOOL_PATHS,
            "app.agents.tools.file_tools:ReadFile",
            "app.agents.tools.file_tools:WriteFile",
            "app.agents.tools.file_tools:StrReplaceFile",
            GET_ENV_VAR_TOOL_PATH,
            SET_ENV_VAR_TOOL_PATH,
            DELETE_ENV_VAR_TOOL_PATH,
            RUNTIME_ENVIRONMENT_TOOL_PATH,
            "app.agents.tools.shell_tool:Shell",
            "app.agents.tools.skill_tools:ListSkills",
            "app.agents.tools.skill_tools:LoadSkill",
            "app.agents.tools.skill_tools:SearchStoreSkills",
            "app.agents.tools.skill_tools:EnableSkill",
            "app.agents.tools.skill_tools:DisableSkill",
            "app.agents.tools.expert_tools:ListSystemExperts",
            "app.agents.tools.expert_tools:InstallExpert",
            "app.agents.tools.expert_tools:ConfigureExpert",
            "app.agents.tools.mcp_tools:ListMCPServers",
            "app.agents.tools.mcp_tools:SearchMCPMarket",
            "app.agents.tools.mcp_tools:InstallMCPServer",
            "app.agents.tools.database_query_tool:DatabaseQuery",
            "app.agents.tools.database_query_tool:ListDatabaseConnectors",
            "app.agents.tools.database_query_tool:ListDatabaseTables",
            "app.agents.tools.database_query_tool:DescribeDatabaseTable",
        ]
    ),
    skill_policy="inherit",
    skills=(
        "aiasys-markdown-output-guide-skill",
        "aiasys-hosting-guide-skill",
    ),
    subagents={
        "data_analyst": SystemSubagentBinding(
            baseline_id=DATA_ANALYST_BASELINE.baseline_id,
            description="数据分析专家，负责执行数据分析、代码实验、notebook 操作、数据可视化和数据库查询",
        ),
        "coder": SystemSubagentBinding(
            baseline_id=CODER_BASELINE.baseline_id,
            description="代码专家，专注在主控授权范围内实现、修改、调试代码并运行验证",
        ),
        "researcher": SystemSubagentBinding(
            baseline_id=RESEARCHER_BASELINE.baseline_id,
            description="研究专家，专注检索资料、阅读文档、回看 notebook 输出和整理证据",
        ),
        "reviewer": SystemSubagentBinding(
            baseline_id=REVIEWER_BASELINE.baseline_id,
            description="审查专家，专注核对结果、比对差异、回看 notebook 输出和输出结论",
        ),
    },
)

_LOCAL_BASELINES: dict[str, SystemAgentBaseline] = {
    DATA_ANALYSIS_BASELINE.baseline_id: DATA_ANALYSIS_BASELINE,
    DATA_ANALYST_BASELINE.baseline_id: DATA_ANALYST_BASELINE,
    CODER_BASELINE.baseline_id: CODER_BASELINE,
    RESEARCHER_BASELINE.baseline_id: RESEARCHER_BASELINE,
    REVIEWER_BASELINE.baseline_id: REVIEWER_BASELINE,
}

_LOCAL_PROFILE_TO_BASELINE_ID: dict[str, str] = {
    "data_analysis": DATA_ANALYSIS_BASELINE.baseline_id,
}

_LOCAL_CONFIG_PATH_TO_BASELINE_ID: dict[str, str] = {
    "data_analysis.preset": DATA_ANALYSIS_BASELINE.baseline_id,
}


def resolve_system_agent_preset(
    *,
    profile_basename: str,
    sandbox_mode: str | None,
) -> ResolvedSystemPreset:
    effective_sandbox_mode = str(sandbox_mode or "local").strip().lower() or "local"
    if effective_sandbox_mode != "local":
        logger.warning(
            "结构化 system preset 目前仅内建 local，sandbox_mode=%s 回退到 local",
            effective_sandbox_mode,
        )
        effective_sandbox_mode = "local"

    baseline_id = _LOCAL_PROFILE_TO_BASELINE_ID.get(profile_basename)
    if baseline_id is None:
        raise KeyError(f"未知 system preset profile: {profile_basename}")
    baseline = _LOCAL_BASELINES[baseline_id]
    referenced_baselines = {
        binding.baseline_id: _LOCAL_BASELINES[binding.baseline_id]
        for binding in baseline.subagents.values()
    }
    return ResolvedSystemPreset(
        sandbox_mode=effective_sandbox_mode,
        profile_basename=profile_basename,
        config_ref=f"preset://{effective_sandbox_mode}/{baseline_id}",
        baseline=baseline,
        subagent_baselines=referenced_baselines,
    )


def resolve_system_agent_preset_from_path(config_path: Path) -> ResolvedSystemPreset | None:
    if config_path.parent.name != LOCAL_CONFIG_DIR.name:
        return None
    baseline_id = _LOCAL_CONFIG_PATH_TO_BASELINE_ID.get(config_path.name)
    if baseline_id is None:
        return None
    profile_basename = next(
        (
            profile_name
            for profile_name, candidate_baseline_id in _LOCAL_PROFILE_TO_BASELINE_ID.items()
            if candidate_baseline_id == baseline_id
        ),
        None,
    )
    if profile_basename is None:
        return None
    return resolve_system_agent_preset(profile_basename=profile_basename, sandbox_mode="local")


def build_system_config_from_preset(preset: ResolvedSystemPreset) -> dict[str, Any]:
    baseline = preset.baseline
    agent_config: dict[str, Any] = {
        "name": baseline.agent_name,
        "model": baseline.model,
        "tools": list(baseline.tools),
        "system_prompt_path": str(baseline.prompt_template_path.resolve()),
    }
    if baseline.skill_policy:
        agent_config["skill_policy"] = baseline.skill_policy
    if baseline.skills:
        agent_config["skills"] = list(baseline.skills)
    return {
        "agent": agent_config,
        "system_preset_ref": preset.config_ref,
    }


_BUILTIN_SUBAGENT_SEEDS: dict[str, SystemAgentBaseline] = {
    "data_analyst": DATA_ANALYST_BASELINE,
    "coder": CODER_BASELINE,
    "researcher": RESEARCHER_BASELINE,
    "reviewer": REVIEWER_BASELINE,
}


def get_builtin_subagent_seed(name: str) -> SystemAgentBaseline | None:
    return _BUILTIN_SUBAGENT_SEEDS.get(name)


def list_builtin_subagent_names() -> list[str]:
    return list(_BUILTIN_SUBAGENT_SEEDS.keys())


def build_subagent_manifest_from_seed(name: str) -> dict[str, Any] | None:
    baseline = _BUILTIN_SUBAGENT_SEEDS.get(name)
    if baseline is None:
        return None
    manifest: dict[str, Any] = {
        "name": name,
        "description": (
            baseline.expert_profile.get("description", "") if baseline.expert_profile else ""
        ),
    }
    try:
        prompt_text = baseline.prompt_template_path.read_text(encoding="utf-8")
        manifest["system_prompt"] = prompt_text
    except Exception:
        manifest["system_prompt"] = ""
    if baseline.model:
        manifest["model"] = baseline.model
    if baseline.tool_policy:
        manifest["tool_policy"] = baseline.tool_policy
    # 工具集不再从 baseline 硬编码读取，由运行时通过 _ROLE_TYPE_TOOL_MAP 动态注入
    if baseline.mcp_policy:
        manifest["mcp_policy"] = baseline.mcp_policy
    if baseline.mcp_servers:
        manifest["mcp_servers"] = list(baseline.mcp_servers)
    if baseline.skill_policy:
        manifest["skill_policy"] = baseline.skill_policy
    if baseline.skills:
        manifest["skills"] = list(baseline.skills)
    if baseline.expert_profile:
        manifest["expert_profile"] = baseline.expert_profile
    if baseline.when_to_use:
        manifest["when_to_use"] = baseline.when_to_use
    return manifest


def compute_expert_catalog_fingerprint_from_preset(preset: ResolvedSystemPreset) -> str:
    roles_payload: list[dict[str, Any]] = []
    for role_id, binding in sorted(preset.baseline.subagents.items()):
        baseline = preset.subagent_baselines[binding.baseline_id]
        expert_profile = baseline.expert_profile or {}
        effective_tools = list(get_role_type_default_tools(role_id))
        prompt_sha256 = (
            hashlib.sha256(baseline.prompt_template_path.read_bytes()).hexdigest()
            if baseline.prompt_template_path.exists()
            else None
        )
        roles_payload.append(
            {
                "role_id": role_id,
                "baseline_id": baseline.baseline_id,
                "display_name": expert_profile.get("display_name"),
                "description": expert_profile.get("description") or binding.description,
                "when_to_use": baseline.when_to_use,
                "default_model": baseline.model,
                "tool_names": [tool_name.split(":")[-1] for tool_name in effective_tools],
                "permissions": expert_profile.get("permissions") or [],
                "capabilities": expert_profile.get("capabilities") or [],
                "supports_background": expert_profile.get("supports_background", True),
                "mcp_policy": baseline.mcp_policy,
                "skill_policy": baseline.skill_policy,
                "prompt_sha256": prompt_sha256,
            }
        )
    return hashlib.sha256(
        json.dumps(
            {
                "preset_ref": preset.config_ref,
                "roles": roles_payload,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]

"""能力注册表静态数据目录。

这里维护工具元数据、功能分类和系统集成目录。
"""

from __future__ import annotations

import os
from typing import Any, Iterable

from app.models.capability import CapabilityKind
from app.services.runtime_tooling import (
    NATIVE_AGENT_TOOL_PATH,
    NATIVE_CREATE_SUBAGENT_TOOL_PATH,
    NATIVE_TASK_TOOL_PATH,
    READ_MEDIA_TOOL_PATH,
)

_TOOL_METADATA: dict[str, dict[str, Any]] = {
    NATIVE_TASK_TOOL_PATH: {
        "capability_id": "native.multiagent_task",
        "display_name": "Task",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "AIASys 原生子任务委派工具。",
    },
    NATIVE_AGENT_TOOL_PATH: {
        "capability_id": "native.multiagent_task",
        "display_name": "Task",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "AIASys 原生子任务委派工具（Agent 命名兼容入口）。",
    },
    "app.agents.tools.notebook_file_tool:ReadNotebook": {
        "capability_id": "runtime.read_notebook",
        "display_name": "Read Notebook",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "按 notebook / cell 语义读取逻辑工作区中的 .ipynb 文件。",
    },
    "app.agents.tools.notebook_file_tool:EditNotebookFile": {
        "capability_id": "runtime.edit_notebook",
        "display_name": "Edit Notebook",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "按 notebook / cell 语义编辑逻辑工作区中的 .ipynb 文件。",
    },
    "app.agents.tools.notebook_session_tool:ListSessionNotebooks": {
        "capability_id": "runtime.list_session_notebooks",
        "display_name": "List Session Notebooks",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "列出当前会话私有 notebook，帮助 Agent 决定复用还是新建。",
    },
    "app.agents.tools.notebook_session_tool:CreateSessionNotebook": {
        "capability_id": "runtime.create_session_notebook",
        "display_name": "Create Session Notebook",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "在当前会话私有目录中创建 scratch notebook 或实验 notebook。",
    },
    "app.agents.tools.notebook_session_tool:ReadNotebookOutputs": {
        "capability_id": "runtime.read_notebook_outputs",
        "display_name": "Read Notebook Outputs",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "按 notebook 语义回看当前会话私有 notebook 的安全输出摘要。",
    },
    "app.agents.tools.notebook_tool:ManageNotebook": {
        "capability_id": "runtime.manage_notebook",
        "display_name": "Manage Notebook",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "统一入口管理 notebook 生命周期：创建、读取输出摘要、执行。",
    },
    "app.agents.tools.code_execution_tool:RunCode": {
        "capability_id": "runtime.run_code",
        "display_name": "Run Code",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "轻量 Python 代码执行，适合快速计算验证，无需 notebook 文件。",
    },
    "app.agents.tools.code_execution_tool:ListKernelEnvs": {
        "capability_id": "runtime.list_kernel_envs",
        "display_name": "List Kernel Envs",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "列出当前系统中可用的 IPython kernel 环境，帮助 Agent 在执行代码前确认可用环境。",
    },
    "app.agents.tools.code_execution_tool:RegisterKernelEnv": {
        "capability_id": "runtime.register_kernel_env",
        "display_name": "Register Kernel Env",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "注册新的 Python kernel 环境，指定名称和 Python 可执行文件路径。",
    },
    "app.agents.tools.code_execution_tool:RemoveKernelEnv": {
        "capability_id": "runtime.remove_kernel_env",
        "display_name": "Remove Kernel Env",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "删除已注册的 Python kernel 环境（python3 受保护不可删）。",
    },
    "app.agents.tools.ask_user.tool:AskUser": {
        "capability_id": "runtime.ask_user",
        "display_name": "AskUser",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "需要用户确认时的宿主交互 helper。",
    },
    READ_MEDIA_TOOL_PATH: {
        "capability_id": "native.read_media_file",
        "display_name": "ReadMediaFile",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "媒体与多模态文件读取工具。",
    },
    # ---- 知识库工具 ----
    "app.agents.tools.knowledge_tool:KnowledgeBaseQuery": {
        "capability_id": "native.knowledge_query",
        "display_name": "Knowledge Query",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "知识库查询工具。",
    },
    "app.agents.tools.knowledge_tool:ListKnowledgeBases": {
        "capability_id": "native.knowledge_bases",
        "display_name": "List Knowledge Bases",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "知识库列表工具。",
    },
    "app.agents.tools.knowledge_tool:CreateKnowledgeBase": {
        "capability_id": "native.create_knowledge_base",
        "display_name": "Create Knowledge Base",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "创建当前用户知识库。",
    },
    "app.agents.tools.knowledge_tool:UpdateKnowledgeBase": {
        "capability_id": "native.update_knowledge_base",
        "display_name": "Update Knowledge Base",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "更新当前用户知识库配置。",
    },
    "app.agents.tools.knowledge_tool:UploadDocumentsToKnowledgeBase": {
        "capability_id": "native.upload_knowledge_base_documents",
        "display_name": "Upload Knowledge Base Documents",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "把当前工作区或会话目录中的文件上传到知识库。",
    },
    "app.agents.tools.knowledge_tool:ListKnowledgeBaseDocuments": {
        "capability_id": "native.list_knowledge_base_documents",
        "display_name": "List Knowledge Base Documents",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "列出知识库中的文档。",
    },
    "app.agents.tools.knowledge_tool:DeleteDocumentsFromKnowledgeBase": {
        "capability_id": "native.delete_knowledge_base_documents",
        "display_name": "Delete Knowledge Base Documents",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "从知识库删除一个或多个文档。",
    },
    "app.agents.tools.knowledge_tool:DeleteKnowledgeBase": {
        "capability_id": "native.delete_knowledge_base",
        "display_name": "Delete Knowledge Base",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "删除当前用户知识库。",
    },
    # ---- 知识图谱工具 ----
    "app.agents.tools.graphrag_tool:SearchKnowledgeGraphEntities": {
        "capability_id": "native.graphrag_entity_search",
        "display_name": "Graph Entity Search",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "GraphRAG 实体搜索工具。",
    },
    "app.agents.tools.graphrag_tool:GetKnowledgeGraphEntityDetail": {
        "capability_id": "native.graphrag_entity_detail",
        "display_name": "Graph Entity Detail",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "GraphRAG 实体详情工具。",
    },
    "app.agents.tools.graphrag_tool:ListKnowledgeGraphs": {
        "capability_id": "native.list_knowledge_graphs",
        "display_name": "List Knowledge Graphs",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "列出知识图谱工具。",
    },
    "app.agents.tools.graphrag_tool:CreateKnowledgeGraph": {
        "capability_id": "native.create_knowledge_graph",
        "display_name": "Create Knowledge Graph",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "创建知识图谱工具。",
    },
    "app.agents.tools.graphrag_tool:DeleteKnowledgeGraph": {
        "capability_id": "native.delete_knowledge_graph",
        "display_name": "Delete Knowledge Graph",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "删除知识图谱工具。",
    },
    "app.agents.tools.graphrag_tool:CreateGraphEntity": {
        "capability_id": "native.create_graph_entity",
        "display_name": "Create Graph Entity",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "创建知识图谱实体工具。",
    },
    "app.agents.tools.graphrag_tool:UpdateGraphEntity": {
        "capability_id": "native.update_graph_entity",
        "display_name": "Update Graph Entity",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "更新知识图谱实体工具。",
    },
    "app.agents.tools.graphrag_tool:DeleteGraphEntity": {
        "capability_id": "native.delete_graph_entity",
        "display_name": "Delete Graph Entity",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "删除知识图谱实体工具。",
    },
    "app.agents.tools.graphrag_tool:CreateGraphRelation": {
        "capability_id": "native.create_graph_relation",
        "display_name": "Create Graph Relation",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "创建知识图谱关系工具。",
    },
    "app.agents.tools.graphrag_tool:QueryEntityRelations": {
        "capability_id": "native.graphrag_entity_relations",
        "display_name": "Graph Entity Relations",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "GraphRAG 实体关系查询工具。",
    },
    "app.agents.tools.graphrag_tool:GetCommunityReport": {
        "capability_id": "native.graphrag_community_report",
        "display_name": "Graph Community Report",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "GraphRAG 社区报告工具。",
    },
    "app.agents.tools.graphrag_tool:UploadDocumentsToGraph": {
        "capability_id": "native.graphrag_document_upload",
        "display_name": "Upload Documents To Graph",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "GraphRAG 文档上传构图工具。",
    },
    # ---- 多维表工具 ----
    "app.agents.tools.data_table_tool:CreateDataTable": {
        "capability_id": "native.create_data_table",
        "display_name": "Create Data Table",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "创建当前工作区或全局工作区多维数据表。",
    },
    "app.agents.tools.data_table_tool:ReadDataTableSchema": {
        "capability_id": "native.read_data_table_schema",
        "display_name": "Read Data Table Schema",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "读取多维数据表的元数据和列定义。",
    },
    "app.agents.tools.data_table_tool:QueryDataTable": {
        "capability_id": "native.query_data_table",
        "display_name": "Query Data Table",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "对多维数据表执行只读 SQL 查询。",
    },
    "app.agents.tools.data_table_tool:InsertDataTableRecords": {
        "capability_id": "native.insert_data_table_records",
        "display_name": "Insert Data Table Records",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "向多维数据表插入记录。",
    },
    "app.agents.tools.data_table_tool:UpdateDataTableRecord": {
        "capability_id": "native.update_data_table_record",
        "display_name": "Update Data Table Record",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "更新多维数据表记录。",
    },
    "app.agents.tools.data_table_tool:DeleteDataTableRecord": {
        "capability_id": "native.delete_data_table_record",
        "display_name": "Delete Data Table Record",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "删除多维数据表记录。",
    },
    "app.agents.tools.data_table_tool:AddDataTableColumn": {
        "capability_id": "native.add_data_table_column",
        "display_name": "Add Data Table Column",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "向多维数据表新增列。",
    },
    "app.agents.tools.data_table_tool:UpdateDataTableColumn": {
        "capability_id": "native.update_data_table_column",
        "display_name": "Update Data Table Column",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "更新多维数据表列定义。",
    },
    "app.agents.tools.data_table_tool:RemoveDataTableColumn": {
        "capability_id": "native.remove_data_table_column",
        "display_name": "Remove Data Table Column",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "删除多维数据表列。",
    },
    # ---- Canvas 工具 ----
    "app.agents.tools.canvas_tool:ReadCanvas": {
        "capability_id": "native.read_canvas",
        "display_name": "Read Canvas",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "读取 JSON Canvas 文件。",
    },
    "app.agents.tools.canvas_tool:WriteCanvas": {
        "capability_id": "native.write_canvas",
        "display_name": "Write Canvas",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "覆盖写入 JSON Canvas 文件。",
    },
    "app.agents.tools.canvas_tool:BatchCanvasOperations": {
        "capability_id": "native.batch_canvas_operations",
        "display_name": "Batch Canvas Operations",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "批量增删改 JSON Canvas 节点和边。",
    },
    "app.agents.tools.skill_tools:ListSkills": {
        "capability_id": "runtime.list_skills",
        "display_name": "ListSkills",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "列出当前上下文所有可用 Skill（builtin + workspace）。",
    },
    "app.agents.tools.skill_tools:LoadSkill": {
        "capability_id": "runtime.load_skill",
        "display_name": "LoadSkill",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "加载指定 Skill 的 SKILL.md 或目录下其他文件内容。",
    },
    "app.agents.tools.skill_tools:SearchStoreSkills": {
        "capability_id": "runtime.search_store_skills",
        "display_name": "SearchStoreSkills",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "搜索全局仓库中可启用的 Skill（系统内置 + 用户导入）。",
    },
    "app.agents.tools.skill_tools:EnableSkill": {
        "capability_id": "runtime.enable_skill",
        "display_name": "EnableSkill",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "将 Skill 从全局仓库启用到当前工作区。",
    },
    "app.agents.tools.skill_tools:DisableSkill": {
        "capability_id": "runtime.disable_skill",
        "display_name": "DisableSkill",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "从当前工作区禁用 Skill。",
    },
    "app.agents.tools.auto_task_signal_tool:AutoTaskSignal": {
        "capability_id": "native.auto_task_signal",
        "display_name": "AutoTaskSignal",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "连续自动任务写回完成或暂停状态的信号工具。",
    },
    "app.agents.tools.auto_task_tool:CreateAutoTask": {
        "capability_id": "native.create_auto_task",
        "display_name": "CreateAutoTask",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "在当前工作区创建自动任务。",
    },
    "app.agents.tools.auto_task_tool:ListAutoTasks": {
        "capability_id": "native.list_auto_tasks",
        "display_name": "ListAutoTasks",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "列出当前工作区的所有自动任务。",
    },
    "app.agents.tools.auto_task_tool:UpdateAutoTask": {
        "capability_id": "native.update_auto_task",
        "display_name": "UpdateAutoTask",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "更新当前工作区的自动任务配置。",
    },
    "app.agents.tools.auto_task_tool:ControlAutoTask": {
        "capability_id": "native.control_auto_task",
        "display_name": "ControlAutoTask",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "暂停、恢复、完成、立即执行或删除当前工作区的自动任务。",
    },
    "app.agents.tools.task_plan_tools:TaskCreateTool": {
        "capability_id": "native.session_task_create",
        "display_name": "TaskCreate",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "在当前会话内创建结构化任务，用于复杂需求拆解和进度跟踪。",
    },
    "app.agents.tools.task_plan_tools:TaskUpdateTool": {
        "capability_id": "native.session_task_update",
        "display_name": "TaskUpdate",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "更新当前会话内结构化任务的状态、内容和依赖。",
    },
    "app.agents.tools.task_plan_tools:TaskListTool": {
        "capability_id": "native.session_task_list",
        "display_name": "TaskList",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "列出当前会话内结构化任务清单和状态统计。",
    },
    "app.agents.tools.task_plan_tools:SetTodoList": {
        "capability_id": "native.session_set_todo_list",
        "display_name": "SetTodoList",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "读写当前会话的待办任务列表。传 todos 写入，不传则读取。",
    },
    "app.agents.tools.task_plan_tools:EnterPlanModeTool": {
        "capability_id": "native.enter_plan_mode",
        "display_name": "EnterPlanMode",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "进入只读规划模式，运行时只暴露读类工具和计划提交入口。",
    },
    "app.agents.tools.task_plan_tools:ExitPlanModeTool": {
        "capability_id": "native.exit_plan_mode",
        "display_name": "ExitPlanMode",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "提交规划方案，写入当前会话 plans 目录并请求用户审批。",
    },
    "app.agents.tools.file_tools:ReadFile": {
        "capability_id": "runtime.read_file",
        "display_name": "ReadFile",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "读取当前工作区中的文本文件内容，支持分页和行号定位。",
    },
    "app.agents.tools.file_tools:WriteFile": {
        "capability_id": "runtime.write_file",
        "display_name": "WriteFile",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "将内容写入当前工作区中的文件，支持覆盖和追加模式。",
    },
    "app.agents.tools.file_tools:StrReplaceFile": {
        "capability_id": "runtime.str_replace_file",
        "display_name": "StrReplaceFile",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "通过精确字符串替换编辑当前工作区中的文件内容。",
    },
    "app.agents.tools.env_vars_tool:GetEnvVar": {
        "capability_id": "runtime.get_env_var",
        "display_name": "GetEnvVar",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "读取当前会话运行态中某个环境变量的值，敏感值会自动脱敏。",
    },
    "app.agents.tools.env_vars_tool:SetEnvVar": {
        "capability_id": "runtime.set_env_var",
        "display_name": "SetEnvVar",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "设置工作区级别的环境变量，写入当前工作区 runtime_binding.env_vars。",
    },
    "app.agents.tools.env_vars_tool:DeleteEnvVar": {
        "capability_id": "runtime.delete_env_var",
        "display_name": "DeleteEnvVar",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "删除工作区级别的环境变量（从当前工作区 runtime_binding.env_vars 中移除）。",
    },
    "app.agents.tools.runtime_environment_tool:RuntimeEnvironment": {
        "capability_id": "runtime.manage_workspace_runtime_environment",
        "display_name": "RuntimeEnvironment",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "管理当前工作区登记的 UV 运行环境，支持列出、检查、创建、安装依赖和绑定默认环境。",
    },
    "app.agents.tools.shell_tool:Shell": {
        "capability_id": "runtime.shell",
        "display_name": "Shell",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "在当前工作区执行单次 Shell 命令，同步返回输出和退出码。",
    },
    "app.agents.tools.database_query_tool:DatabaseQuery": {
        "capability_id": "native.database_query",
        "display_name": "Database Query",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "对挂载的外部数据库执行 SQL 查询或写入。",
    },
    "app.agents.tools.database_query_tool:ListDatabaseConnectors": {
        "capability_id": "native.list_database_connectors",
        "display_name": "List Database Connectors",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "列出当前可用的外部数据库连接器。",
    },
    "app.agents.tools.database_query_tool:ListDatabaseTables": {
        "capability_id": "native.list_database_tables",
        "display_name": "List Database Tables",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "列出指定数据库连接器中的所有表。",
    },
    "app.agents.tools.database_query_tool:DescribeDatabaseTable": {
        "capability_id": "native.describe_database_table",
        "display_name": "Describe Database Table",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "查看指定数据库表的结构信息。",
    },
    "app.services.agent.runtime_backends.aiasys.tools.memory_tool:MemoryTool": {
        "capability_id": "aiasys.memory",
        "display_name": "Memory",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "读写工作区或全局 Memory 文件。",
    },
    "app.services.agent.runtime_backends.aiasys.tools.acp_client_tool:AcpClientTool": {
        "capability_id": "aiasys.acp_client",
        "display_name": "AcpClient",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "调用外部 Agent 协作协议（ACP）端点。",
    },
    "app.services.agent.runtime_backends.aiasys.tools.monitor_tool:SpawnMonitorTool": {
        "capability_id": "aiasys.spawn_monitor",
        "display_name": "SpawnMonitor",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "启动后台长时间运行任务监控。",
    },
    "app.services.agent.runtime_backends.aiasys.tools.monitor_tool:ManageMonitorTool": {
        "capability_id": "aiasys.manage_monitor",
        "display_name": "ManageMonitor",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "管理后台监控任务（停止、查看状态）。",
    },
    NATIVE_CREATE_SUBAGENT_TOOL_PATH: {
        "capability_id": "aiasys.create_subagent",
        "display_name": "CreateSubagent",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "创建子 Agent 实例。",
    },
    "app.services.agent.runtime_backends.aiasys.tools.list_subagents_tool:ListSubagentsTool": {
        "capability_id": "aiasys.list_subagents",
        "display_name": "ListSubagents",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "列出当前会话的子 Agent 实例。",
    },
    "app.services.agent.runtime_backends.aiasys.tools.update_subagent_tool:UpdateSubagentTool": {
        "capability_id": "aiasys.update_subagent",
        "display_name": "UpdateSubagent",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "更新子 Agent 实例配置。",
    },
    "app.services.agent.runtime_backends.aiasys.tools.delete_subagent_tool:DeleteSubagentTool": {
        "capability_id": "aiasys.delete_subagent",
        "display_name": "DeleteSubagent",
        "kind": CapabilityKind.NATIVE_TOOL,
        "provider": "aiasys",
        "description": "删除子 Agent 实例。",
    },
    "app.agents.tools.notebook_runtime_tool:RunNotebook": {
        "capability_id": "runtime.run_notebook",
        "display_name": "RunNotebook",
        "kind": CapabilityKind.RUNTIME_HELPER,
        "provider": "aiasys",
        "description": "执行 Notebook 中的指定 cell 或全部 cell。",
    },
}

_SYSTEM_INTEGRATION_CATALOG: tuple[dict[str, Any], ...] = ()

_TOOL_CATEGORY_CAPABILITY_IDS: dict[str, tuple[str, ...]] = {
    "delegation": ("native.multiagent_task",),
    "workspace-files": (
        "runtime.read_file",
        "runtime.write_file",
        "runtime.str_replace_file",
    ),
    "environment": (
        "runtime.get_env_var",
        "runtime.set_env_var",
        "runtime.delete_env_var",
        "runtime.manage_workspace_runtime_environment",
    ),
    "code-runtime": (
        "runtime.shell",
        "runtime.run_code",
        "runtime.list_kernel_envs",
        "runtime.register_kernel_env",
        "runtime.remove_kernel_env",
    ),
    "task-planning": (
        "native.session_task_create",
        "native.session_task_update",
        "native.session_task_list",
        "native.enter_plan_mode",
        "native.exit_plan_mode",
    ),
    "databases": (
        "native.database_query",
        "native.list_database_connectors",
        "native.list_database_tables",
        "native.describe_database_table",
    ),
    "data-tables": (
        "native.create_data_table",
        "native.read_data_table_schema",
        "native.query_data_table",
        "native.insert_data_table_records",
        "native.update_data_table_record",
        "native.delete_data_table_record",
        "native.add_data_table_column",
        "native.update_data_table_column",
        "native.remove_data_table_column",
    ),
    "canvas": (
        "native.read_canvas",
        "native.write_canvas",
        "native.batch_canvas_operations",
    ),
    "knowledge-base": (
        "native.knowledge_query",
        "native.knowledge_bases",
        "native.create_knowledge_base",
        "native.update_knowledge_base",
        "native.upload_knowledge_base_documents",
        "native.list_knowledge_base_documents",
        "native.delete_knowledge_base_documents",
        "native.delete_knowledge_base",
    ),
    "knowledge-graph": (
        "native.graphrag_entity_search",
        "native.graphrag_entity_detail",
        "native.list_knowledge_graphs",
        "native.create_knowledge_graph",
        "native.delete_knowledge_graph",
        "native.create_graph_entity",
        "native.update_graph_entity",
        "native.delete_graph_entity",
        "native.create_graph_relation",
        "native.graphrag_entity_relations",
        "native.graphrag_community_report",
        "native.graphrag_document_upload",
    ),
    "notebook": (
        "runtime.read_notebook",
        "runtime.edit_notebook",
        "runtime.list_session_notebooks",
        "runtime.create_session_notebook",
        "runtime.read_notebook_outputs",
        "runtime.manage_notebook",
    ),
    "media": ("native.read_media_file",),
    "skills": (
        "runtime.list_skills",
        "runtime.load_skill",
    ),
    "automation": (
        "native.auto_task_signal",
        "native.create_auto_task",
        "native.list_auto_tasks",
        "native.update_auto_task",
        "native.control_auto_task",
    ),
    "user-interaction": ("runtime.ask_user",),
}

_TOOL_CATEGORY_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "category_id": "delegation",
        "display_name": "子任务委派",
        "description": "把独立子任务交给其他 Agent 执行。",
        "permission_summary": ["multiagent_task"],
        "runtime_dependencies": ["agent_runtime"],
    },
    {
        "category_id": "workspace-files",
        "display_name": "工作区文件",
        "description": "读取、写入和编辑当前工作区文件。",
        "permission_summary": ["workspace_files"],
        "runtime_dependencies": ["workspace_storage"],
    },
    {
        "category_id": "environment",
        "display_name": "运行环境",
        "description": "查看运行态变量名，管理当前工作区登记的 UV 执行环境。",
        "permission_summary": ["runtime_env_read", "workspace_runtime_write"],
        "runtime_dependencies": ["session_runtime", "workspace_runtime_registry"],
    },
    {
        "category_id": "code-runtime",
        "display_name": "代码与命令执行",
        "description": "执行 Shell、Python 代码和管理可用内核环境。",
        "permission_summary": ["local_runtime", "shell", "kernel_env"],
        "runtime_dependencies": ["local_python_runtime"],
    },
    {
        "category_id": "task-planning",
        "display_name": "任务计划",
        "description": "维护当前会话的结构化任务清单和规划模式。",
        "permission_summary": ["session_task_plan"],
        "runtime_dependencies": ["session_storage"],
    },
    {
        "category_id": "databases",
        "display_name": "数据库",
        "description": "查看数据库连接器、表结构并执行 SQL。",
        "permission_summary": ["database_query"],
        "runtime_dependencies": ["database_connector_service"],
    },
    {
        "category_id": "data-tables",
        "display_name": "多维表",
        "description": "创建多维表、读写记录并维护列定义。",
        "permission_summary": ["data_table_read", "data_table_write"],
        "runtime_dependencies": ["workspace_storage", "sqlite"],
    },
    {
        "category_id": "canvas",
        "display_name": "Canvas",
        "description": "读取、写入和批量修改 JSON Canvas 文件。",
        "permission_summary": ["canvas_read", "canvas_write"],
        "runtime_dependencies": ["workspace_storage"],
    },
    {
        "category_id": "knowledge-base",
        "display_name": "知识库",
        "description": "查询、创建、上传和清理知识库文档。",
        "permission_summary": ["knowledge_base_read", "knowledge_base_write"],
        "runtime_dependencies": ["knowledge_service"],
    },
    {
        "category_id": "knowledge-graph",
        "display_name": "知识图谱",
        "description": "创建图谱、维护实体关系、检索关系和上传图谱文档。",
        "permission_summary": ["knowledge_graph_read", "knowledge_graph_write"],
        "runtime_dependencies": ["graphrag_storage"],
    },
    {
        "category_id": "notebook",
        "display_name": "Notebook",
        "description": "Notebook 列表、创建、编辑、执行和输出读取能力。",
        "permission_summary": ["notebook_read", "notebook_write", "local_runtime"],
        "runtime_dependencies": ["local_python_runtime"],
    },
    {
        "category_id": "media",
        "display_name": "文件与多模态读取",
        "description": "读取媒体文件和多模态文件内容。",
        "permission_summary": ["workspace_files", "media_read"],
        "runtime_dependencies": ["workspace_storage"],
    },
    {
        "category_id": "skills",
        "display_name": "Skill",
        "description": "列出和加载当前上下文可用的 Skill。",
        "permission_summary": ["skill_read"],
        "runtime_dependencies": ["skill_registry"],
    },
    {
        "category_id": "automation",
        "display_name": "自动任务",
        "description": "创建、查看、更新、完成、执行和删除工作区自动任务。",
        "permission_summary": ["auto_task_control"],
        "runtime_dependencies": ["auto_task_service"],
    },
    {
        "category_id": "user-interaction",
        "display_name": "用户确认",
        "description": "在需要人工确认时暂停并向用户提问。",
        "permission_summary": ["user_confirmation"],
        "runtime_dependencies": ["conversation_runtime"],
    },
)


def _sanitize_capability_id(value: str) -> str:
    return value.replace(":", ".").replace("/", ".").replace("-", "_").strip(".").lower()


def _parse_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_tool_name_for_capability_id(capability_id: str) -> str | None:
    normalized = str(capability_id or "").strip()
    if not normalized:
        return None
    for tool_name, metadata in _TOOL_METADATA.items():
        if metadata.get("capability_id") == normalized:
            return tool_name
    return None


def resolve_tool_category_for_capability_id(capability_id: str) -> tuple[str, str]:
    normalized = str(capability_id or "").strip()
    for catalog in _TOOL_CATEGORY_CATALOG:
        category_id = str(catalog["category_id"])
        if normalized in _TOOL_CATEGORY_CAPABILITY_IDS.get(category_id, ()):
            return category_id, str(catalog["display_name"])
    return "other", "其他工具"


def resolve_tool_category_capability_ids(
    tool_category_ids: Iterable[str] | None,
) -> list[str]:
    capability_ids: list[str] = []
    for category_id in tool_category_ids or []:
        normalized_category_id = str(category_id or "").strip()
        if not normalized_category_id:
            continue
        for capability_id in _TOOL_CATEGORY_CAPABILITY_IDS.get(normalized_category_id, ()):
            if capability_id not in capability_ids:
                capability_ids.append(capability_id)
    return capability_ids


def resolve_tool_category_tool_names(
    tool_category_ids: Iterable[str] | None,
) -> list[str]:
    tool_names: list[str] = []
    for capability_id in resolve_tool_category_capability_ids(tool_category_ids):
        tool_name = _resolve_tool_name_for_capability_id(capability_id)
        if tool_name and tool_name not in tool_names:
            tool_names.append(tool_name)
    return tool_names

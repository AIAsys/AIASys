"""Agent 工具集合。"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.agent_tool import AiasysTool

    from .ask_user.tool import AskUser
    from .auto_task_signal_tool import AutoTaskSignal
    from .expert_tools import (
        ConfigureExpert,
        InstallExpert,
        ListSystemExperts,
    )
    from .auto_task_tool import (
        ControlAutoTask,
        CreateAutoTask,
        ListAutoTasks,
        UpdateAutoTask,
    )
    from .canvas_tool import (
        BatchCanvasOperations,
        ReadCanvas,
        WriteCanvas,
    )
    from .code_execution_tool import (
        ListKernelEnvs,
        RegisterKernelEnv,
        RemoveKernelEnv,
        RunCode,
    )
    from .data_table_tool import (
        AddDataTableColumn,
        CreateDataTable,
        DeleteDataTableRecord,
        InsertDataTableRecords,
        QueryDataTable,
        ReadDataTableSchema,
        RemoveDataTableColumn,
        UpdateDataTableColumn,
        UpdateDataTableRecord,
    )
    from .database_query_tool import (
        DatabaseQuery,
        DescribeDatabaseTable,
        ListDatabaseConnectors,
        ListDatabaseTables,
    )
    from .env_vars_tool import (
        DeleteEnvVar,
        GetEnvVar,
        ListEnvVars,
        SetEnvVar,
    )
    from .file_tools import ReadFile, StrReplaceFile, WriteFile
    from .graphrag_tool import (
        CreateGraphEntity,
        CreateGraphRelation,
        CreateKnowledgeGraph,
        DeleteGraphEntity,
        DeleteKnowledgeGraph,
        GetCommunityReport,
        GetKnowledgeGraphEntityDetail,
        ListKnowledgeGraphs,
        QueryEntityRelations,
        SearchKnowledgeGraphEntities,
        UpdateGraphEntity,
        UploadDocumentsToGraph,
        get_graphrag_service_for_tools,
    )
    from .knowledge_tool import (
        CreateKnowledgeBase,
        DeleteDocumentsFromKnowledgeBase,
        DeleteKnowledgeBase,
        KnowledgeBaseQuery,
        ListKnowledgeBaseDocuments,
        ListKnowledgeBases,
        UpdateKnowledgeBase,
        UploadDocumentsToKnowledgeBase,
        get_create_knowledge_base_tool,
        get_delete_documents_from_knowledge_base_tool,
        get_delete_knowledge_base_tool,
        get_knowledge_query_tool,
        get_list_knowledge_base_documents_tool,
        get_list_knowledge_bases_tool,
        get_update_knowledge_base_tool,
        get_upload_documents_to_knowledge_base_tool,
    )
    from .notebook_session_tool import (
        ListSessionNotebooks,
    )
    from .notebook_tool import ManageNotebook
    from .runtime_environment_tool import RuntimeEnvironment
    from .shell_tool import Shell
    from .task_plan_tools import (
        EnterPlanModeTool,
        ExitPlanModeTool,
        TaskCreateTool,
        TaskListTool,
        TaskUpdateTool,
    )

__all__ = [
    "AiasysTool",
    "ListSystemExperts",
    "InstallExpert",
    "ConfigureExpert",
    "ListSessionNotebooks",
    "ManageNotebook",
    "RunCode",
    "ListKernelEnvs",
    "RegisterKernelEnv",
    "RemoveKernelEnv",
    "ReadFile",
    "WriteFile",
    "StrReplaceFile",
    "GetEnvVar",
    "SetEnvVar",
    "DeleteEnvVar",
    "ListEnvVars",
    "RuntimeEnvironment",
    "Shell",
    "ListSkills",
    "LoadSkill",
    "SearchStoreSkills",
    "EnableSkill",
    "DisableSkill",
    "SearchKnowledgeGraphEntities",
    "GetKnowledgeGraphEntityDetail",
    "ListKnowledgeGraphs",
    "CreateKnowledgeGraph",
    "DeleteKnowledgeGraph",
    "CreateGraphEntity",
    "UpdateGraphEntity",
    "DeleteGraphEntity",
    "CreateGraphRelation",
    "QueryEntityRelations",
    "GetCommunityReport",
    "UploadDocumentsToGraph",
    "get_graphrag_service_for_tools",
    "KnowledgeBaseQuery",
    "get_knowledge_query_tool",
    "ListKnowledgeBases",
    "get_list_knowledge_bases_tool",
    "CreateKnowledgeBase",
    "get_create_knowledge_base_tool",
    "UpdateKnowledgeBase",
    "get_update_knowledge_base_tool",
    "UploadDocumentsToKnowledgeBase",
    "get_upload_documents_to_knowledge_base_tool",
    "ListKnowledgeBaseDocuments",
    "get_list_knowledge_base_documents_tool",
    "DeleteDocumentsFromKnowledgeBase",
    "get_delete_documents_from_knowledge_base_tool",
    "DeleteKnowledgeBase",
    "get_delete_knowledge_base_tool",
    "DatabaseQuery",
    "ListDatabaseConnectors",
    "ListDatabaseTables",
    "DescribeDatabaseTable",
    "CreateDataTable",
    "ReadDataTableSchema",
    "QueryDataTable",
    "InsertDataTableRecords",
    "UpdateDataTableRecord",
    "DeleteDataTableRecord",
    "AddDataTableColumn",
    "UpdateDataTableColumn",
    "RemoveDataTableColumn",
    "ReadCanvas",
    "WriteCanvas",
    "BatchCanvasOperations",
    "CreateAutoTask",
    "ListAutoTasks",
    "UpdateAutoTask",
    "ControlAutoTask",
    "AutoTaskSignal",
    "TaskCreateTool",
    "TaskUpdateTool",
    "TaskListTool",
    "EnterPlanModeTool",
    "ExitPlanModeTool",
    # Ask user
    "AskUser",
    "ListMCPServers",
    "SearchMCPMarket",
    "InstallMCPServer",
    "SearchAvailableConnectors",
    "InstallConnector",
]


def __getattr__(name: str) -> Any:
    if name == "AiasysTool":
        return import_module("app.core.agent_tool").AiasysTool

    if name == "ReadNotebook":
        return import_module(".notebook_file_tool", __name__).ReadNotebook
    if name == "EditNotebookFile":
        return import_module(".notebook_file_tool", __name__).EditNotebookFile
    if name in {
        "ListSessionNotebooks",
        "CreateSessionNotebook",
        "ReadNotebookOutputs",
    }:
        module = import_module(".notebook_session_tool", __name__)
        return getattr(module, name)
    if name == "ManageNotebook":
        return import_module(".notebook_tool", __name__).ManageNotebook
    if name == "RunCode":
        return import_module(".code_execution_tool", __name__).RunCode
    if name == "ListKernelEnvs":
        return import_module(".code_execution_tool", __name__).ListKernelEnvs
    if name == "RegisterKernelEnv":
        return import_module(".code_execution_tool", __name__).RegisterKernelEnv
    if name == "RemoveKernelEnv":
        return import_module(".code_execution_tool", __name__).RemoveKernelEnv
    if name == "ReadFile":
        return import_module(".file_tools", __name__).ReadFile

    if name == "WriteFile":
        return import_module(".file_tools", __name__).WriteFile

    if name == "StrReplaceFile":
        return import_module(".file_tools", __name__).StrReplaceFile

    if name in {
        "GetEnvVar",
        "SetEnvVar",
        "DeleteEnvVar",
        "ListEnvVars",
    }: 
        module = import_module(".env_vars_tool", __name__)
        return getattr(module, name)

    if name == "RuntimeEnvironment":
        return import_module(".runtime_environment_tool", __name__).RuntimeEnvironment

    if name == "Shell":
        return import_module(".shell_tool", __name__).Shell

    if name in {
        "ListSkills",
        "LoadSkill",
        "SearchStoreSkills",
        "EnableSkill",
        "DisableSkill",
    }:
        module = import_module(".skill_tools", __name__)
        return getattr(module, name)

    if name in {
        "ListSystemExperts",
        "InstallExpert",
        "ConfigureExpert",
    }:
        module = import_module(".expert_tools", __name__)
        return getattr(module, name)

    if name in {
        "SearchKnowledgeGraphEntities",
        "GetKnowledgeGraphEntityDetail",
        "ListKnowledgeGraphs",
        "CreateKnowledgeGraph",
        "DeleteKnowledgeGraph",
        "CreateGraphEntity",
        "UpdateGraphEntity",
        "DeleteGraphEntity",
        "CreateGraphRelation",
        "QueryEntityRelations",
        "GetCommunityReport",
        "UploadDocumentsToGraph",
        "get_graphrag_service_for_tools",
    }:
        module = import_module(".graphrag_tool", __name__)
        return getattr(module, name)

    if name in {
        "KnowledgeBaseQuery",
        "get_knowledge_query_tool",
        "ListKnowledgeBases",
        "get_list_knowledge_bases_tool",
        "CreateKnowledgeBase",
        "get_create_knowledge_base_tool",
        "UpdateKnowledgeBase",
        "get_update_knowledge_base_tool",
        "UploadDocumentsToKnowledgeBase",
        "get_upload_documents_to_knowledge_base_tool",
        "ListKnowledgeBaseDocuments",
        "get_list_knowledge_base_documents_tool",
        "DeleteDocumentsFromKnowledgeBase",
        "get_delete_documents_from_knowledge_base_tool",
        "DeleteKnowledgeBase",
        "get_delete_knowledge_base_tool",
    }:
        module = import_module(".knowledge_tool", __name__)
        return getattr(module, name)

    if name in {
        "DatabaseQuery",
        "ListDatabaseConnectors",
        "ListDatabaseTables",
        "DescribeDatabaseTable",
    }:
        module = import_module(".database_query_tool", __name__)
        return getattr(module, name)

    if name in {
        "CreateDataTable",
        "ReadDataTableSchema",
        "QueryDataTable",
        "InsertDataTableRecords",
        "UpdateDataTableRecord",
        "DeleteDataTableRecord",
        "AddDataTableColumn",
        "UpdateDataTableColumn",
        "RemoveDataTableColumn",
    }:
        module = import_module(".data_table_tool", __name__)
        return getattr(module, name)

    if name in {
        "ReadCanvas",
        "WriteCanvas",
        "BatchCanvasOperations",
    }:
        module = import_module(".canvas_tool", __name__)
        return getattr(module, name)

    if name in {
        "CreateAutoTask",
        "ListAutoTasks",
        "UpdateAutoTask",
        "ControlAutoTask",
    }:
        module = import_module(".auto_task_tool", __name__)
        return getattr(module, name)

    if name == "AutoTaskSignal":
        return import_module(".auto_task_signal_tool", __name__).AutoTaskSignal

    if name in {
        "TaskCreateTool",
        "TaskUpdateTool",
        "TaskListTool",
        "SetTodoList",
        "EnterPlanModeTool",
        "ExitPlanModeTool",
    }:
        module = import_module(".task_plan_tools", __name__)
        return getattr(module, name)

    if name == "RunNotebook":
        return import_module(".notebook_runtime_tool", __name__).RunNotebook

    if name == "AskUser":
        return import_module(".ask_user.tool", __name__).AskUser

    if name in {
        "ListMCPServers",
        "SearchMCPMarket",
        "InstallMCPServer",
        "SearchAvailableConnectors",
        "InstallConnector",
    }:
        module = import_module(".mcp_tools", __name__)
        return getattr(module, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# 文档-代码映射索引

> 随代码变更持续更新。修改任一行代码时，检查对应文档是否需要同步。

## workspace-creation.md
- 覆盖功能: 工作区创建、切换、删除、模板选择、Python 环境绑定
- 前端组件:
  - apps/web/src/components/NewWorkspaceDialog/index.tsx (创建对话框)
  - apps/web/src/pages/WorkspacePage/index.tsx (主界面工作区切换)
- 后端路由:
  - apps/backend/app/api/routes/workspaces.py (路由聚合)
  - apps/backend/app/api/routes/workspaces_core.py (工作区 CRUD)
  - apps/backend/app/api/routes/workspace_templates.py (模板 API)
  - apps/backend/app/api/routes/runtime_envs.py (Python 环境注册)

## global-workspace.md
- 覆盖功能: 全局工作区概念、跨工作区共享资源、配置继承
- 前端组件:
  - apps/web/src/components/layout/WorkspaceSidebar/WorkspaceAssetPanel.tsx (全局工作区面板)
- 后端路由:
  - apps/backend/app/api/routes/workspaces_core.py (工作区路由含全局工作区逻辑)
- 关键配置:
  - apps/backend/app/services/workspace_registry.py (工作区目录结构)

## workspace-templates.md
- 覆盖功能: 工作区模板创建、使用、管理、外部导入
- 前端组件:
  - apps/web/src/components/NewWorkspaceDialog/index.tsx (模板选择)
  - apps/web/src/components/settings/TemplateMarketPanel.tsx (模板市场)
  - apps/web/src/components/settings/TemplateManagementPanel.tsx (模板管理)
- 后端路由:
  - apps/backend/app/api/routes/workspace_templates.py (模板 CRUD)

## file-management.md
- 覆盖功能: 文件浏览、编辑、预览、上传、历史版本、差异对比
- 前端组件:
  - apps/web/src/components/layout/WorkspaceSidebar/WorkspaceContextPanel.tsx (文件树)
  - apps/web/src/components/layout/WorkspaceSidebar/FileTreeView.tsx (树视图)
  - apps/web/src/components/editor/CodeEditorPanel.tsx (代码编辑器)
  - apps/web/src/components/editor/CodeMirrorEditor.tsx (CodeMirror 封装)
  - apps/web/src/components/layout/WorkspaceSidebar/FileHistoryDialog.tsx (版本历史)
  - apps/web/src/components/diff/DiffViewer.tsx (差异对比)
- 后端路由:
  - apps/backend/app/api/routes/files.py (文件路由聚合)
  - apps/backend/app/api/routes/files_core.py (文件读写、上传、下载、导出)
  - apps/backend/app/api/routes/files_utils.py (文件工具函数)
  - apps/backend/app/api/routes/diff.py (差异对比)

## file-tree-config.md
- 覆盖功能: .aiasys/file-tree-config.json 配置说明
- 后端路由:
  - apps/backend/app/api/routes/workspaces_resources_tree.py (文件树 API，使用配置)
- 关键配置:
  - apps/backend/app/services/file_tree_config.py (配置模型与默认值)

## canvas-usage.md
- 覆盖功能: JSON Canvas 画布编辑、节点/边操作、Agent 操作
- 前端组件:
  - apps/web/src/components/CanvasEditor/CanvasEditor.tsx (画布编辑器)
  - apps/web/src/components/CanvasEditor/CanvasToolbar.tsx (工具栏)
  - apps/web/src/components/CanvasEditor/CanvasPropertiesPanel.tsx (属性面板)
  - apps/web/src/components/CanvasEditor/CanvasContextMenu.tsx (右键菜单)
- 后端路由:
  - apps/backend/app/api/routes/canvas.py (Canvas 文件读写)

## data-table-usage.md
- 覆盖功能: 多维表格创建、字段定义、行编辑、Agent 操作
- 前端组件:
  - apps/web/src/components/layout/WorkspaceSidebar/DataTablePreviewPanel.tsx (表格预览)
- 后端路由:
  - apps/backend/app/api/routes/data_tables.py (数据表 CRUD)

## notebook-usage.md
- 覆盖功能: Notebook 打开、运行、Inspector 面板、Python 环境切换
- 前端组件:
  - apps/web/src/components/layout/WorkspaceSidebar/preview/NotebookPreview.tsx (Notebook 预览)
  - apps/web/src/pages/WorkspacePage/components/Notebook/ (Notebook 相关组件目录)
- 后端路由:
  - apps/backend/app/api/routes/notebooks.py (路由聚合)
  - apps/backend/app/api/routes/notebooks_core.py (Notebook CRUD)
  - apps/backend/app/api/routes/notebooks_cells.py (Cell 操作)
  - apps/backend/app/api/routes/notebooks_execution.py (Cell 执行)

## database-query.md
- 覆盖功能: DuckDB、外部数据库、SQL 查询、结果作为上下文
- 前端组件:
  - apps/web/src/components/database/DatabaseQueryWorkbench.tsx (查询工作台)
  - apps/web/src/components/database/DatabaseConnectionsManagerPanel/DatabaseConnectionsManagerPanel.tsx (连接管理)
- 后端路由:
  - apps/backend/app/api/routes/database_connectors.py (外部数据库连接器)
  - apps/backend/app/api/routes/file_database.py (文件数据库查询)
  - apps/backend/app/api/routes/runtime_database.py (运行时数据库)
  - apps/backend/app/api/routes/session_database.py (会话数据库 broker)

## execution-resources.md
- 覆盖功能: Python 环境注册、UV 管理、包安装、Kernel 切换
- 前端组件:
  - apps/web/src/components/execution-resources/ExecutionResourcesPanel.tsx (执行资源面板)
  - apps/web/src/components/execution-resources/PythonRuntimeTab.tsx (Python 环境列表与包安装)
- 后端路由:
  - apps/backend/app/api/routes/runtime_envs.py (UV 环境管理)
  - apps/backend/app/api/routes/kernel_envs.py (Kernel 环境管理)
- 后端服务:
  - apps/backend/app/services/runtime_environment.py (UV 环境生命周期与包安装)
- 后端工具:
  - apps/backend/app/agents/tools/runtime_environment_tool.py (Agent 运行时环境工具)

## container-resources.md
- 覆盖功能: Docker 沙盒登记、创建、管理
- 前端组件:
  - apps/web/src/components/container-resources/ContainerResourcesPanel.tsx (容器资源面板)
- 后端路由:
  - apps/backend/app/api/routes/container_resources.py (容器资源管理)

## terminal-monitor.md
- 覆盖功能: WebSocket 终端（Linux/macOS/Windows 三端）、后台监控任务
- 前端组件:
  - apps/web/src/components/terminal/TerminalPanel.tsx (终端面板)
  - apps/web/src/components/layout/WorkspaceSidebar/WorkspaceMonitorPanel.tsx (监控面板)
- 后端路由:
  - apps/backend/app/api/routes/terminal.py (WebSocket 终端)
  - apps/backend/app/api/routes/sessions_monitor.py (后台任务监控)
- 后端服务:
  - apps/backend/app/services/terminal/pty_manager.py (PTY 会话管理，跨平台支持)

## knowledge-base.md
- 覆盖功能: 知识库创建、文档上传、混合检索
- 前端组件:
  - apps/web/src/components/KnowledgeBaseMarket/index.tsx (知识库市场)
- 后端路由:
  - apps/backend/app/api/routes/knowledge.py (知识库 CRUD、检索)

## knowledge-graph.md
- 覆盖功能: 图谱构建、可视化、实体搜索、社区分析
- 前端组件:
  - apps/web/src/components/KnowledgeGraphDialog/ (图谱对话框)
  - apps/web/src/pages/Knowledge/GraphPage/ (图谱独立页面)
- 后端路由:
  - apps/backend/app/api/routes/canvas.py (图可视化相关)
  - apps/backend/app/api/routes/file_database.py (图谱数据库文件)

## agent-chat.md
- 覆盖功能: 对话发起、会话管理、模型选择、富文本聊天、AskUser
- 前端组件:
  - apps/web/src/pages/WorkspacePage/components/WorkspaceLayout/ConversationDock.tsx (对话容器)
  - apps/web/src/pages/WorkspacePage/components/WorkspaceLayout/DockChatView.tsx (聊天视图)
  - apps/web/src/pages/WorkspacePage/components/InputArea.tsx (输入区)
  - apps/web/src/pages/WorkspacePage/components/ModelSelector.tsx (模型选择器)
  - apps/web/src/components/chat/TokenUsageBar.tsx (Token 占用)
  - apps/web/src/components/AskUserDialog/ (确认弹窗)
- 后端路由:
  - apps/backend/app/api/routes/agent.py (Agent 执行)
  - apps/backend/app/api/routes/sessions.py (会话管理)
  - apps/backend/app/api/routes/sessions_messages.py (消息管理)
  - apps/backend/app/api/routes/ask_user.py (AskUser 响应)

## agent-configuration.md
- 覆盖功能: Soul、项目画像、会话覆盖三层配置
- 前端组件:
  - apps/web/src/components/agent-config/AgentConfigPanel.tsx (Agent 配置面板)
  - apps/web/src/components/workspace/WorkspaceAgentConfigPanel.tsx (工作区 Agent 配置)
- 后端路由:
  - apps/backend/app/api/routes/agent_config.py (Agent 配置 API)

## expert-roles.md
- 覆盖功能: 协作专家市场、启用策略、工具策略、执行树
- 前端组件:
  - apps/web/src/components/layout/WorkspaceSidebar/SubAgentTreeOverview.tsx (执行树)
  - apps/web/src/components/layout/WorkspaceSidebar/WorkspaceSubagentPanel.tsx (子 Agent 面板)
  - apps/web/src/components/RolesManagerPanel.tsx (专家管理)
  - apps/web/src/components/CollaborationRolesSettingsDialog.tsx (专家设置)
- 后端路由:
  - apps/backend/app/api/routes/workspaces_core.py (专家启用/禁用路由)

## mcp-skill-market.md
- 覆盖功能: MCP 管理、Skill 安装/卸载、内置 Skill 清单
- 前端组件:
  - apps/web/src/components/MCPMarketDialog.tsx (MCP 市场)
  - apps/web/src/components/settings/SettingsMCPMarketPanel.tsx (MCP 设置)
  - apps/web/src/components/settings/ExternalMCPMarketPanel.tsx (外部 MCP 市场)
  - apps/web/src/components/SkillMarketDialog.tsx (Skill 市场)
  - apps/web/src/components/SkillMarket/index.tsx (Skill 市场面板)
  - apps/web/src/components/settings/SettingsSkillMarketPanel.tsx (Skill 设置)
  - apps/web/src/components/settings/ExternalSkillMarketPanel.tsx (外部 Skill 市场)
- 后端路由:
  - apps/backend/app/api/routes/mcp.py (MCP CRUD)
  - apps/backend/app/api/routes/mcp_session.py (会话级 MCP)
  - apps/backend/app/api/routes/skills.py (Skill 管理)

## autotask.md
- 覆盖功能: AutoTask 四种触发类型、会话策略、完成审计
- 前端组件:
  - apps/web/src/components/layout/WorkspaceSidebar/WorkspaceAutoTaskPanel.tsx (AutoTask 面板)
  - apps/web/src/components/layout/WorkspaceSidebar/AutoTask/ (AutoTask 组件目录)
- 后端路由:
  - apps/backend/app/api/routes/auto_tasks.py (AutoTask CRUD)

## environment-variables.md
- 覆盖功能: 全局/工作区两级环境变量管理
- 前端组件:
  - apps/web/src/components/workspace/EnvVarsPanel.tsx (工作区环境变量)
  - apps/web/src/components/workspace/GlobalEnvVarsDialog.tsx (全局环境变量)
- 后端路由:
  - apps/backend/app/api/routes/global_env_vars.py (全局环境变量)

## session-management.md
- 覆盖功能: Fork、导出 Bundle、预算、检查点
- 前端组件:
  - apps/web/src/components/CheckpointReviewDialog/index.tsx (检查点)
  - apps/web/src/pages/WorkspacePage/components/SessionLifecycleDialogs/ (会话生命周期)
- 后端路由:
  - apps/backend/app/api/routes/sessions.py (会话管理)
  - apps/backend/app/api/routes/sessions_branches.py (分支/Fork)
  - apps/backend/app/api/routes/sessions_exports.py (导出)

## context-compression.md
- 覆盖功能: 双层压缩策略、手动压缩、上下文占用
- 前端组件:
  - apps/web/src/components/chat/TokenUsageBar.tsx (上下文占用展示)
- 关键配置:
  - apps/backend/app/services/agent/compaction.py (压缩引擎)

## memory-system.md
- 覆盖功能: 四层记忆架构、记忆面板
- 前端组件:
  - apps/web/src/components/layout/WorkspaceSidebar/preview/MemoryPreviewPanel.tsx (记忆预览)
- 后端路由:
  - apps/backend/app/api/routes/memory.py (记忆 API)
  - apps/backend/app/api/routes/memory_schemas.py (记忆模型)
- 关键配置:
  - apps/backend/app/services/memory/ (记忆服务模块)

## channel-claw.md
- 覆盖功能: IM 平台接入、微信/飞书连接、远程派任务
- 前端组件:
  - apps/web/src/pages/WorkspacePage/components/WorkspaceLayout/ChannelBindingSection.tsx (频道绑定)
  - apps/web/src/pages/WorkspacePage/components/WorkspaceLayout/ChannelSessionPanel.tsx (频道会话)
- 后端路由:
  - apps/backend/app/api/routes/claw.py (Claw 通信)
  - apps/backend/app/api/routes/channels.py (频道管理)

## capability-registry.md
- 覆盖功能: MCP/Skill/专家的统一发现、安装、验活
- 前端组件:
  - apps/web/src/components/CapabilityPanel/index.tsx (能力面板)
- 后端路由:
  - apps/backend/app/api/routes/capabilities.py (能力注册表 API)

## desktop-app.md
- 覆盖功能: Electron 桌面应用启动、端口管理、三端支持
- 前端组件:
  - apps/desktop/src/main.cjs (Electron 主进程)
  - apps/desktop/src/service-manager.cjs (服务管理)
  - apps/desktop/src/preload.cjs (预加载脚本)
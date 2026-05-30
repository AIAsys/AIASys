# WorkspacePage 页面组件

本目录存放 `WorkspacePage` 当前主页面使用的局部 UI 组件。它们围绕真实分析工作台组织，不再对应早期的 `Host` / `CodeExecutorTestPage` 命名。

## 组件说明

### 布局与导航

- **`TopBar.tsx`**: 顶部任务栏。负责当前对话标题与布局折叠控制，不再承载 execution journal 状态。
- **`ExecutionSpaceButton.tsx`**: 打开右侧任务工作区。当前只要已有对话就保持可达，不再依赖是否已有任务或工作区文件。

### 核心交互区

- **`InputArea.tsx`**: 底部输入区域。包含文本输入、发送、停止、文件上传、模型切换、当前会话工具配置，以及 `压缩上下文` 这类高频会话维护快捷动作。
- **`WorkspaceLayout/ConversationDock.tsx`**: 右侧会话侧栏。承接 `当前会话 / 托管 / Claw` 这组会话级入口，其中 `Claw` 用于当前会话的远端出站同步绑定、微信二维码登录与状态查看。

### 功能模态框与辅助

- **`FileImportModal.tsx`**: 文件导入模态框。允许用户从历史对话或其他来源导入文件到当前工作区。
- **`ExecutionResourcesPanel.tsx`**: Python 与执行资源面板。通过齿轮设置菜单或输入框 Python 状态徽标打开，管理当前工作区 Python 环境、Docker 资源、工作区变量注入。Docker 资源直接嵌在 Docker 分组里，不再作为文件树资源或二级跳转入口。
- **`SessionLifecycleDialogs.tsx`**: 历史记录详情弹窗。用于查看当前会话保留的对话上下文与代码执行轨迹，并按维护时间戳折叠较早批次。
- **`WorkspaceAuxiliaryDialogs.tsx`**: 页面级辅助对话框集合。负责执行环境重置确认以及其他非主链弹窗；其中本地执行链路需要明确提示“释放当前 notebook 内核，下一次代码执行时创建新的执行环境”。
- **`ToastContainer.tsx`**: 页面级消息提示容器，用于显示操作成功或失败的通知。

## 当前页面关系

```text
WorkspacePage
  -> TopBar
  -> ChatArea
  -> InputArea
  -> WorkspaceSidebar
  -> WorkspaceContextSurface
     -> WorkspaceSettingsCanvas
  -> FileImportModal
  -> ToolPreviewPopover
```

## 维护提醒

1. 这些组件大多依赖 `useCodeExecutor` 输出的页面级状态，不应假设自己独立拥有对话生命周期。
2. 右侧任务工作区当前真实对应的是 `tasks / files / database` 三个视图，不是单一日志面板。
3. 当前三层边界已收口为：当前会话工具配置和 `压缩上下文` 的高频主入口放在对话输入框；用户默认层走 `/workspace` 内嵌的模型与 Agent 配置入口，工作区层走中间主画布的 `设置` 视图，会话级远端同步入口走 `ConversationDock -> Claw`，运行证据主要走任务工作区视图与历史记录详情弹窗。
4. 顶部主入口和欢迎屏当前默认打开中间主画布的 `设置` 视图；右侧工作区上下文和侧栏工作区入口打开中间主画布的 `设置` 视图，侧栏底部的”工作区工具”菜单继续负责自动任务管理、托管概览、模型配置和默认工作方式入口。
5. `Claw` 当前入口仍是 session 级：可先用 Hermes 风格二维码链接创建/更新微信连接资产，再把当前会话最后一条 assistant 可见回复出站同步到远端；不要把它误写成工作区资源默认值，也不要把 tool / think / system 内容发出去。
6. “重置执行环境”的文案要继续区分旧 Docker 语义与当前本地执行语义：本地更准确的是“释放当前内核，下一次代码执行时创建新内核”，不要把它写成已经恢复旧变量。
7. 如果当前对话已有执行记录且环境状态处于 `fresh/missing/discarded`，前端只展示真实状态，不自动插入 system 提示，也不改写用户输入；如需继续，应通过“重置执行环境”或让 Agent 基于当前对话、工作区文件和代码执行记录重新生成必要步骤。
8. 如需重命名或拆组件，应优先保持和 `WorkspacePage` 当前术语一致，避免再引入 `Host` 旧名。
9. `WorkspaceSettingsCanvas` 只维护工作区层；不要再往里面塞“我的默认”或独立模型配置这类用户默认层内容。

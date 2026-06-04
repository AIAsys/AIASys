# 组件架构

> 当前前端主链里最重要的组件边界，重点覆盖聊天区、右侧执行空间和 `DataAnalysisPage` 页面组件。

## 当前页面骨架

```text
DataAnalysisPage
  -> TopBar
  -> ChatArea
  -> InputArea
  -> WorkspaceSidebar
  -> FileImportModal
  -> ToolPreviewPopover
```

## ChatArea

### 角色

- 负责渲染 `chatItems`
- 区分用户消息和 AI 消息
- 把 `sessionId`、工具详情回调、Worker 点击回调传入消息渲染树

### 关键特点

- 采用 Compound Components + Context
- `AiMessageContent` 负责解析 `segments`
- 工具详情不是直接塞进正文，而是通过 `onViewToolDetails` 打开悬浮预览

## AiMessageContent

### 角色

- 把 AI 消息分段渲染为：
  - `think`
  - `text`
  - `tool_call`
  - `tool_output`
  - `final_answer`

### 当前边界

- 工具调用正文只展示摘要，不承担完整工具详情面板
- 工作区图片、Markdown 渲染等会话相关资源依赖 `sessionId`
- Worker 活动状态与 `think` 分段需要一起看，不能拆成完全独立的两套渲染

## WorkspaceSidebar

### 角色

右侧执行空间，承接同一会话下的三种视图：

1. `tasks`
2. `files`
3. `database`

### 当前结构

```text
components/layout/WorkspaceSidebar/
  -> SidebarProvider.tsx
  -> TabNavigation.tsx
  -> TaskTimeline.tsx
  -> WorkspaceAssetPanel.tsx
  -> FileTreeView.tsx
  -> DatabaseTab.tsx
  -> ToolPreview.tsx
```

### 当前职责

- `tasks`
  展示执行流、任务事件、工具详情入口
- `files`
  展示工作区文件、预览、删除、ZIP 导出、Markdown 导出
- `database`
  展示当前会话数据库 schema

## DataAnalysisPage 局部组件

### `TopBar.tsx`

- 展示当前会话与任务配置入口的顶部信息
- 不应自行决定会话生命周期，只消费页面主编排状态

### `InputArea.tsx`

- 负责用户输入、发送、停止、文件上传
- 输入锁定应服从页面级生命周期，而不是内部自行判定

### `ExecutionSpaceButton.tsx`

- 打开右侧执行空间
- 当前语义对应整块右侧边栏，不只是“查看日志”

### `FileImportModal.tsx`

- 负责跨来源导入文件
- 最终目标仍是把文件同步到当前会话工作区

## 组件边界原则

1. 页面生命周期在 `DataAnalysisPage` 和其 hooks 中，组件只消费状态，不重建一套流程。
2. `ChatArea` 和 `WorkspaceSidebar` 是同一执行过程的两种展示，不应各自维护独立业务真相。
3. 右侧边栏的导出、数据库查看和工具预览都是会话相关能力，不能脱离 `sessionId` 单独工作。
4. 新增组件前先判断它是页面局部 UI，还是应进 `components/chat` / `components/layout` 的通用层。

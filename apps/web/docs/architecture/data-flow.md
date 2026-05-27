# 数据流

> 当前 `DataAnalysisPage` 从输入、会话编排、SSE 流式、历史恢复到右侧执行空间的主数据流。

## 当前主链

```text
用户输入 / 新建任务 / 会话切换
  -> DataAnalysisPage/index.tsx
  -> useCodeExecutor
       -> useSessionOrchestrator
       -> useExecutionSubmit
       -> useStreamEventHandler
       -> useWorkspacePolling
       -> useChatState
       -> useSessionManagement
       -> useRuntimeEnvironmentPanel
  -> ChatArea / WorkspaceSidebar / TopBar
```

## 三条核心数据流

### 1. 提交流

1. `InputArea` 触发提交。
2. `useCodeExecutor` 负责把“当前会话是否可执行、是否需要先创建/切换目标会话、是否要锁输入”统一编排。
3. `useExecutionSubmit` 发起实际执行请求。
4. `useAgentStream` / SSE 层开始接收事件。

### 2. 流式事件流

1. 后端持续返回 `text / think / tool_call / tool_output / status / error / done` 等事件。
2. `useStreamEventHandler` 把事件拆到两个地方：
   - `chatItems`，用于主聊天区渲染
   - `taskList` / `selectedTask`，用于右侧执行流和工具详情
3. `useToolPreview` 和侧边栏工具预览都消费同一批工具事件，只是展示位置不同。

### 3. 会话恢复 / 工作区流

1. `useSessionManagement` 负责历史会话列表、切换、删除和恢复入口。
2. `sessionRestore.ts` / `useSessionOrchestrator.ts` 负责把历史消息、执行记录和目标会话激活过程收敛到统一生命周期。
3. `useCodeExecutor` 会在前台 session 激活后主动拉一次工作区文件，避免空会话的 `.preference.md` 要等首次执行才出现。
4. `useWorkspacePolling` 只在当前活跃 session 运行中时继续轮询刷新。
5. `useMultiTaskEventStream` 维护 per-session `workspaceFiles` 缓存，后台 session 的文件刷新不会再覆盖当前前台工作区。
6. `SidebarProvider` 在 `tasks / files / database` 三个 Tab 间复用同一会话上下文。

## 当前关键数据结构

### `ChatItem`

- 主聊天区的消息对象。
- 既承载最终内容，也承载流式分段和历史恢复信息。
- 来源：`apps/web/src/pages/DataAnalysisPage/types.ts`

### `ChatSegment`

- AI 消息内部分段。
- 当前重要类型包括：
  - `text`
  - `think`
  - `tool_call`
  - `tool_output`
  - `final_answer`

### `TaskState`

- 右侧执行空间的任务视图模型。
- 主要承载：
  - 任务时间线
  - 工具事件
  - Worker 记录
  - 当前选中任务状态

## 右侧执行空间的数据流

```text
taskList / selectedTask
  -> WorkspaceSidebar
      -> tasks: TaskTimeline / ToolPreview
      -> files: WorkspaceArtifacts / FileTreeView
      -> database: DatabaseTab
```

当前右侧边栏已经不是早期的“任务 + 技能”结构，当前实际是：

1. `tasks`
2. `files`
3. `database`

并且 `files` Tab 还承担了：

- 工作区 ZIP 导出
- `.md` / `.markdown` 文件导出为 `.md / .docx / .pdf`
- 文件预览与删除

## 当前最容易出问题的流转点

1. 新建任务与会话切换是同一条生命周期，不是两个互不相关的动作。
2. SSE 事件不能直接覆盖当前前台会话，必须先确认目标会话已经 ready。
3. 聊天区和右侧边栏展示的是同一任务事实，只是渲染角度不同，不能各自维护一套互相漂移的状态。
4. 工作区文件刷新不能晚于会话激活太多，否则会出现“消息已开始但工作区还没准备好”的分裂体验。
5. 旧 session 的文件刷新结果不能直接写回当前前台；否则最先暴露的问题通常是右侧工作区文件突然变化或 `.preference.md` 消失。

## 当前阅读顺序

1. `apps/web/src/pages/DataAnalysisPage/index.tsx`
2. `apps/web/src/pages/DataAnalysisPage/hooks/useCodeExecutor/index.ts`
3. `apps/web/src/pages/DataAnalysisPage/hooks/useCodeExecutor/useSessionOrchestrator.ts`
4. `apps/web/src/pages/DataAnalysisPage/hooks/useCodeExecutor/useStreamEventHandler.ts`
5. `apps/web/src/components/layout/WorkspaceSidebar/SidebarProvider.tsx`

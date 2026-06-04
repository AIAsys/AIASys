# 状态管理

> 当前前端主链的状态分层，重点覆盖 `DataAnalysisPage`、右侧执行空间和全局流式通信。

## 三层状态模型

1. **全局能力 Hook**
   - 负责跨页面可复用的 API、流式通信和系统能力
2. **页面编排 Hook**
   - 负责 `DataAnalysisPage` 的会话生命周期、执行编排和 UI 主链
3. **组件内 Context**
   - 负责聊天区、右侧执行空间等局部渲染状态共享

## 全局能力 Hook

### 流式与执行

- `useAgentStream.ts`
  Agent 流式执行封装
- `useMultiTaskEventStream.ts`
  任务事件与执行流状态
- `useExecutionHistory.ts`
  历史执行记录读取

### 会话周边能力

- `useAskUser.ts`
  AskUser 请求、恢复与提交
- `useAgentFileUpload.ts`
  Agent 文件上传
- `usePreferences.ts`
  用户偏好读写

### 其他通用能力

- `useSkills.ts`
- `useMCPConfig.ts`
- `useSessionMCP.ts`
- `useSessionMCPManager.ts`
- `useSystemCapabilities.ts`
- `useSystemVersion.ts`
- `useChatInput.ts`
- `useDragDrop.ts`
- `use-mobile.ts`

## 页面级主编排

### `useCodeExecutor`

这是当前 `DataAnalysisPage` 的主编排入口，不只是“执行代码”。

它当前主要负责：

- 聊天消息状态整合
- 执行提交流程
- 会话恢复
- 目标会话激活
- 右侧执行空间状态
- 工作区刷新
- 工作区文件的 session-aware 同步
- 停止执行和错误回收

### `useCodeExecutor` 内部关键子模块

- `useExecutionSubmit.ts`
  发起执行请求，处理真正的 submit 入口
- `useSessionOrchestrator.ts`
  负责新建任务 / 切换目标会话 / 激活前台会话的生命周期
- `useStreamEventHandler.ts`
  负责把 SSE 事件落到 `chatItems` 和 `taskList`
- `useWorkspacePolling.ts`
  负责工作区文件刷新
- `sessionRestore.ts`
  负责历史会话消息与任务恢复
- `useUIState.ts`
  负责页面局部 UI 状态

## 页面级辅助 Hook

- `useChatState.ts`
  管理 `chatItems` 和输入态
- `useSessionManagement.ts`
  管理历史会话列表、切换、删除
- `useWorkspaceRuntimeControls.ts`
  管理新建工作区弹窗、运行态重建确认和相关状态
- `useToolPreview.ts`
  管理工具详情悬浮预览
- `useFileImport.ts`
  管理文件导入模态框

## 组件内 Context

### `AiMessageContext`

负责单条 AI 消息的局部渲染状态，例如：

- `think` 分段
- `tool_call` / `tool_output`
- `final_answer`
- worker 活动状态

目标是把复杂渲染状态封装在消息内部，而不是继续把大量 props 往下传。

### `ChatAreaContext`

负责聊天区域单条消息渲染时共享：

- 当前消息项
- 用户 / AI 身份判断
- 工具详情预览回调
- Worker 点击回调
- 会话级元信息

### `SidebarContext`

负责右侧执行空间共享：

- 当前 `activeTab`
- `taskList / selectedTask`
- `workspaceFiles`
- `sessionId`
- 导出动作
- 工具详情选中状态

当前 `activeTab` 真实取值是：

- `tasks`
- `files`
- `database`

## 当前最重要的状态边界

1. 会话状态和 UI 展示状态不能提前分离，目标会话未 ready 前不能切到前台。
2. `chatItems` 和 `taskList` 不是两套业务事实，而是同一执行过程的两种视图。
3. 右侧工作区文件刷新、数据库 Tab 和聊天区消息都依赖当前会话上下文，不能跨会话串线。
4. `useCodeExecutor` 是当前主链总编排，后续如要拆分，必须先守住生命周期一致性，而不是只按文件大小拆。
5. `workspaceFiles` 不能再只靠“当前 React state”保存，后台 session 的文件刷新必须写回 per-session 缓存，避免旧回包覆盖前台。
6. `.preference.md` 的可见性属于会话激活链的一部分，前台 session 进入可见状态后就应主动同步一次工作区文件。

## 当前推荐阅读顺序

1. `apps/web/src/pages/DataAnalysisPage/hooks/useCodeExecutor/index.ts`
2. `apps/web/src/pages/DataAnalysisPage/hooks/useCodeExecutor/useSessionOrchestrator.ts`
3. `apps/web/src/pages/DataAnalysisPage/hooks/useCodeExecutor/useStreamEventHandler.ts`
4. `apps/web/src/components/chat/AiMessageContent/context.tsx`
5. `apps/web/src/components/layout/WorkspaceSidebar/context/types.ts`

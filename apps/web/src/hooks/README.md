# 全局 Hooks

本目录存放跨页面可复用的 React Custom Hooks，重点覆盖 API 调用、SSE、会话周边能力和系统信息。

## 当前主要分类

### 流式与执行

- **`useSSEStream.ts`**: 基础 SSE 通道，不带业务语义。
- **`useAgentStream.ts`**: Agent 流式执行封装。
- **`useMultiTaskEventStream.ts`**: 任务事件流与执行流状态。
- **`useExecutionHistory.ts`**: 历史执行记录读取。

### 会话周边能力

- **`useAgentFileUpload.ts`**: Agent 文件上传。
- 当前主线不再提供独立的运行环境查询与切换 Hook；相关逻辑已收口到分析页内部的工作区创建与运行态控制链路。
- **`useAskUser.ts`**: AskUser 请求与恢复。
- **`useSessionMCP.ts`** / **`useSessionMCPManager.ts`**: 会话级 MCP 控制。
- **`useMCPConfig.ts`**: 用户级 MCP 配置。

### 数据与配置

- **`useSkills.ts`**: Skills 相关请求。
- **`useSystemVersion.ts`**: 系统版本读取。

### 输入与交互

- **`useChatInput.ts`**: 输入框交互。
- **`useDragDrop.ts`**: 拖拽上传。

## 维护提醒

1. 认证相关 Hook 已经收口到 `contexts/AuthContext.tsx` 导出的 `useAuthContext()` / `useAuthState()`，本目录不再维护旧式 `useAuth.ts`。
2. 当前页面主编排大多在 `pages/DataAnalysisPage/hooks/`，不要把页面级生命周期误记到这里。
3. 如新增 Hook，优先判断它是“跨页面复用能力”还是“页面编排逻辑”，避免继续把所有逻辑都塞进 `src/hooks/`。

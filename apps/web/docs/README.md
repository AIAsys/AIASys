# Web 文档索引

本目录记录 `apps/web` 侧的人类可读架构说明。它主要用来帮助理解当前前端主链，不应替代源码或 `ai-rules`。

## 当前文档

- `architecture/data-flow.md`
  当前 `DataAnalysisPage` 从输入、流式事件、会话恢复到右侧边栏的主数据流
- `architecture/state-management.md`
  当前页面级 Hook、全局 Hook 与侧边栏 / 聊天区状态分层
- `architecture/components.md`
  当前聊天区、右侧执行空间、DataAnalysisPage 组件职责
- `types/core-types.md`
  核心类型定义

## 推荐阅读顺序

1. `architecture/data-flow.md`
2. `architecture/state-management.md`
3. `architecture/components.md`
4. `types/core-types.md`

## 使用边界

1. 文档用于解释结构，不作为运行时真实状态的唯一来源。
2. 遇到 DataAnalysisPage、会话生命周期、工作区、运行态控制等主链问题时，优先回源码和 `ai-rules` 的状态流资料核对。
3. 当前主链重点已经不只是聊天，还包括：
   - `useCodeExecutor` 的会话编排
   - 右侧执行空间的 `tasks/files/database` 三个 Tab
   - 工具预览、工作区导出、偏好初始化、会话恢复
   - `workspaceFiles` 的 session-aware 同步，以及 `.preference.md` 的前台可见性
4. 后续前端主链重构，应优先补这里的索引和主题说明，再决定是否拆新文档。

## 本地开发

```bash
cd apps/web
npm install
npm run dev -- --port 13000
```

## 与后端联调

默认联调目标：`http://localhost:13001`

- 代理路径：`/api`、`/health`
- 配置位置：`apps/web/vite.config.ts`
- 可通过 `VITE_API_TARGET` 覆盖

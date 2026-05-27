# AIASys Web Frontend

AIASys 前端应用，基于 React + TypeScript + Vite，主要页面是 `/analysis` 的会话化分析工作台。

## 技术栈

- React `19`
- TypeScript `5.9`
- Vite `7`
- Tailwind CSS `4`
- Radix UI / shadcn/ui

## 快速开始

```bash
./dev.sh setup
./dev.sh
```

如只想单独运行前端，也可以：

```bash
cd apps/web
npm install
npm run dev -- --port 13000
```

开发地址：`http://localhost:13000`

## 前后端联调

Vite 代理配置在 `vite.config.ts`：

- `/api` -> `VITE_API_TARGET`（默认 `http://localhost:13001`）
- `/health` -> `VITE_API_TARGET`

可选环境变量：

```bash
VITE_API_TARGET=http://localhost:13001
VITE_AUTH_MODE=local
```

## 路由概览（`src/App.tsx`）

- `/`, `/home`
- `/analysis`, `/analysis/:sessionId`
- `/tools`
- `/skills`
- `/environments`
- `/my-environments`
- `/profile`
- `/login`

## 关键模块

- `src/pages/DataAnalysisPage/`：主工作台（输入、消息区、左右侧栏、弹窗）
- `src/hooks/useCodeExecutor.ts`：会话、提交、上传、停止、工作区联动
- `src/hooks/useAgentStream.ts`：Agent 流式执行封装
- `src/components/layout/WorkspaceSidebar/`：执行事件与工件视图
- `src/components/AskUserDialog/`：人机确认交互
- `src/config/api.ts`：统一 API 常量

## 常用命令

```bash
npm run dev
npm run build
npm run lint
npm run preview
```

## 相关文档

- `apps/web/docs/README.md`
- 根目录开发入口：`dev.sh`（聚合 `check/setup/start/start-local/restart/restart-local/stop/status/logs`）
- 根协作规则：`.agents/skills/.ai-rules/SKILL.md`

---
name: aiasys-frontend-architecture
description: |
  AIASys 项目专属前端架构与实现约束。用于在 AIASys 仓库中开发前端代码时，明确当前系统真实骨架与通用最佳实践之间的取舍关系。涵盖目录结构、路由方式、状态管理、API 层、组件分层等关键决策。始终在通用 skill 之前读取，确保实现服从项目现状。
---

# AIASys 前端架构

描述 AIASys 前端项目的真实架构现状，以及何时参考通用最佳实践、何时必须服从当前系统骨架。

---

## 定位与使用方式

本 skill 不是替代 `frontend-pattern`、`frontend-design` 等通用技能，而是**优先级覆盖层**。

当在 AIASys 中写前端代码时，调用顺序应为：

1. `aiasys-frontend-architecture`（本项目真相）
2. `aiasys-system-design`（产品语义与信息架构）
3. 根目录 `DESIGN.md`（视觉设计基线，颜色/字体/间距/组件规格，Google Stitch 标准，放根目录是约定）
4. `frontend-pattern` / `frontend-design`（通用技术与设计规范）
5. 当前任务文档 / task session

如果通用 best practice 与本文档冲突，**优先服从本文档**。

---

## 技术栈真相

| 技术 | 版本 / 方式 | 备注 |
|------|------------|------|
| React | 19.1 | 利用并发特性，但 `use` 钩子目前使用较少 |
| TypeScript | 5.9 | 严格类型 |
| Tailwind CSS | 4 | 原子化样式，禁止内联 style |
| 路由 | 自定义手动路由 | 基于 `window.history`，**无 React Router** |
| 状态管理 | React Context + 自定义 Hooks | **无 Redux / Zustand / Jotai** |
| API 层 | 基于 fetch 的 `httpClient` | 位于 `src/lib/api/` |
| UI 组件 | shadcn/ui + Radix UI | 位于 `src/components/ui/` |
| 构建 | Vite | 标准配置 |

---

## 核心取舍：为什么不是标准 best practice

### 1. 手动路由 vs React Router

**现状**：AIASys 使用自己实现的手动路由，在 `App.tsx` 中通过 `useState` 监听 `location.pathname` 和 `search`，并暴露 `appNavigate` 全局函数。

**取舍原因**：
- 当前系统路由极简单（仅 10 个以内顶层页面）
- 不需要嵌套路由、路由守卫、loader 等复杂能力
- 自定义路由更轻量，能统一处理 overlay 弹层与 legacy path 重定向

**要求**：
- 新页面必须在 `App.tsx` 中手动注册 lazy import 和路由匹配
- 禁止引入 React Router、TanStack Router 等第三方路由库
- 页面间跳转统一使用 `window.appNavigate?.(path)` 或直接操作 `window.history`

### 2. Context + Hooks vs 全局状态管理库

**现状**：没有 Zustand/Redux/MobX。全局状态只有 `AuthContext`，其余全部是页面级 / 组件级自定义 hooks。

**取舍原因**：
- 系统状态天然按页面隔离（分析页、设置页、知识页互不共享）
- 引入全局状态库会增加不必要的抽象和依赖
- 当前模式在页面内部通过 hook composition 已经能表达复杂状态

**要求**：
- 如果一个状态只服务单个页面，放在 `pages/xxx/hooks/` 下
- 如果一个状态跨 2~3 个组件但仍在同一页面内，放在该页面的 `hooks/` 或 `components/` 下
- 只有真正跨页面、跨工作区的状态（如当前用户、当前任务工作区主键）才能进 `src/contexts/` 或 `src/hooks/` 全局层
- 禁止为了“规范”而把局部状态抬到全局

### 3. 自定义 httpClient vs Axios / TanStack Query

**现状**：`src/lib/api/httpClient.ts` 封装了基于 `fetch` 的请求逻辑，各模块在 `src/lib/api/` 下按领域拆分为独立文件（`workspaces.ts`、`mcp.ts`、`knowledge.ts` 等）。

**取舍原因**：
- fetch 原生支持已足够，无需引入 axios
- 没有复杂的缓存、去重、后台刷新需求，暂时不需要 TanStack Query
- 按领域拆分的 API 文件更符合当前后端微模块结构

**要求**：
- 新增后端接口时，先在 `src/lib/api/` 下找到对应领域文件补充函数
- 如果没有对应文件，新建一个以领域命名的 ts 文件
- 统一通过 `apiFetch` 发起请求，继承统一的 baseURL、timeout、错误提取逻辑
- 禁止在组件内部直接写 `fetch(url)` 或引入 axios

### 4. Feature-Folder 的适用范围

**现状**：只有复杂页面采用 Feature-Folder（`pages/DataAnalysisPage/components/`、`hooks/`），简单页面仍是单文件。

**取舍原因**：
- 不要为了拆分而拆分。简单页面（如 `SettingsPage`、`LoginPage`）保持扁平更直观
- 只有当一个页面超过 3 个专属组件或 3 个专属 hooks 时，才启用 Feature-Folder

**要求**：
- 新建页面默认在 `pages/` 下放一个 `index.tsx`
- 当页面复杂度增长时，再拆出 `components/` 和 `hooks/`
- 不要一开始就创建过度嵌套的目录

---

## 目录结构规范

```
apps/web/src/
├── App.tsx                    # 根组件 + 手动路由
├── main.tsx                   # 入口
├── index.css                  # Tailwind 导入 + 全局变量
├── lib/
│   ├── api/                   # 按领域拆分的 API 层
│   ├── utils.ts               # 通用工具函数
│   └── ...
├── contexts/
│   └── AuthContext.tsx        # 认证上下文（唯一全局 Context）
├── hooks/
│   ├── useAuth.ts             # AuthContext 消费 hook
│   ├── useMultiTaskEventStream.ts
│   └── ...                    # 其他跨页面全局 hooks
├── components/
│   ├── ui/                    # shadcn/ui 组件
│   ├── layout/                # 布局组件（侧边栏、顶部栏）
│   ├── chat/                  # 聊天相关复合组件
│   └── ...                    # 其他跨页面复用组件
├── pages/
│   ├── HomePage/
│   │   └── index.tsx
│   ├── DataAnalysisPage/
│   │   ├── index.tsx
│   │   ├── components/        # 页面专属组件
│   │   ├── hooks/             # 页面专属 hooks
│   │   └── types.ts
│   └── ...
├── config/
│   ├── api.ts                 # API_BASE_URL 等
│   └── auth.ts                # 认证模式配置
└── types/
    └── api.ts                 # 通用 API 类型
```

**禁止的行为**：
- 不要在 `components/` 下创建与页面完全绑定的组件（应放到对应页面的 `components/` 下）
- 不要把 API 类型和业务类型混在 `types/` 里不动脑分类
- 不要把路由守卫逻辑散落在各个页面（统一在 `App.tsx` 或 `components/auth/RouteGuard.tsx`）

---

## 状态管理分层

### 全局层（src/contexts/、src/hooks/）

只放以下状态：
- 当前认证用户（AuthContext）
- 当前任务工作区主键（useMultiTaskEventStream）
- 全局事件流（SSE）连接状态

### 页面层（pages/xxx/hooks/）

放以下状态：
- 页面内列表数据、筛选条件、查询结果
- 页面级弹窗开关
- 页面内表单状态
- 页面级副作用协调（如 DataAnalysisPage 的 controller hook）

### 组件层

只放以下状态：
- 局部 UI 状态（hover、展开/折叠、内部 tab 索引）
- 不跨组件的表单输入

---

## 路由与导航

### 当前路由表（App.tsx 中硬编码）

主要路由：
- `/` -> HomePage
- `/workspace` -> WorkspacePage（核心页面，带 overlay 参数）
- `/analysis` -> 已重定向到 /workspace（保留兼容）
- `/knowledge/*` -> 知识库相关页面
- `/settings/*` -> 设置中心
- `/login` -> LoginPage

### 导航方式

```tsx
// 推荐：使用全局暴露的 navigate
window.appNavigate?.("/workspace?session_id=123");

// 或直接使用 history API
window.history.pushState({}, "", "/workspace");
window.dispatchEvent(new PopStateEvent("popstate"));
```

### Overlay 弹层路由

AIASys 当前大量使用 overlay 参数控制弹层：
- `/workspace?overlay=database`
- `/workspace?overlay=knowledge_base`

这种设计让弹层能与 URL 同步，同时不脱离当前页面上下文。

**要求**：
- 新增需要在 URL 中保留状态的弹层，优先沿用 overlay 参数模式
- 弹层关闭时负责清理 URL 参数，并触发 `popstate` 事件让 App.tsx 重新渲染

---

## API 层规范

### 错误处理

`httpClient.ts` 已经统一提取错误信息：
- 优先读取 `detail`
- 其次读取 `message`
- 最后读取 `error`

**要求**：
- 组件中调用 API 时，不要自己再写一层错误消息解析
- 只需要根据业务判断是否需要 toast 提示或显示在表单里

### 类型定义

- API 请求/响应类型优先放在 `src/types/api.ts` 或页面级 `types.ts`
- 不要把后端 schema 直接 copy 到前端而不加筛选

---

## 组件开发原则

### 何时使用 shadcn/ui

- 基础交互组件（Button、Input、Dialog、Card、Select）必须使用 shadcn/ui
- 自定义组件在 shadcn 基础上包装，不要从零写基础样式

### 何时创建跨页面组件

以下条件满足 2 条以上才放到 `src/components/`：
- 明确被 2 个以上页面使用
- 不依赖特定页面的业务类型
- 具备通用语义（如 `DataTable`、`Sidebar`、`ChatArea`）

### 样式规范

- 必须使用 `cn()` 合并类名（来自 `src/lib/utils.ts`）
- 禁止内联 `style={{ ... }}`
- 禁止在 className 里写模板字符串拼接，统一用 `cn()`

---

## 最佳实践参考指南

### 这些情况优先看 `frontend-pattern`

- React 19 新特性怎么用（`useTransition`、Suspense 边界）
- Tailwind 4 类名写法、响应式断点、主题变量
- shadcn/ui 组件的安装和使用方式
- 竞态防护、AbortController 等通用模式
- 组件 Props 类型定义、错误状态处理等代码规范

### 这些情况优先服从本 skill

- 路由怎么加、页面怎么注册
- 状态放全局还是页面级
- API 文件放哪里、怎么命名
- 组件目录怎么拆
- 导航代码怎么写
- 是否与当前手动路由 / Context+Hooks 架构冲突

---

## 快速检查清单

**新增页面时：**
- [ ] 已在 `App.tsx` 中注册 lazy import 和路由匹配
- [ ] 页面复杂度不高时保持单文件，必要时再拆 Feature-Folder
- [ ] 页面级 hooks 放在 `pages/xxx/hooks/`

**新增 API 调用时：**
- [ ] 已检查 `src/lib/api/` 下是否有对应领域文件
- [ ] 使用 `apiFetch` 或该文件封装好的函数
- [ ] 未在组件内直接写裸 fetch

**新增组件时：**
- [ ] 跨页面通用组件才放 `src/components/`
- [ ] 页面专属组件放 `pages/xxx/components/`
- [ ] 使用 `cn()` 管理类名
- [ ] 支持 `className` prop

**新增状态时：**
- [ ] 先判断是否真的需要全局状态
- [ ] 局部状态优先放在最近的使用层级
- [ ] 复杂页面级状态用自定义 hook 封装

---

注意：本 skill 是 AIASys 前端项目的专属约束层，描述的是当前代码库的真实骨架，不是理想架构。任何改动若与本文档冲突，必须先经过架构讨论，不能单方面引入新依赖或新模式。

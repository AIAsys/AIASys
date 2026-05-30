---
name: frontend-pattern
description: AIASys 前端开发完整规范，包含项目架构取舍、React 19 + Tailwind 4 + shadcn/ui 开发模式、性能优化规则。始终优先于通用 best practice，确保实现服从项目现状。当创建 React 组件、实现页面、处理状态管理、或处理异步操作时使用。
---

# 前端开发规范

AIASys 前端开发的完整指南：先讲架构取舍（为什么不做 X），再讲实现规范（怎么做 Y）。

**关联文档：**
- `DESIGN.md`：视觉设计基线，涉及界面布局、视觉风格、组件外观时必读
- `aiasys-system-design`：系统设计约束，涉及页面路由、信息架构、设置页布局时参考
- `aiasys-frontend-architecture`：AIASys 专属前端架构与实现约束，路由、状态管理、API 层的取舍说明
- `browser-control`：前端验证的浏览器截图和交互验收流程
- `testing-strategy`：前端 Playwright E2E 测试规范

---

## 第一部分：AIASys 架构取舍

以下决策描述的是当前系统真实骨架，不是理想架构。如果通用 best practice 与本部分冲突，优先服从本部分。

### 技术栈真相

| 技术 | 版本 / 方式 | 备注 |
|------|------------|------|
| React | 19.1 | 利用并发特性，但 `use` 钩子目前使用较少 |
| TypeScript | 5.9 | 严格类型 |
| Tailwind CSS | 4 | 原子化样式，禁止内联 style |
| 路由 | 自定义手动路由 | 基于 `window.history`，无 React Router |
| 状态管理 | React Context + 自定义 Hooks | 无 Redux / Zustand / Jotai |
| API 层 | 基于 fetch 的 `httpClient` | 位于 `src/lib/api/` |
| UI 组件 | shadcn/ui + Radix UI | 位于 `src/components/ui/` |
| 构建 | Vite | 标准配置 |

### 核心取舍

**1. 手动路由 vs React Router**

当前使用自定义路由，在 `App.tsx` 中通过 `useState` 监听 `location.pathname` 和 `search`，暴露 `appNavigate` 全局函数。

取舍原因：
- 路由极简单（仅 10 个以内顶层页面）
- 不需要嵌套路由、路由守卫、loader 等复杂能力
- 自定义路由更轻量，能统一处理 overlay 弹层与 legacy path 重定向

要求：
- 新页面必须在 `App.tsx` 中手动注册 lazy import 和路由匹配
- 禁止引入 React Router、TanStack Router 等第三方路由库
- 页面间跳转统一使用 `window.appNavigate?.(path)` 或直接操作 `window.history`

**2. Context + Hooks vs 全局状态管理库**

没有 Zustand/Redux/MobX。全局状态只有 `AuthContext`，其余全部是页面级 / 组件级自定义 hooks。

取舍原因：
- 系统状态天然按页面隔离（分析页、设置页、知识页互不共享）
- 引入全局状态库会增加不必要的抽象和依赖
- 当前模式在页面内部通过 hook composition 已经能表达复杂状态

要求：
- 单页面状态放在 `pages/xxx/hooks/`
- 跨 2-3 个组件但仍在同一页面内的状态，放在该页面的 `hooks/` 或 `components/` 下
- 只有真正跨页面、跨工作区的状态才能进 `src/contexts/` 或 `src/hooks/` 全局层
- 禁止为了"规范"而把局部状态抬到全局

**3. 自定义 httpClient vs Axios / TanStack Query**

`src/lib/api/httpClient.ts` 封装了基于 `fetch` 的请求逻辑，各模块在 `src/lib/api/` 下按领域拆分。

取舍原因：
- fetch 原生支持已足够，无需引入 axios
- 没有复杂的缓存、去重、后台刷新需求，暂时不需要 TanStack Query

要求：
- 新增后端接口时，先在 `src/lib/api/` 下找到对应领域文件补充函数
- 没有对应文件则新建一个以领域命名的 ts 文件
- 统一通过 `apiFetch` 发起请求
- 禁止在组件内部直接写 `fetch(url)` 或引入 axios

**4. Feature-Folder 的适用范围**

只有复杂页面采用 Feature-Folder（`pages/WorkspacePage/components/`、`hooks/`），简单页面仍是单文件。

取舍原因：简单页面（如 `SettingsPage`、`LoginPage`）保持扁平更直观。只有当一个页面超过 3 个专属组件或 3 个专属 hooks 时，才启用 Feature-Folder。

要求：
- 新建页面默认在 `pages/` 下放一个 `index.tsx`
- 复杂度增长时再拆出 `components/` 和 `hooks/`
- 不要一开始就创建过度嵌套的目录

### 目录结构规范

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
│   ├── WorkspacePage/
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

禁止的行为：
- 不要在 `components/` 下创建与页面完全绑定的组件（应放到对应页面的 `components/` 下）
- 不要把 API 类型和业务类型混在 `types/` 里不动脑分类
- 不要把路由守卫逻辑散落在各个页面（统一在 `App.tsx` 或 `components/auth/RouteGuard.tsx`）

### 状态管理分层

**全局层（src/contexts/、src/hooks/）**：只放当前认证用户、当前任务工作区主键、全局事件流（SSE）连接状态。

**页面层（pages/xxx/hooks/）**：页面内列表数据、筛选条件、查询结果、页面级弹窗开关、页面内表单状态、页面级副作用协调。

**组件层**：局部 UI 状态（hover、展开/折叠、内部 tab 索引）、不跨组件的表单输入。

### 路由与导航

主要路由（App.tsx 中硬编码）：
- `/` -> HomePage
- `/workspace` -> WorkspacePage（核心页面，带 overlay 参数）
- `/knowledge/*` -> 知识库相关页面
- `/settings/*` -> 设置中心
- `/login` -> LoginPage

导航方式：

```tsx
// 推荐：使用全局暴露的 navigate
window.appNavigate?.("/workspace?session_id=123");

// 或直接使用 history API
window.history.pushState({}, "", "/workspace");
window.dispatchEvent(new PopStateEvent("popstate"));
```

Overlay 弹层路由：AIASys 大量使用 overlay 参数控制弹层（`/workspace?overlay=database`），让弹层与 URL 同步同时不脱离当前页面上下文。新增需要在 URL 中保留状态的弹层，优先沿用 overlay 参数模式。

### API 层规范

`httpClient.ts` 已统一提取错误信息（优先读取 `detail`，其次 `message`，最后 `error`）。组件中调用 API 时不要自己再写一层错误消息解析。

类型定义：API 请求/响应类型优先放在 `src/types/api.ts` 或页面级 `types.ts`，不要把后端 schema 直接 copy 到前端。

---

## 第二部分：实现规范

### 组件开发

**函数组件模板：**

```tsx
import { useState, useCallback } from "react";
import { cn } from "@/lib/utils";

interface MyComponentProps {
  title: string;
  onAction?: () => void;
  className?: string;
}

export function MyComponent({ 
  title, 
  onAction, 
  className 
}: MyComponentProps) {
  const [isLoading, setIsLoading] = useState(false);

  const handleClick = useCallback(async () => {
    if (isLoading) return;
    setIsLoading(true);
    try {
      await onAction?.();
    } finally {
      setIsLoading(false);
    }
  }, [onAction, isLoading]);

  return (
    <div className={cn("rounded-lg border p-4", className)}>
      <h2 className="text-lg font-semibold">{title}</h2>
      <button
        onClick={handleClick}
        disabled={isLoading}
        className={cn(
          "mt-2 rounded-md px-4 py-2",
          "bg-primary text-primary-foreground",
          "hover:bg-primary/90",
          "disabled:opacity-50 disabled:cursor-not-allowed"
        )}
      >
        {isLoading ? "处理中..." : "执行"}
      </button>
    </div>
  );
}
```

**类名管理**：必须使用 `cn()` 工具函数。禁止内联 `style={{ ... }}`，禁止 className 里写模板字符串拼接。

**组件放置规则**：
- 基础交互组件（Button、Input、Dialog、Card、Select）必须使用 shadcn/ui
- 跨页面通用组件放 `src/components/`
- 页面专属组件放 `pages/xxx/components/`
- 自定义组件在 shadcn 基础上包装，不要从零写基础样式

跨页面组件判断标准（满足 2 条以上）：
- 明确被 2 个以上页面使用
- 不依赖特定页面的业务类型
- 具备通用语义（如 `DataTable`、`Sidebar`、`ChatArea`）

### 异步状态与竞态防护

```tsx
import { useState, useEffect, useRef, useCallback } from "react";

function useAsyncData<T>(fetcher: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const execute = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsLoading(true);
    setError(null);
    try {
      const result = await fetcher();
      if (!controller.signal.aborted) {
        setData(result);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err as Error);
      }
    } finally {
      if (!controller.signal.aborted) {
        setIsLoading(false);
      }
    }
  }, [fetcher]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  return { data, isLoading, error, execute };
}
```

竞态防护三种方案：
1. AbortController（推荐）
2. 请求序号（`let currentRequest = ++requestIdRef.current`）
3. 自定义 hook 封装

### 请求锁模式

```tsx
function useRequestLock() {
  const isRunningRef = useRef(false);

  const withLock = useCallback(async <T>(fn: () => Promise<T>): Promise<T | undefined> => {
    if (isRunningRef.current) return undefined;
    isRunningRef.current = true;
    try {
      return await fn();
    } finally {
      isRunningRef.current = false;
    }
  }, []);

  return { withLock, isRunning: () => isRunningRef.current };
}
```

### 乐观更新

适用场景：删除列表项、切换收藏/启用状态、轻量级排序或局部标记。

不适合：高风险写操作、影响权限判断或审批流程的操作、无法明确回滚的复杂联动写入。

模式：先立即更新 UI → 再发起真实请求 → 失败时回滚并给出可见错误。

### Tailwind CSS 4

布局：
```tsx
<div className="flex items-center justify-between gap-4">
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
```

设置类界面布局：左侧导航 + 右侧内容。左栏承接分类导航，右栏独立滚动。窄屏允许折叠但不要摊平成超长表单。

```tsx
<DialogContent className="h-[90vh] max-h-[90vh] max-w-6xl grid-rows-[auto_minmax(0,1fr)] overflow-hidden p-0">
  <DialogHeader className="border-b px-6 py-5">
    <DialogTitle>工作区设置</DialogTitle>
  </DialogHeader>
  <div className="grid min-h-0 flex-1 grid-cols-[220px_minmax(0,1fr)] overflow-hidden">
    <aside className="border-r px-3 py-4">
      <nav className="space-y-1">
        <button className="w-full rounded-lg px-3 py-2 text-left">基础信息</button>
        <button className="w-full rounded-lg px-3 py-2 text-left">能力与工具</button>
      </nav>
    </aside>
    <section className="min-h-0 overflow-y-auto px-6 py-5">
      {/* 当前分组内容 */}
    </section>
  </div>
</DialogContent>
```

颜色：使用 CSS 变量（`bg-background`、`text-foreground`、`bg-primary`、`bg-muted`），状态色（`text-destructive`、`text-green-600`）。

### React 19 新特性

```tsx
import { use, useTransition } from "react";

// use Hook：读取 Promise 或 Context
function Comments({ commentsPromise }) {
  const comments = use(commentsPromise);
  return comments.map(comment => <p key={comment.id}>{comment.text}</p>);
}

// useTransition：标记非紧急更新
function SearchResults() {
  const [isPending, startTransition] = useTransition();
  const [results, setResults] = useState([]);

  const handleSearch = (query) => {
    startTransition(() => {
      setResults(search(query));
    });
  };

  return (
    <>
      <input onChange={e => handleSearch(e.target.value)} />
      {isPending ? <Spinner /> : <Results data={results} />}
    </>
  );
}
```

---

## 第三部分：性能优化规则

以下规则来自 Vercel Engineering 的 React 性能优化指南，已适配 AIASys 的 Vite + React 19 栈。Next.js/RSC 专用规则已排除。

### 优先级分类

| 优先级 | 类别 | 影响 |
|--------|------|------|
| 1 | 消除请求瀑布（Waterfall） | 关键 |
| 2 | Bundle 体积优化 | 关键 |
| 3 | 客户端数据获取 | 中高 |
| 4 | 重渲染优化 | 中 |
| 5 | 渲染性能 | 中 |
| 6 | JavaScript 性能 | 低中 |
| 7 | 高级模式 | 低 |

### 1. 消除请求瀑布

- `async-cheap-condition-before-await`：先检查同步条件，再 await
- `async-defer-await`：把 await 移到实际使用的分支里
- `async-parallel`：独立操作用 Promise.all()
- `async-suspense-boundaries`：用 Suspense 流式渲染内容

### 2. Bundle 体积优化

- `bundle-barrel-imports`：直接导入，避免 barrel 文件
- `bundle-dynamic-imports`：用 React.lazy() + Suspense 加载重型组件
- `bundle-defer-third-party`：分析/日志脚本延迟到 hydration 后加载
- `bundle-conditional`：只在功能激活时加载对应模块
- `bundle-preload`：hover/focus 时预加载

### 3. 客户端数据获取

- `client-swr-dedup`：用 SWR 或类似机制自动去重请求
- `client-event-listeners`：全局事件监听器去重
- `client-passive-event-listeners`：scroll 用 passive 监听器

### 4. 重渲染优化

- `rerender-defer-reads`：不要把只在回调里用的状态订阅到组件
- `rerender-memo`：昂贵计算提取到 memoized 组件
- `rerender-memo-with-default-value`：非原始类型默认值提升到组件外
- `rerender-dependencies`：effect 依赖用原始值而非对象
- `rerender-derived-state`：订阅派生布尔值，不是原始值
- `rerender-derived-state-no-effect`：在 render 阶段派生状态，不在 effect 里
- `rerender-functional-setstate`：用函数式 setState 获得稳定回调
- `rerender-lazy-state-init`：useState 传函数初始化昂贵值
- `rerender-simple-expression-in-memo`：简单原始值不要 memo
- `rerender-split-combined-hooks`：独立依赖的 hook 拆开
- `rerender-move-effect-to-event`：交互逻辑放 event handler，不放 effect
- `rerender-transitions`：非紧急更新用 startTransition
- `rerender-use-deferred-value`：用 useDeferredValue 延迟昂贵渲染
- `rerender-use-ref-transient-values`：高频瞬态值用 ref
- `rerender-no-inline-components`：不要在组件内定义组件

### 5. 渲染性能

- `rendering-content-visibility`：长列表用 content-visibility
- `rendering-hoist-jsx`：静态 JSX 提到组件外
- `rendering-conditional-render`：用三元而不是 `&&` 做条件渲染
- `rendering-usetransition-loading`：优先用 useTransition 展示 loading 状态

### 6. JavaScript 性能

- `js-batch-dom-css`：通过 class 或 cssText 批量修改 CSS
- `js-index-maps`：重复查找时建 Map
- `js-cache-property-access`：循环中缓存对象属性
- `js-cache-function-results`：模块级 Map 缓存函数结果
- `js-combine-iterations`：多个 filter/map 合并成一次循环
- `js-early-exit`：函数尽早 return
- `js-hoist-regexp`：正则提到循环外
- `js-set-map-lookups`：用 Set/Map 做 O(1) 查找

### 7. 高级模式

- `advanced-effect-event-deps`：useEffectEvent 结果不放进 effect 依赖
- `advanced-event-handler-refs`：事件处理器存 ref
- `advanced-init-once`：应用初始化只执行一次
- `advanced-use-latest`：用 useLatest 获取稳定回调 ref

---

## 第四部分：运行时验证

前端改动必须在真实浏览器中验证，不能仅凭代码推断。

验证项目：
- 截图对比：改动前后分别截图
- Console 检查：页面加载和交互后控制台零错误、零警告
- Network 分析：确认 API 请求 URL、方法、payload、响应状态正确
- Performance Trace：检查 LCP、INP、CLS
- Accessibility Tree：确认交互元素有正确的 accessible name

---

## 快速检查清单

**创建组件时：**
- [ ] Props 有 TypeScript 类型定义
- [ ] 使用 `cn()` 合并类名
- [ ] 支持 `className` prop
- [ ] 处理加载状态和错误状态

**实现异步逻辑时：**
- [ ] 使用请求锁防止重复提交
- [ ] 组件卸载时取消请求
- [ ] 处理竞态条件

**样式编写时：**
- [ ] 使用 Tailwind 类名
- [ ] 使用主题变量（background, foreground 等）
- [ ] 响应式设计

**新增页面时：**
- [ ] 已在 `App.tsx` 中注册 lazy import 和路由匹配
- [ ] 页面复杂度不高时保持单文件，必要时再拆 Feature-Folder
- [ ] 页面级 hooks 放在 `pages/xxx/hooks/`

**新增 API 调用时：**
- [ ] 已检查 `src/lib/api/` 下是否有对应领域文件
- [ ] 使用 `apiFetch` 或该文件封装好的函数
- [ ] 未在组件内直接写裸 fetch

**新增状态时：**
- [ ] 先判断是否真的需要全局状态
- [ ] 局部状态优先放在最近的使用层级
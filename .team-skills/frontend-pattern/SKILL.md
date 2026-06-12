---
name: frontend-pattern
description: |
  React 19 前端开发模式规范。当需要创建 React 组件、实现页面、处理状态管理或处理异步操作与竞态条件时触发。
  适用于 React 19 模式、Tailwind CSS 4 使用、shadcn/ui 集成、并发保护。
  不适用于非 React 框架（如 Vue、Angular）、纯 CSS/HTML 页面、与 AIASys 设计系统无关的独立组件开发。
---

# 前端开发模式

基于 React 19 + Tailwind CSS 4 + shadcn/ui 的专业前端开发指南。

---

## 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 19 | UI 框架，利用并发特性 |
| TypeScript | 5.9 | 类型安全 |
| Tailwind CSS | 4 | 原子化样式 |
| shadcn/ui | Latest | 组件库 |
| Radix UI | Latest | Headless UI 基座 |

---

## 项目规范

### 核心规则

1. **React 19 优先**：利用并发特性，`use` 钩子当前代码中暂未使用，属可选特性
2. **Tailwind 4 标准**：统一使用原子化样式类，禁止内联样式
3. **禁止代码污染**：严禁在注释中描述"未来计划"或"TODO"
4. **Feature-Folder 架构**：大型页面应有 `components/` 与 `hooks/` 子目录
5. **手动路由优先**：新页面需在 `App.tsx` 手动注册
6. **竞态防护**：副作用操作必须使用请求锁

### 前置依赖门禁

- 默认顺序：后端能力就绪 → 前端接入 → 联调验收
- 后端接口未就绪时，前端任务不得标记为"成功完成"
- 仅在用户明确同意时才允许 Mock 先行，且状态必须标记为"部分成功"

### 产品文案边界

- 前端渲染文案只写用户真正需要看到的产品内容
- 不要把内部治理规则、迁移说明、开发注释、重构背景直接渲染到界面里
- 需要解释实现意图时，写代码注释、架构文档或 Skill 规则，不写进用户可见文案
- 用户界面文案优先回答“这里能做什么”“从这里会去哪里”，不要写“为什么我们内部这样重构”

---

## 组件开发

### 函数组件模板

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

### 类名管理

**必须使用 `cn()` 工具函数：**

```tsx
import { cn } from "@/lib/utils";

// 正确： 正确
<div className={cn("base-class", condition && "conditional-class", className)}>

// 错误： 错误
<div className={`base-class ${condition ? "conditional" : ""} ${className}`}>

// 错误： 错误
<div className="base-class" style={{ marginTop: 10 }}>
```

### 组件文件组织

```
src/
├── components/
│   ├── ui/                 # shadcn/ui 组件
│   │   ├── button.tsx
│   │   └── card.tsx
│   └── custom/             # 自定义组件
│       ├── DataTable/
│       │   ├── index.tsx
│       │   ├── types.ts
│       │   └── utils.ts
│       └── Sidebar/
├── pages/
│   └── Dashboard/
│       ├── index.tsx
│       ├── components/     # 页面专属组件
│       │   ├── StatCard.tsx
│       │   └── Chart.tsx
│       └── hooks/          # 页面专属 hooks
│           └── useStats.ts
└── hooks/                  # 全局 hooks
    └── useAsync.ts
```

---

## 状态管理

### 本地状态

```tsx
// 简单状态
const [count, setCount] = useState(0);

// 对象状态
const [form, setForm] = useState({ name: "", email: "" });

// 更新对象
setForm(prev => ({ ...prev, name: "new name" }));
```

### 异步状态（带竞态防护）

```tsx
import { useState, useEffect, useRef, useCallback } from "react";

function useAsyncData<T>(fetcher: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const execute = useCallback(async () => {
    // 取消之前的请求
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

### 状态分层

状态默认按离使用位置最近的层级放置：

- 全局状态：只放真正跨页面、跨工作区都需要共享的状态，例如当前用户、认证态、当前任务工作区主键
- 页面状态：放页面级列表、筛选、查询结果、资源摘要
- 组件状态：放弹窗开关、表单输入、局部 loading、局部错误

如果一个状态只服务单个弹层或单个组件，不要先抬到全局。

### 乐观更新

对用户感知明显、且失败可回滚的操作，优先使用乐观更新：

1. 先立即更新 UI，减少等待感
2. 再发起真实请求
3. 失败时回滚并给出可见错误

适用场景：

- 删除列表项
- 切换收藏 / 启用状态
- 轻量级排序或局部标记

不适合的场景：

- 高风险写操作
- 会影响后续权限判断或审批流程的操作
- 无法明确回滚的复杂联动写入

### 请求锁模式

```tsx
import { useState, useCallback, useRef } from "react";

function useRequestLock() {
  const isRunningRef = useRef(false);

  const withLock = useCallback(async <T>(fn: () => Promise<T>): Promise<T | undefined> => {
    if (isRunningRef.current) {
      return undefined;
    }
    
    isRunningRef.current = true;
    try {
      return await fn();
    } finally {
      isRunningRef.current = false;
    }
  }, []);

  return { withLock, isRunning: () => isRunningRef.current };
}

// 使用示例
function MyComponent() {
  const { withLock } = useRequestLock();
  const [data, setData] = useState(null);

  const handleSubmit = useCallback(async () => {
    await withLock(async () => {
      const result = await api.submit(data);
      setData(result);
    });
  }, [data, withLock]);

  return <button onClick={handleSubmit}>提交</button>;
}
```

---

## 竞态防护

### 问题场景

```tsx
// 错误： 问题：快速切换时，旧请求可能晚于新请求返回
useEffect(() => {
  fetchData(id).then(setData);
}, [id]);
```

### 解决方案

```tsx
// 正确： 方案 1：AbortController
useEffect(() => {
  const controller = new AbortController();
  
  fetchData(id, { signal: controller.signal })
    .then(setData)
    .catch(err => {
      if (err.name !== "AbortError") {
        setError(err);
      }
    });
  
  return () => controller.abort();
}, [id]);

// 正确： 方案 2：请求序号
useEffect(() => {
  let currentRequest = ++requestIdRef.current;
  
  fetchData(id).then(result => {
    if (currentRequest === requestIdRef.current) {
      setData(result);
    }
  });
}, [id]);

// 正确： 方案 3：自定义 hook
const { data, isLoading } = useFetch(() => fetchData(id), [id]);
```

---

## Tailwind CSS 4 使用

### 布局模式

```tsx
// Flexbox
<div className="flex items-center justify-between gap-4">

// Grid
<div className="grid grid-cols-3 gap-4">

// 响应式
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
```

### 设置类界面布局

设置 / 配置类页面默认采用“左侧导航 + 右侧内容”。

- 左栏承接分类导航、分组切换、局部状态摘要
- 右栏承接当前分组的说明、表单、开关和操作
- 右栏独立滚动，避免整个页面或整个弹窗一起滚
- 窄屏允许折叠成“上方分组选择 + 下方内容区”，但不要把所有设置重新摊平成一个超长表单

设置类弹窗也沿用同一骨架，不要默认用顶部一排 tab 承接主导航。

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
        <button className="w-full rounded-lg px-3 py-2 text-left">资源</button>
      </nav>
    </aside>

    <section className="min-h-0 overflow-y-auto px-6 py-5">
      {/* 当前分组的设置内容 */}
    </section>
  </div>
</DialogContent>
```

### 间距系统

```tsx
// 基础单位 4px
// 4, 8, 12, 16, 20, 24, 32, 48, 64...

<div className="p-4">           {/* padding: 16px */}
<div className="m-2">           {/* margin: 8px */}
<div className="gap-4">         {/* gap: 16px */}
<div className="space-y-2">     {/* > * + * margin-top: 8px */}
```

### 颜色与主题

```tsx
// 使用 CSS 变量（由 shadcn/ui 提供）
<div className="bg-background text-foreground">
<div className="bg-primary text-primary-foreground">
<div className="bg-secondary text-secondary-foreground">
<div className="bg-muted text-muted-foreground">

// 状态色
<div className="text-destructive bg-destructive/10">  {/* 错误 */}
<div className="text-green-600 bg-green-50">          {/* 成功 */}
```

### 条件样式

```tsx
<button
  className={cn(
    "rounded-md px-4 py-2 font-medium",
    variant === "primary" && "bg-primary text-white hover:bg-primary/90",
    variant === "secondary" && "bg-secondary text-secondary-foreground",
    isDisabled && "opacity-50 cursor-not-allowed",
    isLoading && "relative text-transparent"
  )}
>
  {children}
</button>
```

---

## shadcn/ui 使用

### 安装组件

```bash
npx shadcn add button
npx shadcn add card
npx shadcn add dialog
```

### 常用组件示例

```tsx
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

// Button
<Button variant="default" size="sm">提交</Button>
<Button variant="outline" disabled>禁用</Button>

// Card
<Card>
  <CardHeader>
    <CardTitle>标题</CardTitle>
  </CardHeader>
  <CardContent>内容</CardContent>
</Card>

// Dialog
<Dialog open={isOpen} onOpenChange={setIsOpen}>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>确认删除</DialogTitle>
    </DialogHeader>
    <p>确定要删除此项吗？</p>
  </DialogContent>
</Dialog>
```

---

## React 19 新特性

### use Hook

```tsx
import { use } from "react";

// 读取 Promise
function Comments({ commentsPromise }) {
  const comments = use(commentsPromise);
  return comments.map(comment => <p key={comment.id}>{comment.text}</p>);
}

// 读取 Context
function ThemeComponent() {
  const theme = use(ThemeContext);
  return <div className={theme}>...</div>;
}
```

### useTransition

```tsx
import { useTransition } from "react";

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

## 运行时验证（DevTools MCP）

前端改动必须在真实浏览器中验证，不能仅凭代码推断。

### 验证项目

- **截图对比**：改动前后分别截图，确认视觉输出符合预期
- **Console 检查**：页面加载和交互后控制台应零错误、零警告
- **Network 分析**：确认 API 请求 URL、方法、payload、响应状态正确
- **Performance Trace**：检查 LCP、INP、CLS，确认无明显回归
- **Accessibility Tree**：确认交互元素有正确的 accessible name 和层级

### 使用方式

当项目配置了 Chrome DevTools MCP 时，在验证阶段主动调用：

1. 启动前端开发服务器
2. 导航到目标页面
3. 执行需要验证的交互
4. 读取 DevTools 数据作为验收证据

---

## 快速检查清单

**创建组件时：**
- [ ] Props 有 TypeScript 类型定义
- [ ] 使用 `cn()` 合并类名
- [ ] 支持 `className` prop
- [ ] 处理加载状态
- [ ] 处理错误状态

**实现异步逻辑时：**
- [ ] 使用请求锁防止重复提交
- [ ] 组件卸载时取消请求
- [ ] 处理竞态条件
- [ ] 提供取消/重置能力

**样式编写时：**
- [ ] 使用 Tailwind 类名
- [ ] 使用主题变量（background, foreground 等）
- [ ] 响应式设计
- [ ] 无障碍状态（focus, disabled）

---

## 关联参考

- 复杂 UI 状态流设计规范参见 `references/state-flow.md`

---

*前端是用户直接接触的界面——追求像素级还原与流畅体验。*

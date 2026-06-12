# 浏览器标签页功能实现

> 创建：2026-06-12 · 状态：已完成

## 目标

在 AIASys 工作区的 tab 系统里新增"浏览器视图"tab 类型，支持：
1. 打开本地 HTML 文件（工作区内的 .html 文件在 iframe 里渲染）
2. 打开外部 URL（http/https，受 iframe 同源策略限制）
3. 入口：tab bar "+" 下拉菜单 + 文件树右键 HTML 文件

## 实施结果

所有 7 项任务已完成，TypeScript 编译通过，Vite build 成功。

### 改动的文件

```
apps/web/src/pages/WorkspacePage/components/WorkspaceLayout/
  components/WorkspaceTabBar.tsx   — WorkspaceTab 加 url 字段；+ 按钮变下拉菜单；加 URL 输入弹窗
  usePaneTree.ts                  — 新增 openBrowserTab(url)
  PaneRenderer.tsx                — 新增 BrowserTabView 组件（iframe + sandbox + 地址栏）
  MainContent.tsx                 — 串联 onNewBrowserTab / onOpenInBrowserTab

apps/web/src/components/
  layout/WorkspaceSidebar/
    FileTreeContextMenus.tsx       — HTML 文件右键加"在浏览器标签页打开"
    FileTreeView.tsx              — 透传 onOpenInBrowserTab
    WorkspaceAssetPanel.tsx       — 透传 onOpenInBrowserTab
    index.tsx                    — 透传 onOpenInBrowserTab
  artifacts/
    WorkspaceArtifactRenderer.tsx — UnsupportedArtifact 对 HTML 显示"在浏览器打开"
  chat/
    ChartAwareMarkdown.tsx        — 透传 onOpenInBrowserTab
    AiMessageContent/index.tsx    — 透传 onOpenInBrowserTab 到所有 ChartAwareMarkdown 调用点
    AiMessageContent/
      context.tsx                 — AiMessageMeta 加 onOpenInBrowserTab 字段
      StreamingThoughtBlock.tsx   — 从 context 读取 onOpenInBrowserTab 传给 ChartAwareMarkdown
      ToolBlock.tsx               — 从 context 读取 onOpenInBrowserTab 传给 ChartAwareMarkdown
      FinalAnswerBlock.tsx        — 从 context 读取 onOpenInBrowserTab 传给 ChartAwareMarkdown
```

### 用户交互

1. Tab bar "+" → 下拉 → "浏览器视图" → 输入 URL/路径 → 新 tab
2. 文件树右键 HTML → "在浏览器标签页打开"
3. Chat HTML artifact → "在浏览器打开"按钮（主聊天流、思考块、工具块、最终回答全链路覆盖）
4. 浏览器 tab 顶部地址栏：本地路径（琥珀色）/ 外部 URL（紫色）

### 文档更新

- `design-draft/design/design-thinking/121-浏览器标签页功能设计决策.md`
- `design-draft/design/frontend/界面设计/工作区壳层/文件预览支持矩阵.md`

### 后续可能

- 桌面端可考虑 `<webview>` 绕过 iframe 同源限制
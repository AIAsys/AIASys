# 通用 UI 组件 (Generic UI Components)

本目录存放了跨页面复用的通用 UI 组件。这些组件不绑定于特定的业务页面（尽管有些可能主要用于特定场景，但设计上是可复用的）。

## 目录结构

- **`ui/`**: 存放基于 Shadcn UI 或 Radix UI 封装的基础原子组件（如 Button, Input, Dialog 等）。
- **`ui_design/`**: 存放特定设计风格的侧边栏或其他设计相关的复合组件。
- **`layout/WorkspaceSidebar/`**: `/analysis` 工作区侧栏与中间工作台资源面板。

## 核心组件说明

### 交互与输入

- **`ChatInput.tsx`**: 聊天输入框组件，支持文本输入和发送操作。
- **`FileUpload*.tsx`**: 文件上传相关组件套件（列表、单项、Toast 提示等）。
- **`PasswordInput.tsx`**: 带显示/隐藏功能的密码输入框。

### 展示与反馈

- **`AiResponse*.tsx`**: AI 响应内容的展示组件，支持 Markdown 渲染和流式输出。
- **`MessageList.tsx`**: 聊天消息列表容器。
- **`ToolCard.tsx` / `ToolComponent.tsx`**: 工具展示卡片。

### 模态框与侧边栏

- **`layout/WorkspaceSidebar/`**: 工作区侧栏、资源树、预览面板和执行空间入口。
- **`layout/DesignSidebar.tsx`**: 设计与历史会话管理侧边栏。

### 其他

- **`Login.tsx`**: 登录表单组件。

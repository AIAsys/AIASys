# Changelog

## [v0.1.5-dev] - 2026-02-16 - 代码整理与架构优化

### 新增功能

#### 后端
- **执行日志服务** (`execution_logger.py`): 记录 Host/SubAgent 的详细执行事件流
- **历史记录 API 增强** (`sessions.py`): 返回统一格式的消息历史，保持 SDK 的 think/text 字段结构
- **文件下载增强** (`files.py`): 支持从 `work/` 子目录和会话根目录两个位置查找文件

#### 前端
- **HTML 图片标签支持**: 自动将 `<img src="/workspace/xxx.png">` 转换为 Markdown 格式并正确渲染
- **历史记录渲染统一**: 使用 SDK content 直接构建 segments，保持与流式输出一致的渲染效果
- **品牌标识更新**: 新增斧头 logo favicon，页面标题改为"天工-AIASys"

### 改进

#### 后端
- **Agent Service**: 记录 Host Agent 的 think 事件到 execution 日志
- **Session Manager**: 添加文件快照功能
- **Prompt 优化**: 更新数据分析 prompt，改进图片引用格式

#### 前端
- **useSessionManagement**: 简化历史加载逻辑，删除复杂的 execution events 映射
- **AiMessageContent**: 支持 MarkdownImage 组件，统一处理图片路径
- **FinalAnswerBlock**: 添加 HTML img 到 Markdown 的预处理转换
- **资源文件整理**: 重命名 `087dbe049a431b763e2ac46a6a9df530 1.svg` 为 `logo.svg`

### 修复

- **历史记录 think 丢失**: 后端 API 返回的 content 字段名与 SDK 保持一致 (think/text)
- **图片无法渲染**: 后端文件下载支持从多个位置查找，前端支持 HTML img 标签
- **用户消息 content 格式**: 字符串内容包装为 `text` 字段而非 `content`

### 删除

- 删除 `docs/ai-coding-prompts/` 目录（迁移到 .agents/skills/）
- 删除 `docs/workflow/` 目录
- 删除 `apps/backend/app/agents/tools/ipython_tool_old.py`
- 删除 `apps/backend/app/cli.py`
- 删除 `apps/backend/docker_ipython.py`
- 删除 `apps/backend/start.py`
- 删除 `docs/IMPLEMENTATION_STATUS.md`
- 删除 `docs/weekly-report_2026-02-02.md`
- 删除 Docker rootfs 缓存文件
- 删除 `apps/web/src/assets/react.svg`（未使用）
- 删除 `apps/web/src/assets/images/background.png`（未使用）

## 技术债务

- [ ] execution_logger 中 Host think 事件记录需要验证是否完整
- [ ] 消息时间戳分配逻辑可以优化（基于 tool_calls 匹配）
- [ ] 前端控制台日志需要清理（buildSegmentsFromContent 等）

## 下一步计划

### 1. 前端交互优化
- [ ] 消息加载骨架屏
- [ ] 虚拟滚动优化长对话性能
- [ ] 图片懒加载

### 2. SSO 接入
- [ ] 研究 Authentik/OpenID Connect 集成方案
- [ ] 后端 JWT 认证改造
- [ ] 前端登录页面
- [ ] 用户权限管理

### 3. 代码质量
- [ ] 前端单元测试补充
- [ ] API 文档同步更新
- [ ] 性能监控接入

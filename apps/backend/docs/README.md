# Backend 文档索引

本目录只保留 `apps/backend` 侧的人类可读专题说明。内容以源码为准，不应替代：

- `apps/backend/app/` 中的真实实现

## 推荐入口

### 先看这些

- `api.md`
  当前后端 API 与主要路由口径
- `authentication.md`
  认证模式、会话与鉴权边界
- `workspace.md`
  会话目录、工作区、文件存储相关设计

- `../DOCKER_IMAGE.md`
  当前 Docker 官方镜像、构建命令与初始化规则

### 当前源码优先专题

- `app/api/routes/files.py`
  工作区文件、ZIP 导出、Markdown 导出
- `message_rendering_architecture.md`
  当前消息渲染链路补充说明
- `file_watching.md`
  文件变更监听与同步
- `llm_config.md`
  LLM 配置与模型解析

### 历史材料

- `subagent_task_design.md`
  早期 Task / SubAgent 设计稿，含旧运行时示例，不作为当前事实来源
- `frontend_display.md`
  早期前端展示草稿，工具名与消息样例只作历史参考

## 使用边界

1. 文档只解释背景和设计，不作为最终事实来源。
2. 遇到路由、端口、鉴权、工作区路径冲突时，优先回源码核对。
3. 影响 AI 判断“是否完成”的内容，应该同步到项目协作规范，不要只留在这里。
4. `RAG`、`GraphRAG`、`Markdown 导出`、`偏好记忆` 这些近期变化较多的模块，优先回源码和产品需求总台账核对。
5. 标记为“历史材料”的文档只保留设计演进背景，不应用来判断当前工具面、模块路径或运行时行为。

## 常用验证命令

```bash
cd apps/backend
uv sync
AUTH_MODE=local uv run uvicorn app.main:app --reload --port 13001
```

```bash
cd apps/backend
uv run pytest -v
```

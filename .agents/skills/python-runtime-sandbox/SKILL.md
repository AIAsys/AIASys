---
name: python-runtime-sandbox
description: |
  AIASys 的 Python 运行时与沙盒执行开发指南。覆盖 IPython Kernel 执行工具、UV 虚拟环境管理、
  执行计划解析、代码改写与路径注入、Docker 沙盒入口等核心模块。用于修改代码执行逻辑、
  新增运行时环境类型、或调整沙盒安全策略时。
---

# Python 运行时与沙盒执行

AIASys 的 Python 代码执行以本地 IPython Kernel 为主，UV 管理依赖环境，Docker 沙盒为可选入口。

---

## IPython Kernel 执行

### LocalIPythonBox

`agents/tools/local_ipython_box.py`（1264 行）是核心的 Python 代码执行工具：

- 使用 `jupyter_client` 启动本地 IPython Kernel
- 每个 session 有独立的 kernel 实例（通过 `MultiKernelManager` 管理）
- 支持魔法命令（`%matplotlib inline`、`%timeit` 等）
- 捕获 matplotlib 图表输出（base64 编码返回）
- 支持富输出（HTML、Markdown、LaTeX）

### 代码执行流程

1. Agent 调用代码执行工具（`RunCode` 或 `LocalIPythonBox`），传入代码字符串
2. `plan_for_python_execution()` 解析执行计划（本地/UV/Docker）
3. `rewrite_local_runtime_code()` 改写代码（路径注入、workspace 映射）
4. `build_local_runtime_bootstrap_code()` 注入引导代码
5. Kernel 执行，收集 stdout/stderr/display_data
6. `sanitize_ansi_text()` 清理 ANSI 转义序列
7. 结果记录到 `SessionExecutionJournal`

### 敏感环境变量过滤

`SENSITIVE_KERNEL_ENV_KEYS` 定义不应传递到 kernel 的敏感变量：

- `AIASYS_EMBEDDING_API_KEY`、`AIASYS_AUTH_JWT_SECRET`
- `KIMI_API_KEY`、`OPENAI_API_KEY`、`OPENAI_BASE_URL`
- 各种 `_PASSWORD`、`_SECRET` 后缀变量

### 数据库运行时访问

`services/database/database_access_broker.py` 提供 kernel 内的数据库查询代理：

- `build_runtime_database_helper_env()` 注入连接凭据
- 通过 broker URL 代理数据库访问，不直接暴露连接字符串

---

## UV 运行环境管理

### 工作区环境

`services/runtime_environment.py` 管理工作区级 UV/Python 虚拟环境：

- 环境目录：`{workspace}/.env/`
- 默认环境 ID：`workspace-default`
- 使用 `pyproject.toml` 声明依赖
- 支持多个命名环境（如 `pytorch`、`tensorflow` 等）

### 环境注册

- `environments.json` 记录所有已注册环境
- 每个环境记录：ID、Python 版本、依赖列表、创建时间
- API 路由：`api/routes/runtime_envs.py` 提供 CRUD

### 环境绑定

- 工作区通过 `RuntimeEnvironmentService` 指定当前使用的环境
- Agent 工具在 `plan_for_python_execution()` 中解析绑定
- 不同 session 可以使用不同环境

---

## 执行计划系统

### RuntimeExecutionPlan

`services/runtime/runtime_execution.py`：

- `RuntimeExecutionPlan` 定义执行计划数据结构
- `plan_for_python_execution()` 函数解析工作区的 runtime binding
- 支持三种模式：`local`（默认）、`docker`、`uv`
- Shell、RunCode、Notebook 工具都从此取执行环境配置

### 代码改写

`services/runtime/execution_support.py`：

- `rewrite_local_runtime_code()`：注入 workspace 路径映射
- `build_local_runtime_bootstrap_code()`：生成环境初始化代码
- `sanitize_ansi_text()`：清理终端 ANSI 转义
- `restore_logical_workspace_path()`：还原逻辑工作区路径

---

## Docker 沙盒

### 当前状态

- `pyproject.toml` 依赖 `docker>=7.1.0`
- `services/container_resource.py` 管理容器资源
- `core/config.py` 中默认 `sandbox_mode="local"`，Docker 不是默认路径
- Shell 工具支持 `container` 参数进入 Docker 沙盒执行

### 当前限制

- 无 CPU/内存/时间资源限制机制
- 无真正的沙盒隔离（本地 kernel 共享主机环境）
- Docker 模式有入口但非完整实现

---

## 执行日志

### SessionExecutionJournal

`services/history/session_execution_journal.py`：

- 记录每次代码执行的完整上下文
- 包含：代码、输出、错误、执行时间、环境信息
- 用于 Memory 子系统的 Stage 1 提炼

---

## 关键文件索引

| 文件 | 职责 |
|------|------|
| `agents/tools/local_ipython_box.py` | IPython Kernel 执行工具 |
| `services/runtime_environment.py` | UV 环境管理 |
| `services/runtime/runtime_execution.py` | 执行计划解析 |
| `services/runtime/execution_support.py` | 代码改写与路径注入 |
| `services/database/database_access_broker.py` | 数据库运行时代理 |
| `services/container_resource.py` | Docker 容器管理 |
| `agents/tools/code_execution_tool.py` | RunCode 等代码执行工具 |
| `agents/tools/shell_tool.py` | Shell 执行工具（含 Docker 入口） |
| `api/routes/runtime_envs.py` | 运行时环境 API |
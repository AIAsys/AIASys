# AIASys 快速启动指南

> 当前版本: v0.3.9

本指南用于帮助新协作者把当前仓库跑起来。当前后端运行配置使用 `apps/backend/config.toml`，前端默认从 `13000` 访问后端 `13001`。

## 1. 前置要求

请先确认本机已经有这些工具：

- Python 3.12+
- [uv](https://astral.sh/uv/)
- Node.js 22+
- npm
- Docker，可选，用于显式登记或创建工作区 Docker 沙盒资源
- Redis，可选，未安装时系统会回退到内存模式

## 2. 准备依赖

```bash
git clone https://github.com/AIAsys/AIASys.git
cd AIASys
```

后端依赖：

```bash
cd apps/backend
[ -f config.toml ] || cp config.example.toml config.toml
uv sync
cd ../..
```

前端依赖：

```bash
cd apps/web
npm ci
cd ../..
```

说明：

- 后端依赖事实源是 `apps/backend/pyproject.toml` 和 `apps/backend/uv.lock`。

- `config.toml` 需要按本机模型、认证和运行时配置补齐。新增项目请优先使用 TOML。

## 3. 启动开发环境

项目根目录提供统一开发启动入口：

```bash
./dev.sh
```

它会同时启动：

- 后端：`http://127.0.0.1:13001`
- 前端：`http://127.0.0.1:13000`

查看状态：

```bash
./dev.sh status
```

停止前台运行的开发服务时，在启动命令所在终端按 `Ctrl+C`。

## 4. 常用配置

### 首次模型配置

首次启动后，需要先配置至少一个可用的 Chat 模型，否则 Agent 对话、自动任务、上下文压缩等需要模型调用的功能无法正常执行。

推荐从界面配置：

1. 打开 `http://localhost:13000/workspace`。
2. 点击左侧边栏底部的`工作区工具`，进入`模型配置`。
3. 点击`添加服务商`，填写服务商的 API 连接信息。
4. 在服务商卡片中点击`测试`，确认 Base URL 和 API Key 可用。
5. 点击`获取模型`批量导入模型；如果服务商不支持模型列表接口，就点击`添加模型`手动填写模型名称。
6. 在`默认模型`里选择默认 Chat 模型，保存后回到分析页开始对话。

服务商配置需要填写：

| 字段 | 说明 | 示例 |
|:---|:---|:---|
| ID | 本地配置标识，只用于系统内部引用 | `kimi`、`my-openai` |
| 名称 | 界面显示名称 | `Kimi`、`OpenAI` |
| Base URL | 服务商 API 地址，通常以 `/v1` 结尾 | `https://api.kimi.com/coding/v1` |
| 类型 | 接口协议格式 | `OpenAI Chat Completions`、`OpenAI Responses`、`Anthropic Messages` |
| API Key | 服务商密钥 | `sk-...` |
| 自定义请求头 | 可选，JSON 格式 | `{"User-Agent":"KimiCLI/1.16.0"}` |
| 环境变量 | 可选，JSON 格式，适合代理配置 | `{"HTTPS_PROXY":"http://127.0.0.1:7890"}` |

模型配置需要填写：

| 字段 | 说明 | 示例 |
|:---|:---|:---|
| 模型类型 | `Chat` 用于对话和 Agent 执行，`Embedding` 用于知识库向量化 | `Chat` |
| 实际模型标识 | API 请求里使用的模型名 | `kimi-for-coding` |
| 显示名称 | 界面里看到的名字 | `Kimi Coding` |
| 最大上下文长度 | 模型上下文窗口大小，单位是 token | `128000` |
| 模型能力 | 按模型实际能力勾选 | `thinking`、`image_in` |

配置完成后，分析页输入框旁边的模型选择器只会显示已启用的 Chat 模型。知识库向量化需要单独配置默认 Embedding 模型。

如果新用户还没有任何可用 Chat 模型，产品内建议直接提示：

> 还没有可用模型。先配置一个 Chat 模型后，AIASys 才能执行对话和自动任务。

这个提示适合放在分析页输入框附近、模型选择器空列表里，以及用户点击发送但没有可用模型时的拦截弹窗里。按钮文案建议用`去配置模型`，点击后打开`模型配置`弹窗。

### 后端配置

```bash
cd apps/backend
vim config.toml
```

关键项示例：

```toml
[server]
host = "0.0.0.0"
port = 13001

[llm]
default_provider = "stepfun"
default_model = "step-3.7-flash"
temperature = 0.6

[llm.providers.stepfun]
type = "openai_chat_completions"
base_url = "https://api.stepfun.com/v1"
api_key = "sk-..."

# 纯文本模型
[[llm.providers.stepfun.models]]
name = "step-router-v1"
max_context_size = 256000
capabilities = []

[[llm.providers.stepfun.models]]
name = "step-3.5-flash"
max_context_size = 200000
capabilities = []

# 多模态模型
[[llm.providers.stepfun.models]]
name = "step-3.7-flash"
max_context_size = 256000
capabilities = ["thinking", "image_in", "video_in"]

[[llm.providers.stepfun.models]]
name = "step-router-v2-pro"
max_context_size = 190000
capabilities = ["thinking", "image_in"]
```

模型配置支持两种写法：

- 字符串数组：`models = ["step-3.7-flash"]`，capabilities 由后端按接口类型推断。
- 对象数组：每个模型可声明 `name`、`max_context_size`、`capabilities`，用于精确区分纯文本模型和多模态模型。

`config.toml` 适合本地首次启动前预置模型。用户配置为空时，后端会把这里的 `llm.providers` 同步到当前用户的全局工作区模型配置中，之后界面上的模型配置会保存到：

```text
workspaces/{user_id}/global_workspace/.aiasys/llm_config.json
```

默认代码执行路径使用本地 UV 运行环境。Docker 不作为默认 `RuntimeEnvironment`，需要在工作区的 Docker 沙盒资源中显式登记已有容器，或按镜像创建容器后再使用。容器通过 `/workspace` 访问工作区文件和产物，容器内系统依赖与 Python 环境由镜像或容器内安装提供。

如果已经在界面里配置过模型，修改 `config.toml` 不会覆盖现有用户配置。需要调整时，优先在界面的`模型配置`里修改。

### 前端配置

单独启动前端时，可以在 `apps/web/` 下覆盖认证模式或后端地址：

```bash
cd apps/web

VITE_AUTH_MODE=local VITE_API_TARGET=http://localhost:13001 npm run dev -- --port 13000
```

用根目录脚本启动时，可以覆盖前端端口：

```bash
AIASYS_FRONTEND_PORT=13010 ./dev.sh
```

## 5. 桌面版快速启动（可选）

如果想用桌面版而不是浏览器：

```bash
cd apps/desktop
npm install
npm run dev
```

桌面版自动管理前后端服务，不需要单独启动 `./dev.sh`。详见 [桌面应用文档](desktop-app.md)。

## 6. 验证运行状态

服务启动后，可以通过以下方式验证（以下 URL 为默认值）：

- 前端界面：[http://localhost:13000](http://localhost:13000)
- 分析页：[http://localhost:13000/workspace](http://localhost:13000/workspace)
- 后端健康检查：

  ```bash
  curl http://localhost:13001/health
  ```

- Docker daemon 状态，可用于判断工作区 Docker 沙盒资源是否可用：

  ```bash
  curl http://localhost:13001/health/docker
  ```

## 7. 常用开发命令

| 任务 | 命令 | 路径 |
|:---|:---|:---|
| 安装后端依赖 | `uv sync` | `apps/backend/` |
| 安装前端依赖 | `npm ci` | `apps/web/` |
| 启动开发环境 | `./dev.sh` | 项目根目录 |
| 查看开发环境状态 | `./dev.sh status` | 项目根目录 |
| 后端启动 | `uv run uvicorn app.main:app --host 0.0.0.0 --port 13001` | `apps/backend/` |
| 前端启动 | `npm run dev` | `apps/web/` |
| 运行后端测试 | `.venv/bin/python -m pytest` | `apps/backend/` |
| 前端构建 | `npm run build` | `apps/web/` |
| 校验视觉基线 | `./dev.sh design-lint` | 项目根目录 |
| 桌面版开发 | `npm run dev` | `apps/desktop/` |
| 桌面版 Linux 打包 | `npm run dist:linux:dir` | `apps/desktop/` |
| 桌面版 Windows 打包 | `npm run dist:win` | `apps/desktop/` |
| 桌面版 macOS 打包 | `npm run dist:mac` | `apps/desktop/` |

---

遇到启动问题时，先看 [../../deployment.md](../../deployment.md)。

---

## 8. 界面预览

启动成功后，你可以访问：

- 首页：`http://localhost:13000`
- 分析工作区：`http://localhost:13000/workspace`

分析工作区是当前主界面，左侧 Activity Bar 提供文件管理、数据查询、自动化任务等功能，右侧聊天侧栏用于与 Agent 对话和查看执行上下文。

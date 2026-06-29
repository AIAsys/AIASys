# LLM 配置与模型解析

当前默认模型配置以 Step 系列模型为优先入口。`apps/backend/config.example.toml` 默认使用：

```toml
[llm]
default_provider = "stepfun"
default_model = "step-3.7-flash"
temperature = 0.6

[llm.providers.stepfun]
type = "openai_chat_completions"
base_url = "https://api.stepfun.com/v1"
api_key = "your-stepfun-api-key"

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
```

系统按接口协议识别服务商，当前支持：

| 类型 | 用途 |
|------|------|
| `openai_chat_completions` | OpenAI Chat Completions 兼容接口，Step、DashScope 等走这个协议 |
| `openai_responses` | OpenAI Responses 兼容接口 |
| `anthropic_messages` | Anthropic Messages 兼容接口，Kimi Coding API 走这个协议 |

其他服务商（OpenAI、Anthropic、Gemini 网关等）可以按它们实际兼容的协议接入。

## 配置入口

推荐从前端配置：

1. 打开 `/analysis`。
2. 点击左侧边栏底部的`工作区工具`。
3. 打开`模型配置`。
4. 添加服务商，填写 `Base URL`、协议类型、`API Key`。
5. 在服务商卡片里点击`测试`。
6. 点击`获取模型`批量导入模型，或手动添加模型。
7. 在`默认模型`里选择默认 Chat 模型并保存。

后端配置文件适合首次启动前预置模型：

```bash
cd apps/backend
[ -f config.toml ] || cp config.example.toml config.toml
```

用户配置为空时，后端会把 `config.toml` 里的 `llm.providers` 同步到当前用户的全局工作区模型配置。用户已经配置过模型后，后续修改 `config.toml` 不会覆盖已有用户配置。

模型列表支持两种写法：

- 字符串数组：`models = ["step-3.7-flash"]`，capabilities 由后端按接口类型推断。
- 对象数组：每个模型可声明 `name`、`max_context_size`、`capabilities`，用于精确区分纯文本模型和多模态模型。

## 配置存储

用户模型配置保存在用户默认层：

```text
workspaces/{user_id}/global_workspace/.aiasys/llm_config.json
```

实际路径受 `WORKSPACE_DIR` 影响。默认开发环境下，`WORKSPACE_DIR` 来自：

```text
apps/backend/data/workspaces
```

服务商的 API Key 会加密存储，接口返回时只给脱敏值。运行时需要真实请求时，后端从存储里读取并解密。

## 主要 API

LLM 配置路由挂在 `/api/llm` 下。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/llm/providers` | 列出服务商 |
| `POST` | `/api/llm/providers` | 创建服务商 |
| `PATCH` | `/api/llm/providers/{provider_id}` | 更新服务商 |
| `DELETE` | `/api/llm/providers/{provider_id}` | 删除服务商，并删除关联模型 |
| `GET` | `/api/llm/models` | 列出模型 |
| `POST` | `/api/llm/models` | 创建模型 |
| `GET` | `/api/llm/models/by-id?model_id={model_id}` | 获取模型详情 |
| `PATCH` | `/api/llm/models/by-id?model_id={model_id}` | 更新模型 |
| `DELETE` | `/api/llm/models/by-id?model_id={model_id}` | 删除模型 |
| `POST` | `/api/llm/models/by-id/default?model_id={model_id}` | 设为默认模型 |
| `POST` | `/api/llm/providers/{provider_id}/test` | 测试服务商连接 |
| `POST` | `/api/llm/providers/{provider_id}/fetch_models` | 从服务商获取模型列表 |
| `POST` | `/api/llm/defaults` | 设置默认 Chat / Embedding 模型 |

## 环境变量覆盖

服务端支持通过环境变量覆盖敏感配置：

```bash
AIASYS_LLM_PROVIDER_STEPFUN_API_KEY=sk-xxx
AIASYS_LLM_PROVIDER_STEPFUN_BASE_URL=https://api.stepfun.com/v1
AIASYS_EMBEDDING_API_KEY=sk-xxx
AIASYS_AUTH_JWT_SECRET=your-secret
```

其中 `{PROVIDER_ID}` 是 `config.toml` 中 `llm.providers` 的键名（如 `stepfun`）。系统启动时会自动遍历所有已配置的 provider 并检查对应的环境变量。

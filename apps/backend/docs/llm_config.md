# LLM 配置与模型解析

当前默认模型配置以 Kimi 为优先入口。`apps/backend/config.example.json` 默认使用：

```json
{
  "llm": {
    "default_provider": "kimi",
    "default_model": "kimi-for-coding",
    "providers": {
      "kimi": {
        "type": "kimi",
        "base_url": "https://api.kimi.com/coding/v1",
        "api_key": "your-kimi-api-key",
        "models": ["kimi-for-coding"]
      }
    }
  }
}
```

`type: "kimi"` 是历史配置写法。运行时会把它迁移为 `anthropic_messages` 协议处理。通过前端手动添加 Kimi Coding API 时，服务商类型选 `Anthropic Messages`。

其他服务商可以作为补充配置。系统按接口协议识别服务商，当前支持：

| 类型 | 用途 |
|------|------|
| `openai_chat_completions` | OpenAI Chat Completions 兼容接口 |
| `openai_responses` | OpenAI Responses 兼容接口 |
| `anthropic_messages` | Anthropic Messages 兼容接口，Kimi Coding API 走这个协议 |

DashScope、OpenAI、Anthropic、Gemini 网关等服务可以按它们实际兼容的协议接入。文档和示例里的默认模型应优先写 Kimi。

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
[ -f config.json ] || cp config.example.json config.json
```

用户配置为空时，后端会把 `config.json` 里的 `llm.providers` 同步到当前用户的全局工作区模型配置。用户已经配置过模型后，后续修改 `config.json` 不会覆盖已有用户配置。

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
| `POST` | `/api/llm/providers/{provider_id}/test` | 测试服务商连通性 |
| `POST` | `/api/llm/providers/{provider_id}/fetch-models` | 从服务商获取模型列表 |
| `GET` | `/api/llm/models` | 列出模型 |
| `POST` | `/api/llm/models` | 创建模型 |
| `PATCH` | `/api/llm/models/{model_id}` | 更新模型 |
| `DELETE` | `/api/llm/models/{model_id}` | 删除模型 |
| `GET` | `/api/llm/defaults` | 读取默认 Chat / Embedding 模型 |
| `PUT` | `/api/llm/defaults` | 保存默认 Chat / Embedding 模型 |
| `GET` | `/api/llm/templates` | 获取前端参考模板 |
| `POST` | `/api/llm/initialize` | 初始化空配置 |

## 服务商字段

| 字段 | 说明 | Kimi 示例 |
|------|------|------|
| `id` | 本地唯一标识 | `kimi` |
| `name` | 界面显示名 | `Kimi` |
| `type` | 接口协议类型 | `anthropic_messages` |
| `base_url` | API 基础地址 | `https://api.kimi.com/coding/v1` |
| `api_key` | API Key | `sk-...` |
| `custom_headers` | 自定义请求头 | `{}` |
| `env` | 请求环境变量 | `{}` |
| `enabled` | 是否启用 | `true` |
| `is_default` | 是否默认服务商 | `true` |

Kimi Coding API 会自动补 `User-Agent: KimiCLI/1.16.0`。如果手动填写自定义请求头，也可以显式写入。

## 模型字段

| 字段 | 说明 | Kimi 示例 |
|------|------|------|
| `id` | 本地模型配置 ID | `kimi-for-coding` |
| `name` | 界面显示名 | `Kimi Coding` |
| `provider` | 关联服务商 ID | `kimi` |
| `model` | API 请求里的真实模型名 | `kimi-for-coding` |
| `model_type` | `chat` 或 `embedding` | `chat` |
| `max_context_size` | 最大上下文长度 | `200000` |
| `capabilities` | 模型能力 | `["thinking", "image_in"]` |
| `enabled` | 是否启用 | `true` |
| `is_default` | 是否默认模型 | `true` |

`Chat` 模型用于 Agent 对话、自动任务、上下文压缩等执行链路。`Embedding` 模型用于知识库向量化，需要在默认模型区域单独选择。

## 运行时解析顺序

当前执行链路通过 `LLMConfigService.get_full_config(user_id)` 读取用户模型配置。解析结果包含：

- `providers`
- `models`
- `default_model`
- `default_chat_model`
- `default_embedding_model`

默认 Chat 模型优先来自用户默认层的 `default_chat_model` / `default_model`。如果没有显式默认模型，服务会从启用模型里选择可用项。服务商和模型都为空时，Agent 执行会缺少可用模型，前端应提示用户先配置模型。

## 环境变量覆盖

服务端可以用环境变量覆盖 `config.json` 中的敏感字段，避免把真实 Key 写入仓库或镜像。

Kimi 常用项：

```bash
AIASYS_LLM_PROVIDER_KIMI_API_KEY=...
AIASYS_LLM_PROVIDER_KIMI_BASE_URL=https://api.kimi.com/coding/v1
```

其他服务商按 provider ID 生成环境变量后缀。例如 provider ID 为 `dashscope` 时，对应：

```bash
AIASYS_LLM_PROVIDER_DASHSCOPE_API_KEY=...
AIASYS_LLM_PROVIDER_DASHSCOPE_BASE_URL=...
```

这类服务商可以作为补充示例，不应写成当前默认模型。

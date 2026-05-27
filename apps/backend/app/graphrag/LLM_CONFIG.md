# GraphRAG LLM 配置指南

GraphRAG 使用系统现有的 `llm_config.json` 配置，无需额外设置。

## 配置文件位置

```
# 系统默认配置
apps/backend/data/workspaces/local_default/global_workspace/.aiasys/llm_config.json

# 用户特定配置（可选）
apps/backend/data/workspaces/{user_id}/global_workspace/.aiasys/llm_config.json
```

## 快速开始

### 1. 确保系统已配置 LLM

检查 `data/workspaces/local_default/global_workspace/.aiasys/llm_config.json` 是否存在且包含启用的 provider：

```bash
cat apps/backend/data/workspaces/local_default/global_workspace/.aiasys/llm_config.json
```

预期内容：
```json
{
  "providers": [
    {
      "id": "kimi",
      "name": "Kimi Coding",
      "type": "anthropic_messages",
      "base_url": "https://api.kimi.com/coding/v1",
      "api_key_encrypted": "...",
      "enabled": true,
      "is_default": true
    }
  ],
  "models": [
    {
      "id": "kimi-coding-model",
      "name": "Kimi for Coding",
      "provider": "kimi",
      "model": "kimi-for-coding",
      "max_context_size": 128000,
      "enabled": true,
      "is_default": true
    }
  ]
}
```

### 2. 通过系统设置配置（推荐）

1. 进入系统 **设置 > LLM 配置**
2. 点击 **添加 Provider**
3. 填写配置：
   - **类型**: `kimi` (或其他)
   - **名称**: 任意名称
   - **Base URL**: `https://api.kimi.com/coding/v1`
   - **API Key**: 你的 API Key
4. 勾选 **设为默认**
5. 保存

### 3. GraphRAG 自动使用

GraphRAG 会自动：
1. 读取用户默认层 `llm_config.json`
2. 使用默认 provider
3. 自动解密 `api_key_encrypted`
4. 创建 LLM 客户端

## 支持的 Provider 类型

| 类型 | 说明 | 示例 Base URL |
|------|------|---------------|
| `kimi` | Moonshot Kimi | `https://api.kimi.com/coding/v1` |
| `openai_chat_completions` | OpenAI 兼容模式 | `https://api.openai.com/v1` |
| `openai_responses` | OpenAI 新 API | `https://api.openai.com/v1` |
| `anthropic` | Claude | `https://api.anthropic.com` |
| `gemini` | Google Gemini | `https://generativelanguage.googleapis.com/v1beta` |
| `vertexai` | Google Cloud | `https://...googleapis.com` |

## 配置优先级

1. **用户配置**（如果指定了 user_id）
   - `workspaces/{user_id}/global_workspace/.aiasys/llm_config.json`
2. **系统配置**（默认）
   - `data/workspaces/local_default/global_workspace/.aiasys/llm_config.json`

## 验证配置

```bash
# 检查 LLM 状态
curl http://localhost:13001/api/graph/config/llm/status

# 预期响应
{
  "status": "available",
  "initialized": true,
  "extractor_available": true,
  "resolver_available": true,
  "reporter_available": true
}
```

## 测试文档处理

```bash
# 上传测试文档（自动使用配置的 LLM）
curl -X POST http://localhost:13001/api/graph/documents \
  -H "Content-Type: application/json" \
  -d '{
    "content": "人工智能（AI）是计算机科学的一个分支。机器学习是 AI 的子集。",
    "resolve_entities": true
  }'

# 预期响应
{
  "doc_id": "abc123...",
  "entity_count": 3,
  "relation_count": 2,
  "token_count": 1500,
  "merged_entities": 0
}
```

## 故障排查

### 错误: "LLM not configured"

**原因**: `llm_config.json` 中没有启用的 provider

**解决**:
```bash
# 检查配置文件是否存在
cat apps/backend/data/workspaces/local_default/global_workspace/.aiasys/llm_config.json

# 如果没有，通过 API 添加
curl -X POST http://localhost:13001/api/llm/providers \
  -H "Content-Type: application/json" \
  -d '{
    "id": "kimi",
    "name": "Kimi",
    "type": "anthropic_messages",
    "base_url": "https://api.kimi.com/coding/v1",
    "api_key": "sk-your-key",
    "enabled": true,
    "is_default": true
  }'
```

### 错误: "No API key"

**原因**: api_key_encrypted 解密失败或为空

**解决**:
- 重新在系统设置中添加 provider
- 确保 `ENCRYPTION_KEY` 环境变量正确设置

### 错误: "Provider type not supported"

**原因**: `llm_config.json` 中的 type 不在支持列表

**支持类型**: `kimi`, `openai_chat_completions`, `openai_responses`, `anthropic`, `gemini`, `vertexai`

## 手动测试 Provider

```python
import asyncio
from app.graphrag.llm_adapter import create_llm_client_from_config

async def test():
    client = await create_llm_client_from_config()
    if client:
        response = await client.achat("Hello, what is AI?")
        print(response)
    else:
        print("No LLM configured")

asyncio.run(test())
```

## 配置示例

### Kimi (推荐)

```json
{
  "providers": [{
    "id": "kimi",
    "name": "Kimi Coding",
    "type": "anthropic_messages",
    "base_url": "https://api.kimi.com/coding/v1",
    "api_key_encrypted": "gAAAA...",
    "enabled": true,
    "is_default": true
  }],
  "models": [{
    "id": "kimi-model",
    "name": "Kimi for Coding",
    "provider": "kimi",
    "model": "kimi-for-coding",
    "max_context_size": 128000,
    "enabled": true,
    "is_default": true
  }]
}
```

### 阿里云 DashScope

```json
{
  "providers": [{
    "id": "dashscope",
    "name": "DashScope",
    "type": "openai_chat_completions",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key_encrypted": "gAAAA...",
    "enabled": true,
    "is_default": true
  }],
  "models": [{
    "id": "deepseek-v3",
    "name": "DeepSeek V3",
    "provider": "dashscope",
    "model": "deepseek-v3",
    "max_context_size": 64000,
    "enabled": true,
    "is_default": true
  }]
}
```

## 注意事项

1. **API Key 加密**: 配置中的 `api_key_encrypted` 由系统自动加密/解密
2. **默认 Provider**: GraphRAG 使用标记为 `is_default: true` 的 provider
3. **多用户**: 支持为不同用户使用不同的配置
4. **热更新**: 修改配置后无需重启服务，下次请求自动生效

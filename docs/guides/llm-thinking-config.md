# LLM Thinking / Reasoning 配置指南

## 概述

AIASys 支持为支持 reasoning（深度思考）的模型配置思考深度和 reasoning 内容解析方式。当前已验证支持：

- **阶跃星辰（StepFun）**：step-3.5-flash-2603
- **DeepSeek**：deepseek-chat、deepseek-reasoner 等
- **Kimi**：kimi-for-coding、kimi-k2 系列
- **Anthropic**：Claude Opus 4 / Claude Sonnet 4 / Claude Haiku 3.5

## Provider 配置

### 基础连接信息

在"设置 > 模型服务商"中配置服务商时，需要填写：

| 字段 | 说明 | 示例 |
|------|------|------|
| ID | 唯一标识 | `stepfun` |
| 名称 | 显示名称 | `阶跃星辰` |
| 类型 | 接口协议 | `openai_chat_completions` |
| Base URL | API 地址 | `https://api.stepfun.com/v1` |
| API Key | 密钥 | `sk-...` |

### Thinking 相关字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `reasoning_key` | string | API 返回 reasoning 内容时使用的字段名。不填则默认按 `reasoning_content` 解析。阶跃需要填 `reasoning`。 |
| `reasoning_format` | string | 仅阶跃支持。可选 `general`（默认）或 `deepseek-style`。控制返回字段名：`general` 用 `reasoning`，`deepseek-style` 用 `reasoning_content`。 |

## 各厂商配置对照

### 阶跃星辰（StepFun）

```json
{
  "id": "stepfun",
  "name": "阶跃星辰",
  "type": "openai_chat_completions",
  "base_url": "https://api.stepfun.com/v1",
  "reasoning_key": "reasoning",
  "reasoning_format": "general"
}
```

**重要**：阶跃默认返回的 reasoning 字段名是 `reasoning`，不是 `reasoning_content`。如果不配置 `reasoning_key: "reasoning"`，系统将解析不到 reasoning 内容。

支持的模型和 thinking 参数：

| 模型 | reasoning_effort | 说明 |
|------|-----------------|------|
| step-3.5-flash-2603 | `low` / `high` | 支持 thinking，可配置 effort |
| step-3.5-flash | 不支持 | 普通对话模型 |
| step-3.7-flash | 待验证 | 内测阶段，仅标准 API |

### DeepSeek

```json
{
  "id": "deepseek",
  "name": "DeepSeek",
  "type": "openai_chat_completions",
  "base_url": "https://api.deepseek.com/v1",
  "reasoning_key": "reasoning_content"
}
```

DeepSeek 默认返回 `reasoning_content` 字段，与系统默认值一致，可不配置 `reasoning_key`。

### Kimi（Moonshot）

```json
{
  "id": "kimi",
  "name": "Kimi",
  "type": "openai_chat_completions",
  "base_url": "https://api.moonshot.cn/v1"
}
```

Kimi 的 thinking 参数通过 `extra_body.thinking.type` 控制，系统已内置适配，无需额外配置 `reasoning_key`。

### Anthropic（Claude）

```json
{
  "id": "anthropic",
  "name": "Anthropic",
  "type": "anthropic_messages",
  "base_url": "https://api.anthropic.com/v1"
}
```

Anthropic 使用独立的 Messages API 协议，thinking 配置通过 `thinking.type` 和 `output_config.effort` 控制，系统已完整适配 adaptive / legacy 两种模式。

## 模型配置

在"设置 > 模型配置"中为模型启用 thinking 能力：

```json
{
  "id": "stepfun-step-3.5-flash-2603",
  "name": "step-3.5-flash-2603",
  "provider": "stepfun",
  "model": "step-3.5-flash-2603",
  "capabilities": ["thinking", "image_in"],
  "thinking_effort": "high"
}
```

| 字段 | 说明 |
|------|------|
| `capabilities` | 包含 `"thinking"` 表示该模型支持 thinking 开关；包含 `"always_thinking"` 表示该模型固定开启 thinking |
| `thinking_effort` | 思考深度：`low` / `medium` / `high`。不同模型支持的级别不同 |

## 前端使用

配置完成后，在对话输入区：

1. **模型选择器**：选择支持 thinking 的模型
2. **思考模式**：在模型选择器下拉面板中开启/关闭 thinking，选择 effort 级别
3. **思考内容展示**：模型回复时会显示"思考过程"折叠面板，可展开查看 reasoning 内容

## 故障排查

### 开了 thinking 但看不到 reasoning 内容

1. 检查 provider 是否配置了正确的 `reasoning_key`
2. 检查模型 capabilities 是否包含 `"thinking"`
3. 检查模型是否配置了 `thinking_effort`

### API 返回 400 关于 reasoning

1. 确认模型是否支持 thinking（不是所有模型都支持）
2. 确认 `reasoning_effort` 值是否在模型支持范围内（阶跃仅支持 `low` / `high`）

---
name: aiasys-llm-config
description: |
  AIASys LLM 模型配置管理。说明 LLM 配置的两层存储机制、key 位置、
  同步流程、故障排查和验证方法。适用于新环境部署或 LLM 配置变更时。
---

# AIASys LLM 模型配置

## 背景

AIASys 的 LLM 配置采用两层存储：源配置文件 + 运行时加密存储。部署新环境时，如果只同步了代码而遗漏了配置，会导致 Agent 执行时无法调用模型。

## 配置架构

```
config.toml                          llm_config.json (运行时)
┌─────────────────────┐              ┌──────────────────────────────┐
│ llm:                │              │ providers: [                 │
│   default_provider  │  同步后      │   { id, name, type,          │
│   default_model     │ ──────────►  │     base_url, api_key(加密), │
│   temperature       │              │     ... } ]                  │
│   providers:        │  启动时自动   │ models: [                    │
│     stepfun:        │              │   { id, name, provider,      │
│       base_url      │              │     model, max_context,      │
│       api_key       │              │     capabilities } ]         │
│       models: [...] │              │ ]                            │
│     kimi:           │              └──────────────────────────────┘
│       ...           │                     ↑
└─────────────────────┘              实际被系统读取
```

| 层级 | 文件 | 作用 |
|------|------|------|
| 源配置 | `apps/backend/config.toml` | 开发者维护，不进入 git（含真实 key） |
| 运行时存储 | `data/workspaces/{user_id}/global_workspace/.aiasys/llm_config.json` | 系统读写，key 加密存储 |

## 关键规则

1. **`config.toml` 不在 rsync 同步范围** — 如果通过 rsync 同步代码，需要单独传输 `config.json`
2. **启动时自动同步** — 后端启动时调用 `sync_config_json_to_user()`，仅在运行时存储为空时才同步，不会覆盖已有配置
3. **同步后必须重启后端** — 修改 `config.toml` 后需要重启 uvicorn 才能生效
4. **key 加密存储** — `llm_config.json` 中的 `api_key` 经过 Fernet 对称加密，不是明文

## 新环境部署时的 LLM 配置检查清单

部署到新机器（Mac / 新 WSL / CI）时，按以下步骤检查：

### 1. 确认 config.toml 存在

```bash
# 在目标机器上
ls apps/backend/config.toml
```

如果不存在，从源机器复制（**不要提交到 git**）：

```bash
scp apps/backend/config.toml <用户>@<目标IP>:~/projects/AIASys/apps/backend/config.json
```

### 2. 确认 key 未过期

```bash
# 读取 key 前缀（不暴露完整 key）
grep api_key apps/backend/config.toml
```

拿到 key 后，用 Python 脚本验证连通性：

```python
import urllib.request, json

config = tomllib.loads(Path("apps/backend/config.toml").read_text(encoding="utf-8"))
provider = config["llm"]["providers"]["<provider_id>"]
key = provider["api_key"]

data = json.dumps({
    "model": provider["models"][0],
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 10
}).encode()

req = urllib.request.Request(
    f"{provider['base_url']}/chat/completions",
    data=data,
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}"
    },
    method="POST"
)

resp = urllib.request.urlopen(req, timeout=15)
print(resp.status, resp.read().decode()[:200])
```

期望 HTTP 200。如果返回 401/403，说明 key 过期或被撤销，需要更新。

### 3. 安装后端依赖并启动

```bash
cd apps/backend
uv venv .venv --python 3.12
uv pip install -r pyproject.toml --python .venv/bin/python3
mkdir -p data workspaces logs
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 13001
```

### 4. 验证 LLM 配置已加载

```bash
# 检查启动日志
grep "config.toml 同步完成" logs/  # 或看 uvicorn 输出
# 期望看到: config.toml 同步完成: N providers, M models

# 通过 API 验证
curl -s http://localhost:13001/api/workspaces | python3 -c "import sys,json; print('OK')"
```

### 5. 如果提示 "LLM 动态配置为空"

这是最常见的部署错误。表现：

```
app.services.agent.mixins.session - ERROR - LLM 动态配置为空，请检查 config.toml 和启动日志
```

原因和解决：

| 原因 | 解决 |
|------|------|
| `config.toml` 不存在 / `配置文件不存在` | 从源机器复制 |
| `config.toml` 中 `llm.providers` 为空或格式错误 | 检查 TOML 格式 |
| 后端启动时 `sync_config_json_to_user` 抛出异常 | 查看启动日志中的 warning |
| `llm_config.json` 已存在但内容损坏 | 删除 `global_workspace/.aiasys/llm_config.json` 后重启 |

手动触发同步：

```bash
cd apps/backend
.venv/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from app.services.llm.llm_config_service import get_llm_config_service
get_llm_config_service().sync_config_json_to_user('local_default')
"
```

验证同步结果：

```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from app.services.llm.llm_config_service import get_llm_config_service
config = get_llm_config_service().get_full_config('local_default')
print('Providers:', list(config.get('providers', {}).keys()))
print('Models:', list(config.get('models', {}).keys()))
"
```

## 配置文件结构说明

`config.toml` 中 `llm` 字段的完整结构：

```json
{
  "llm": {
    "default_provider": "stepfun",
    "default_model": "step-3.7-flash",
    "temperature": 0.6,
    "providers": {
      "<provider_id>": {
        "type": "openai_chat_completions",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-xxxx",
        "models": ["model-name-1", "model-name-2"]
      }
    }
  }
}
```

| 字段 | 说明 |
|------|------|
| `default_provider` | 默认服务商 ID，对应 `providers` 中的 key |
| `default_model` | 默认模型名，对应 `providers.*.models` 中的值 |
| `type` | 服务商类型，通常用 `openai_chat_completions`（兼容 OpenAI 接口的服务商通用此类型） |
| `base_url` | API 端点地址 |
| `api_key` | 服务商 API 密钥 |
| `models` | 该服务商支持的模型名列表 |

## 常见模型配置参考

| 服务商 | provider_id | base_url | 模型名 |
|--------|-------------|----------|--------|
| 阶跃星辰 | `stepfun` | `https://api.stepfun.com/v1` | `step-3.7-flash` |
| Kimi | `kimi` | `https://api.kimi.com/coding/v1` | `kimi-for-coding` |
| SiliconFlow (Embedding) | `siliconflow` | `https://api.siliconflow.cn/v1` | `BAAI/bge-m3` |

> 以上为项目当前使用的配置，实际以 `config.toml` 为准。

## 故障排查速查

| 症状 | 检查点 |
|------|--------|
| 后端启动正常但 Agent 调用返回 400 | 检查 `config.toml` 的 `api_key` 是否有效 |
| 后端启动报 "LLM 动态配置为空" | 按第 5 节排查 |
| API 返回 401 "Incorrect API key" | key 过期或被撤销，需要更新 |
| API 返回 400 "input_invalid" | 请求体格式问题，检查模型名是否正确 |
| Mac 上 curl 能通但 Python urllib 报 Connection refused | 检查后端是否在监听 `0.0.0.0:13001` |
| 同步后仍为空 | 删除 `llm_config.json` 后重启后端 |

## 相关文件

| 文件 | 说明 |
|------|------|
| `apps/backend/config.toml` | LLM 源配置（**不提交 git**） |
| `apps/backend/app/storage/llm_provider_storage.py` | 配置存储层，处理加密/解密 |
| `apps/backend/app/services/llm/llm_config_service.py` | 配置服务层，含同步逻辑 |
| `apps/backend/app/services/agent/mixins/session.py` | Agent 运行时加载 LLM 配置 |

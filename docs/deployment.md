# AIASys 部署说明

本文档描述当前仓库的真实启动方式，适用于单机本地部署或开发联调环境。

这是 `docs/` 目录下唯一当前维护的部署入口。旧的重复部署稿和 Docker 启动说明已经归档到
`design-draft/archive/06-docs-and-references/`，不再作为主入口继续维护。

如果你需要先看产品怎么用，再回来部署，请先看 [基础使用教程](getting-started.md)。

## 1. 已验证版本

当前这份文档按本机已验证环境整理，建议优先贴近以下版本：

- 后端 Python：`3.12.12`
- 前端 Node.js：22+
- 前端 npm：`10.9.7`

补充说明：

- 后端部署基线按 `apps/backend/.venv/bin/python`，暂不按根目录 `.python-version`
- 前端当前按 `npm` 路径验证，不按 `pnpm` 作为主部署口径

## 2. 运行前提

- 前端端口默认使用 `13000`
- 后端端口默认使用 `13001`
- 后端配置文件位于 `apps/backend/config.json`
- 建议显式设置 `ENCRYPTION_KEY`，否则后端会使用临时密钥并在启动时发出警告

## 3. 依赖准备

### 3.1 前端依赖

前端有 `package-lock.json`，推荐直接使用：

```bash
cd apps/web
npm ci
```

### 3.2 后端依赖

后端依赖事实源是：

- `apps/backend/pyproject.toml`
- `apps/backend/uv.lock`

推荐优先使用 `uv` 准备环境：

```bash
cd apps/backend
uv sync
```

如果部署环境需要严格复用锁文件，可以使用：

```bash
cd apps/backend
uv sync --frozen
```

如果你只是沿用当前仓库这份已经可运行的 `.venv`，则不需要再额外安装后端依赖。

需要注意：

- 如果不设置 `ENCRYPTION_KEY`，当前进程仍可启动
- 只是重启后无法稳定复用之前的加密状态
- 所以无论是本地长期使用还是远程示例环境，都建议显式设置

## 4. 后端启动

首次部署时，先准备配置文件：

```bash
cd apps/backend
[ -f config.json ] || cp config.example.json config.json
```

然后按实际情况填写 `config.json` 里的关键配置：

- `llm.providers.*.api_key`
- `embedding.api_key`
- `auth.mode`
- 其他与你环境相关的地址和密钥

启动后端：

```bash
cd apps/backend
export ENCRYPTION_KEY="replace-with-your-own-secret"
uv run uvicorn app.main:app --host 0.0.0.0 --port 13001
```

健康检查：

```bash
curl http://127.0.0.1:13001/health
```

## 5. 前端启动

安装依赖并启动前端：

```bash
cd apps/web
npm ci
npm run dev -- --host 0.0.0.0 --port 13000
```

默认前端会把以下路径代理到后端：

- `/api`
- `/health`

默认联调目标是 `http://localhost:13001`。如需覆盖，可设置：

```bash
VITE_API_TARGET=http://localhost:13001
VITE_AUTH_MODE=local
```

## 6. 访问地址

- 前端首页：`http://localhost:13000`
- 分析页：`http://localhost:13000/analysis`
- 后端健康检查：`http://localhost:13001/health`

## 7. 构建前端

如果只需要验证前端打包：

```bash
cd apps/web
npm run build
```

## 8. 当前部署说明边界

- 当前仓库有统一开发启动脚本 `./dev.sh`
- 本文档以手动进程部署为准，方便排查配置和依赖问题
- 当前文档以单机本地部署为准
- 当前主线默认使用本地执行链路
- 生产化部署如需反向代理、进程守护、HTTPS 或更严格的用户数据隔离，应在此基础上另行补充

如果你要看远端服务器发布脚本、PM2 / Nginx / PostgreSQL 的实际发布流程，请直接看
[infra/deploy/README.md](../infra/deploy/README.md)。

## 9. 远程示例版如何不暴露真实 Key

可以。推荐做法是：

1. 远程机器上的 `apps/backend/config.json` 只保留占位值或示例值，不写真实 key
2. 把真实 key 只放在服务器环境变量里
3. 前端始终只调用你的后端接口，不直接接触第三方模型 key
4. 对外演示时单独使用一套额度受控的演示 key，不要复用个人主 key

当前后端支持很多环境变量覆盖，但远程示例版通常只需要最小的一组。

推荐优先配置：

```bash
AIASYS_LLM_PROVIDER_KIMI_API_KEY=...
AIASYS_EMBEDDING_API_KEY=...
AIASYS_AUTH_JWT_SECRET=...
```

可选高级项：

```bash
AIASYS_LLM_PROVIDER_DASHSCOPE_API_KEY=...
AIASYS_LLM_PROVIDER_KIMI_BASE_URL=...
AIASYS_DOCUMENT_EXTRACTION_PDF_PASSWORD=...
```

LLM provider 的环境变量命名遵循动态规则 `AIASYS_LLM_PROVIDER_{PROVIDER_ID}_API_KEY` 和 `AIASYS_LLM_PROVIDER_{PROVIDER_ID}_BASE_URL`，其中 `{PROVIDER_ID}` 是 `config.json` 中 `llm.providers` 的键名（如 `kimi`、`dashscope`）。系统启动时会自动遍历所有已配置的 provider 并检查对应的环境变量。若需覆盖服务商 endpoint（如接入 Ollama、vLLM 等本地模型服务），可同时设置 `AIASYS_LLM_PROVIDER_{PROVIDER_ID}_BASE_URL`。

建议：

- LLM 与 embedding 使用两套独立配置，不要共用同一组服务口径
- 至少分开 `AIASYS_LLM_PROVIDER_*_API_KEY` 与 `AIASYS_EMBEDDING_API_KEY`
- 演示站优先使用单独额度、单独权限的 key

示例：

```bash
cd apps/backend

export AIASYS_LLM_PROVIDER_KIMI_API_KEY="你的远程演示 key"
export AIASYS_EMBEDDING_API_KEY="你的 embedding key"
export AIASYS_AUTH_JWT_SECRET="一个新的远程密钥"

uv run uvicorn app.main:app --host 0.0.0.0 --port 13001
```

这样做的结果是：

- Git 仓库里不需要保存真实 key
- 浏览器里也不会直接看到第三方模型 key
- 你可以在远程起一个可用的 example/demo 版本
- `LocalIPythonBox` 默认不会继承这些敏感环境变量到执行内核

需要注意：

- 如果示例站对公网开放，即使 key 没暴露，别人仍然可能通过你的后端消耗额度
- 所以建议给示例站单独准备低额度 key、登录门槛、限流或白名单
露，别人仍然可能通过你的后端消耗额度
- 所以建议给示例站单独准备低额度 key、登录门槛、限流或白名单
��备低额度 key、登录门槛、限流或白名单

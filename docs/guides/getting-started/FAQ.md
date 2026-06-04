# AIASys 常见问题

## 启动与运行

### Q: `./dev.sh` 启动后页面打不开？

先用 `./dev.sh status` 确认前后端端口状态：

```bash
./dev.sh status
```

输出会显示 `frontend http://127.0.0.1:13000: up/down` 和 `backend http://127.0.0.1:13001: up/down`。

如果显示 `down`，检查：
- 端口是否被占用：`ss -tlnp | grep -E ':(13000|13001)'`
- 后端是否缺少依赖：进 `apps/backend` 执行 `uv sync`
- 前端是否缺少依赖：进 `apps/web` 执行 `npm ci`

### Q: 后端启动报 `ModuleNotFoundError`？

依赖未安装完整。重新同步：

```bash
cd apps/backend
uv sync
```

### Q: 前端启动报 `npm` 找不到模块？

```bash
cd apps/web
rm -rf node_modules
npm ci
```

### Q: 端口被占用怎么办？

覆盖默认端口：

```bash
# 前端
cd apps/web
npm run dev -- --port 13002

# 后端
cd apps/backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 13002

# 或通过 dev.sh 覆盖
AIASYS_FRONTEND_PORT=13002 AIASYS_BACKEND_PORT=13003 ./dev.sh
```

### Q: Docker 未安装会影响使用吗？

不会。AIASys 默认使用本地 UV 运行环境执行代码，不强制依赖 Docker。Docker 只在需要 Docker 沙盒执行环境时才需要。详见 [../../deployment.md](../../deployment.md)。

### Q: Redis 未安装会影响使用吗？

不会。Redis 是可选的，未安装时系统自动回退到内存模式。

---

## 模型配置

### Q: 在界面上配置了模型，为什么对话还是发不出去？

检查三件事：

1. 模型类型是否选了 `Chat`（不是 `Embedding`）
2. 模型是否已启用（模型列表中开关是开的）
3. 默认模型是否已设置（在"默认模型"下拉里选中了一个 Chat 模型）

### Q: 修改了 `config.json` 但界面上没变化？

`config.json` 只在用户配置为空时作为初始值同步一次。如果已经在界面里配置过模型，`config.json` 的修改不会覆盖现有用户配置。需要调整时在界面的"模型配置"里改。

如果需要强制从 `config.json` 重新同步，需要先清空用户的全局工作区 LLM 配置文件（`workspaces/{user_id}/global_workspace/.aiasys/llm_config.json`），然后重启后端。LLM 配置在启动时加载，没有热更新接口。

### Q: 模型测试连接失败？

逐项排查：
1. Base URL 是否以 `/v1` 结尾（大多数 OpenAI 兼容 API 需要）
2. API Key 是否有效
3. 网络是否能访问目标地址（公司内网 / 代理问题）
4. 类型字段是否和服务商协议匹配（`OpenAI Chat Completions` vs `Anthropic Messages`）

### Q: 怎么查看后端日志排查模型调用问题？

后端启动终端会输出日志。如果通过 `./dev.sh` 启动，日志在启动的终端里。也可以手动启动后端来观察：

```bash
cd apps/backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 13001
```

---

## 认证与安全

### Q: ENCRYPTION_KEY 丢了怎么办？

开发模式下（`auth.mode=local`），不设置 `ENCRYPTION_KEY` 也能启动，系统会自动使用基于用户主目录的确定性派生密钥。生产模式下未设置 `ENCRYPTION_KEY` 会直接拒绝启动。

如果之前用某个 key 加密了敏感数据（如数据库连接密码、API Key），换 key 后这些数据无法解密，需要重新配置。如果只是本地开发且没有持久化的加密数据，可以换一个新 key：

```bash
export ENCRYPTION_KEY="new-random-secret"
```

也可以使用 `AIASYS_DEV_ENCRYPTION_KEY` 作为中间选项，显式指定一个固定的开发密钥，避免依赖自动派生。建议把 key 写入 shell 配置文件（`~/.bashrc` 或 `~/.zshrc`），避免每次手动设置。

### Q: 怎么重置用户数据？

删除 `apps/backend/data/` 目录：

```bash
rm -rf apps/backend/data/
```

注意：这会清除所有工作区、会话历史、LLM 配置、知识库等数据。如果 `DATA_DIR` 被环境变量 `AIASYS_RUNTIME_DATA_DIR` 或 `runtime-storage.json` 覆盖过，需要确认实际路径后再操作。日志文件在 `apps/backend/logs/`，不在 `data/` 下，如需彻底清空也要单独处理。

---

## 工作区与会话

### Q: 全局工作区和普通工作区有什么区别？

全局工作区（左侧 Activity Bar 第二个图标）存放跨工作区共享的资源，所有工作区都能访问。普通工作区是独立的任务空间。详见 [SYSTEM_USAGE.md](SYSTEM_USAGE.md)。

### Q: 会话和工作区是什么关系？

工作区是任务的容器，会话是工作区内的一条任务推进线。一个工作区可以有多个会话，会话之间上下文隔离。

### Q: Agent 执行到一半卡住了？

点击输入区旁边的停止按钮，或调用 API：

```bash
curl -X POST http://localhost:13001/api/agent/stop \
  -H "Content-Type: application/json" \
  -d '{"session_id": "session-id"}'
```

---

## 前端构建

### Q: `npm run build` 报错？

常见原因：
1. `node_modules` 损坏：删掉重装 `rm -rf node_modules && npm ci`
2. Node.js 版本太低：需要 22+
3. TypeScript 类型错误：看具体报错信息

### Q: Vite 代理配错导致 API 请求失败？

前端 dev server 默认代理 `/api` 和 `/health` 到 `http://localhost:13001`。如果后端不在默认端口，设置：

```bash
VITE_API_TARGET=http://localhost:13002 npm run dev
```

### Q: 构建产物放哪里？

`apps/web/dist/`。生产环境用 `infra/deploy/static_web_server.py` 托管。

---

## 数据库

### Q: 系统依赖 PostgreSQL 吗？

不依赖。AIASys 内置 SQLite 和 DuckDB，开箱即用。`infra/docker/postgres/` 下的 PostgreSQL 容器仅用于测试系统接入外部数据库的能力，不是系统运行的必要条件。

### Q: 如何备份数据？

默认情况下工作区数据在 `apps/backend/data/` 下，直接备份该目录：

```bash
tar -czf backup.tar.gz apps/backend/data/
```

如果 `DATA_DIR` 被环境变量 `AIASYS_RUNTIME_DATA_DIR` 或 `runtime-storage.json` 覆盖过，先确认实际路径：

```bash
# 查看当前配置中的数据目录
grep -r "data" apps/backend/config.json
```

### Q: Docker 沙盒里的数据库怎么访问？

Docker 运行时通过 broker 访问数据库，容器内不直接持有数据库凭据。如果报"数据库 broker 未配置"，看 [../operations/docker-network-configuration.md](../operations/docker-network-configuration.md)。
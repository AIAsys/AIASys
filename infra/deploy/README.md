# AIASys 部署脚本

本目录包含 AIASys 项目的部署脚本。

## 部署方式

当前使用 **源码部署**（PM2 进程管理 + Docker PostgreSQL）：
- 前端：PM2 管理静态站点进程
- 后端：PM2 管理 Python 进程
- 入口：Nginx 统一监听 `80`
- 数据库：Docker 运行 PostgreSQL

## 脚本说明

| 脚本 | 用途 | 使用场景 |
|------|------|----------|
| `deploy_init.sh` | 服务器初始化部署 | **首次部署**到新服务器，自动安装 Python 3.12、Node.js 22、PM2、Nginx |
| `deploy_update.sh` | 代码更新部署 | **后续更新**，只上传代码并重启服务（依赖已存在） |
| `check_server.sh` | 服务器状态检查 | 查看服务器资源使用情况 |
| `remote_pm2.sh` | 远端 PM2 运维 | 查看状态、日志、重启服务 |
| `remote_postgres.sh` | 远端 PostgreSQL 运维 | 管理主库与 sandbox PostgreSQL |
| `remote_shell.sh` | 远端交互式 Shell | 直接登录到远端项目目录 |

## 快速开始

> 以下命令统一假定在**仓库根目录**执行，避免 `infra/deploy/README.md` 与实际执行目录假设不一致。

### 1. 配置部署参数

```bash
cp infra/deploy/.env.example infra/deploy/.env
# 编辑 .env 填入测试 / 发布服务器信息
```

说明：

- 部署脚本不再硬编码服务器地址、密码和端口
- 模板文件只保留 `infra/deploy/.env.example`
- 实际使用文件只保留本地 `infra/deploy/.env`（gitignored）
- `.env` 内同时维护测试 / 发布两套配置，通过 `DEPLOY_TARGET=test|prod` 选择
- 云端部署默认强制 `sandbox.mode=docker` 且 `sandbox.allow_local=false`
- 前端会通过 `/api/system/capabilities` 自动隐藏本地沙盒选项
- 默认目标建议设为 `DEPLOY_TARGET=test`，发布时显式使用 `DEPLOY_TARGET=prod`
- 远端后端配置统一由本地 `apps/backend/config.json` 渲染生成，再按部署环境覆盖端口/主机
- 系统级 LLM 动态配置 `apps/backend/data/llm_config.json` 会随部署同步到远端，确保默认 Provider / Model 与本地一致
- 如使用 SSH 密钥认证，推荐配置 `SSH_KEY_PATH` 并留空 `SERVER_PASS`
- 默认会在本地先构建前端 `dist`，并随发布包上传；远端直接用 `infra/deploy/static_web_server.py` 托管静态产物，避免低配服务器在 `vite build` 或 `npm ci` 阶段 OOM
- 如目标机已内置可用的 Python 3.12（例如 Miniconda `py312` 环境），部署会优先复用该解释器，避免 `uv python install 3.12` 卡住
- 如宿主机 `nginx` 不可用但 Docker 可用，部署会自动退化为 Docker 版 `nginx` 入口容器

### 2. 首次部署（新服务器）

```bash
./infra/deploy/deploy_init.sh
```

发布环境：

```bash
DEPLOY_TARGET=prod ./infra/deploy/deploy_init.sh
```

此脚本会：
- 上传源码到服务器
- 安装基础依赖、`uv`、Node.js 22、PM2、Nginx
- 使用渲染后的 `config.json` 启动 PostgreSQL 与服务
- 执行 `uv sync --frozen --no-dev`、`npm ci`、`npm run build`
- 如发布包已包含本地预构建的前端 `dist`，远端会自动跳过前端 `npm` 安装与 `npm run build`
- `deploy_update.sh` 会校验 `package-lock.json` 哈希；依赖未变化时自动跳过远端 `npm ci`
- 渲染并覆盖 `Nginx` 站点配置，将 `80` 端口统一反代到前后端
- 先清理同名 PM2 旧进程，再使用 `pm2 start ecosystem.config.cjs --update-env`（需自行准备 PM2 配置文件） 启动前后端服务
- 自动执行本机烟测：`/health`、`/api/graph/health`、`/`

### 3. 后续更新

```bash
./infra/deploy/deploy_update.sh
```

发布环境：

```bash
DEPLOY_TARGET=prod ./infra/deploy/deploy_update.sh
```

此脚本会：
- 打包并上传最新代码
- 使用渲染后的最新配置覆盖远端文件
- 执行 `uv sync --frozen --no-dev`、`npm ci`、`npm run build`
- 如发布包已包含本地预构建的前端 `dist`，远端会自动跳过前端 `npm` 安装与 `npm run build`
- 若前端依赖哈希未变化且远端已有 `node_modules`，会直接跳过 `npm ci`
- 同步并重载 `Nginx` 反向代理配置
- 先清理同名 PM2 旧进程，再用 `pm2 start ecosystem.config.cjs --update-env`（需自行准备 PM2 配置文件） 以最新路径与环境重建服务
- 自动执行本机烟测：`/health`、`/api/graph/health`、`/`

### 4. 检查服务器状态

```bash
./infra/deploy/check_server.sh
```

### 5. 远端服务运维

```bash
# PM2 状态 / 日志 / 重启
./infra/deploy/remote_pm2.sh status
./infra/deploy/remote_pm2.sh logs --service aiasys-backend --lines 200
./infra/deploy/remote_pm2.sh restart --service all

# PostgreSQL（主库 / sandbox）
./infra/deploy/remote_postgres.sh status --target all
./infra/deploy/remote_postgres.sh restart --target app
./infra/deploy/remote_postgres.sh logs --target sandbox

# 打开远端项目目录 shell
./infra/deploy/remote_shell.sh
```

## 环境变量配置

复制 `.env.example` 为 `.env` 并填写：

```bash
DEPLOY_TARGET=test              # 默认部署目标，推荐先指向测试环境
REMOTE_DIR=/opt/aiasys          # 共享默认远端目录
REMOTE_FRONTEND_PORT=13000
REMOTE_BACKEND_PORT=13001
DEPLOY_BUILD_FRONTEND_LOCALLY=1
DEPLOY_AUTH_MODE=local
DEPLOY_SANDBOX_MODE=docker
DEPLOY_SANDBOX_ALLOW_LOCAL=false

# 测试环境
TEST_SERVER_IP=your_test_server_ip
TEST_SERVER_PORT=22
TEST_SERVER_USER=root
TEST_SERVER_PASS=your_test_password

# 发布环境
PROD_SERVER_IP=your_prod_server_ip
PROD_SERVER_PORT=22
PROD_SERVER_USER=root
PROD_SERVER_PASS=your_prod_password
```

变量解析规则：

1. 先加载 `infra/deploy/.env`
2. 如果 `DEPLOY_TARGET=test`，则优先取 `TEST_*`
3. 如果 `DEPLOY_TARGET=prod`，则优先取 `PROD_*`
4. 若目标变量缺失，则回退到通用 `SERVER_*` / `REMOTE_*`

安全约束：

- `infra/deploy/.env` 只用于本地，不得提交
- 发布包会主动排除 `.env`，不会上传到远端服务器
- 云端环境默认按演示环境处理，不开放本地沙盒入口

## 服务器上手动操作

```bash
# SSH 到服务器
ssh root@your_server_ip

cd /opt/aiasys

# 查看服务状态
pm2 status

# 查看日志
pm2 logs

# 重启服务
pm2 restart all

# 停止服务
pm2 stop all
```

说明：

- PostgreSQL 容器通过 `docker compose` 管理，详见 `infra/docker/postgres/README.md`。

## 目录结构

```
infra/deploy/
├── common.sh            # 公共部署函数
├── deploy_init.sh      # 首次部署（含环境安装）
├── deploy_update.sh    # 代码更新
├── check_server.sh     # 服务器状态检查
├── remote_pm2.sh       # 远端 PM2 运维
├── remote_postgres.sh  # 远端 PostgreSQL 运维
├── remote_shell.sh     # 远端项目 Shell
├── .env                # 部署配置（gitignored）
├── .env.example        # 唯一模板文件
└── README.md           # 本文档
```

## 注意事项

1. **首次部署**必须使用 `deploy_init.sh`
2. **后续更新**使用 `deploy_update.sh`
3. 部署前确保 `infra/deploy/.env` 与 `apps/backend/config.json` 配置正确
4. 建议使用 SSH 密钥认证，并尽快轮换旧密码
5. 服务器需要能访问外网以安装 `uv`、Node.js 和依赖
6. `docling` 不是默认部署依赖；如需高成本文档解析，可在远端后端目录手动执行 `uv sync --extra docling`

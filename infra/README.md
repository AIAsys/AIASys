# Infra

部署与容器化基础设施。

## 目录结构

```
infra/
├── deploy/          # 生产部署脚本（PM2 + Nginx + Docker PostgreSQL）
└── docker/          # Docker 配置（本地开发用 PostgreSQL 容器）
```

## deploy/

生产环境部署脚本。详见 [deploy/README.md](deploy/README.md)。

核心脚本：

| 脚本 | 用途 |
|------|------|
| `deploy_init.sh` | 首次部署，安装 Python/Node/PM2/Nginx 全套环境 |
| `deploy_update.sh` | 后续更新，只上传代码并重启服务 |
| `check_server.sh` | 服务器资源与进程状态检查 |
| `remote_pm2.sh` | 远端 PM2 运维（状态、日志、重启） |
| `remote_postgres.sh` | 远端 PostgreSQL 运维（主库 + sandbox） |
| `remote_shell.sh` | 打开远端服务器项目目录 shell |
| `static_web_server.py` | 轻量 SPA 静态站点服务器（PM2 管理的生产前端进程） |

部署方式：源码部署，前端静态产物 + 后端 Python 进程由 PM2 管理，Nginx 统一监听 80 端口，数据库用 Docker 运行 PostgreSQL。

## docker/

本地开发用 PostgreSQL 容器，通过 `docker compose` 管理。

**AIASys 系统不依赖 PostgreSQL。** 系统内置 SQLite 和 DuckDB，开箱即用。这个 PostgreSQL 容器仅用于验证系统接入外部数据库的能力（数据库连接器功能测试），不是系统运行的必要组件。

初始化脚本（按序执行）：

| 文件 | 用途 |
|------|------|
| `01_init_users_and_databases.sql` | 创建 smoke / demo 数据库及用户 |
| `02_init_tables.sql` | 初始化 orders 表结构并插入测试数据 |

测试数据库和用户：

| 数据库 | 用户 | 密码 | 用途 |
|--------|------|------|------|
| smoke_db | smoke | smoke | 冒烟测试 |
| demo | demo | demo | 演示数据库 |
| demo | readonly | readonly | 只读权限验证 |
| demo | writer | writer | 读写权限验证 |

连接信息：Host `127.0.0.1`，Port `5433`，默认数据库 `demo`。
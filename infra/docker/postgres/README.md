# PostgreSQL 测试容器

本目录提供用于本地开发和测试的 PostgreSQL Docker 容器。

**注意：AIASys 系统不依赖 PostgreSQL。** 系统内置 SQLite 和 DuckDB，开箱即用。这个 PostgreSQL 容器仅用于验证系统接入外部数据库的能力（数据库连接器功能测试），不是系统运行的必要组件。

## 启动

```bash
cd infra/docker/postgres
./manage.sh start
```

## 管理

```bash
./manage.sh status   # 查看状态
./manage.sh stop     # 停止
```

## 初始化内容

容器启动时自动执行 `init/` 下的 SQL 脚本（按文件名排序）：

### `01_init_users_and_databases.sql`

创建测试用数据库和用户：

| 数据库 | 用户 | 密码 | 用途 |
|--------|------|------|------|
| `smoke_db` | `smoke` | `smoke` | 冒烟测试 |
| `demo` | `demo` | `demo` | 演示数据库 |
| `demo` | `readonly` | `readonly` | 只读权限验证 |
| `demo` | `writer` | `writer` | 读写权限验证 |

### `02_init_tables.sql`

在 `smoke_db` 和 `demo` 中分别创建 `orders` 表并插入示例数据，同时配置权限：

- `smoke` 用户拥有 `smoke_db` 全部权限
- `demo` 用户拥有 `demo` 全部权限
- `readonly` 用户只能 SELECT
- `writer` 用户有 SELECT/INSERT/UPDATE/DELETE 权限

## 连接信息

| 参数 | 值 |
|------|-----|
| Host | `127.0.0.1` |
| Port | `5433` |
| 默认数据库 | `demo` |

连接示例：

```bash
psql -h 127.0.0.1 -p 5433 -U demo -d demo
# 密码: demo
```

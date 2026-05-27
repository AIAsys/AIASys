# Docker 运行时数据库 Broker 网络配置指南

> 更新日期：2026-03-22
> 适用范围：AIASys Docker 运行时、数据库 helper、session-database broker
> 结论先行：当前 Docker 运行时访问数据库的主路径已经改为“容器内 `db helper` 访问 backend broker，再由 broker 访问 built-in database 或 external connectors”。`172.17.0.1` 仍然重要，但现在主要用于 Docker 容器访问宿主机上的 backend broker。

---

## 1. 当前主链

### 1.1 运行时访问数据库的真实路径

当前 Docker 运行时代码访问数据库的主路径是：

1. 容器内代码调用 `db.list_handles / db.query / db.execute / db.list_tables / db.describe_table`
2. `db_helper.py` 读取：
   - `AIASYS_DB_BROKER_URL`
   - `AIASYS_DB_SESSION_TOKEN`
   - `AIASYS_DB_DEFAULT_HANDLE`
3. helper 把请求发到 `/api/session-database`
4. backend 里的 `DatabaseAccessBroker` 根据句柄决定访问：
   - `builtin_db`
   - `connector:{id}`

因此当前必须明确：

- 容器不再依赖 `DB_DSN`
- 容器不再依赖 `DB_NAME`
- 容器默认不直接持有数据库原始凭据

### 1.2 `172.17.0.1` 现在用来做什么

`172.17.0.1` 当前仍然是 Docker 可选运行时的关键地址，但语义已经变化：

- Docker 容器通过 `http://172.17.0.1:{PORT}` 访问宿主机上的 backend
- backend 再通过 broker 和后端服务访问数据库

也就是说，Docker 运行时当前最重要的网络链路是：

`container -> 172.17.0.1:{backend_port} -> /api/session-database`

容器直连某个内置数据库实例已经从默认链路里移除。

---

## 2. 为什么仍然保留 `172.17.0.1`

### 2.1 Docker 到宿主机 backend 的默认通路

当前 `get_default_runtime_database_broker_url_for_docker()` 返回：

`http://172.17.0.1:{PORT}`

这条链路的价值在于：

- Linux Docker 下稳定
- 不依赖不稳定的 `host.docker.internal`
- 可以让容器内 helper 统一访问宿主机上的 backend broker

### 2.2 本地与 Docker 的差异

当前默认 broker URL：

- Local runtime：`http://127.0.0.1:{PORT}`
- Docker runtime：`http://172.17.0.1:{PORT}`

因此当前需要关注的是：

- helper 能否访问 backend broker
- broker 再能否访问 built-in database 或 external connector

---

## 3. 当前相关配置点

### 3.1 Runtime helper 注入

当前 helper 环境变量由后端构造：

- `AIASYS_DB_BROKER_URL`
- `AIASYS_DB_SESSION_TOKEN`
- `AIASYS_DB_DEFAULT_HANDLE`

对应实现位置：

- `apps/backend/app/services/database_access_broker.py`
- `apps/backend/app/agents/tools/local_ipython_box.py`

### 3.2 容器内 helper

运行态 helper 位于：

- `apps/backend/agent_runtime_helpers/db_helper.py`

当前 helper 的关键约束：

- 没有 broker 就报错
- 不允许回退到 `DB_DSN` 直连
- 所有数据库动作都统一发到 `/api/session-database`

---

## 4. 当前排障顺序

### 4.1 运行时提示“数据库 broker 未配置”

优先检查：

1. 容器环境变量里是否有：
   - `AIASYS_DB_BROKER_URL`
   - `AIASYS_DB_SESSION_TOKEN`
2. 当前运行环境是否由新的 helper/broker 逻辑启动

### 4.2 容器访问 broker 失败

优先检查：

1. backend 是否在宿主机正常监听
2. 容器内是否能访问 `172.17.0.1:{PORT}`
3. `/api/session-database` 是否可达

可用类似方式快速探测：

```bash
docker run --rm <your-image> python - <<'PY'
import requests
url = "http://172.17.0.1:13001/health"
try:
    r = requests.get(url, timeout=3)
    print(r.status_code, r.text[:200])
except Exception as e:
    print("health failed:", e)
PY
```

### 4.3 broker 可达但数据库动作失败

这时要继续分层判断：

- `builtin_db`
  - 看 broker 到 `builtin_database_service.py` 的链路
- `connector:{id}`
  - 看当前运行时是否能看到这个 connector 句柄
  - 看 `grant / approval_policy`
  - 看目标数据库账号 / 角色是否真有权限

---

## 5. 当前不应继续使用的旧排障口径

下面这些旧排障路径当前都不应再作为默认主口径：

- “先去容器里找 `DB_DSN`”
- “容器里直接 `create_engine(os.environ['DB_DSN'])`”
- “数据库网络问题就是容器直连内置数据库的问题”

当前应该优先看的是真实分层：

1. helper 环境变量是否存在
2. helper 能否访问 broker
3. broker 能否解析 session token
4. broker 再能否访问对应数据库资源

---

## 6. 一句话结论

当前 Docker 网络配置文档的关键点已经改为“如何让容器稳定访问 backend broker，并由 broker 统一访问 built-in database 与 external connectors”。`172.17.0.1` 仍是 Docker 到宿主机的默认稳定路径，但它服务的是 broker-only runtime helper 主链，内置数据库不再是这条链路的必经前提。

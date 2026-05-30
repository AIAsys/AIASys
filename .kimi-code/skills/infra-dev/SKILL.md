---
name: infra-dev
description: Develop infrastructure configurations including Docker, Nginx, and deployment scripts. Use when writing Dockerfiles, configuring docker-compose, setting up Nginx, or creating deployment automation. This skill covers multi-stage Docker builds, container orchestration, and production deployment best practices. Always use this skill when the user asks you to configure Docker, set up Nginx, or work with deployment infrastructure.
---

# 基础设施开发

Docker、Nginx 和部署配置的开发规范，确保系统可稳定运行和便捷部署。

|---

## AIASys 当前启动与部署真相

在 AIASys 当前仓库里，优先遵守下面这组现实边界：

- 本地开发统一入口：`./dev.sh`
- 正式部署主线：源码部署 + `infra/deploy/README.md`
- 主应用当前不支持整站 Docker Compose 部署
- Docker 当前主要用于 PostgreSQL、分组件基础设施和运行时相关能力

如果用户要求"部署 AIASys 主应用"，不要默认去找整站 `docker compose`；先看 `infra/deploy/README.md` 与根目录启动脚本。

### 已知缺口与排雷（重要）

以下是在审查部署设计时发现的**现实阻塞项**，动代码前必须先确认：

1. **`infra/docker/postgres/manage.sh` 不存在**
   - `deploy_init.sh` 第 207 行显式调用该脚本启动主库
   - `README.md` 声称本地 `./dev.sh` 也调用同一份脚本，但 `./dev.sh` 实际调用的是 `scripts/dev/cli.sh`，其中并未引用 `manage.sh`
   - **这是首次部署的阻塞性 bug**，必须先补上 `manage.sh`（至少支持 `start/stop/status/logs`）才能在新服务器跑通

2. **部署流程未执行数据库迁移**
   - `deploy_init.sh` 和 `deploy_update.sh` 中均没有 `alembic upgrade head` 或同类命令
   - 若代码更新伴随 schema 变更，部署不会自动 apply，属于隐性风险

3. **前端实际由 Python 静态服务器托管**
   - 远端并非 Nginx 直接 `root` 指向 `dist`
   - 而是 PM2 运行 `static_web_server.py`（基于 `ThreadingHTTPServer`）
   - 并发能力和静态资源优化弱于 Nginx 直供

4. **单实例、无 HTTPS、无负载均衡**
   - PM2 中后端 `instances: 1`，未利用多核
   - Nginx 配置仅监听 `80`，无 `443 ssl`
   - 水平扩展路径不清晰

|---


## 核心原则

1. **多阶段构建**：减小镜像体积，分离构建和运行环境
2. **安全优先**：敏感信息不进入镜像，使用非 root 用户
3. **健康检查**：所有服务必须配置健康检查端点
4. **日志收集**：结构化日志，便于集中收集

|---

## Docker 配置

### Python/FastAPI 后端

```dockerfile
# Dockerfile
# 阶段 1：构建阶段
FROM python:3.11-slim as builder

WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# 阶段 2：运行阶段
FROM python:3.11-slim

WORKDIR /app

# 创建非 root 用户
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# 从构建阶段复制依赖
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# 复制应用代码
COPY ./app ./app

# 设置权限
RUN chown -R appuser:appgroup /app
USER appuser

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### React/Vite 前端

```dockerfile
# Dockerfile.frontend
# 阶段 1：构建
FROM node:20-alpine as builder

WORKDIR /app

# 安装依赖
COPY package*.json ./
RUN npm ci

# 构建
COPY . .
RUN npm run build

# 阶段 2：Nginx 服务
FROM nginx:alpine

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s \
    CMD wget --no-verbose --tries=1 --spider http://localhost:80/ || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

### .dockerignore

```
# Git
.git
.gitignore

# Python
__pycache__
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info
dist
build
.venv
venv/
ENV/

# Node
node_modules
npm-debug.log
yarn-error.log
.pnpm-debug.log

# IDE
.idea
.vscode
*.swp
*.swo
*~

# 测试和文档
tests/
docs/
*.md

# 环境变量（重要！）
.env
.env.*
!.env.example

# 本地数据
data/
*.db
*.sqlite

# 其他
.DS_Store
*.log
```

|---

## Docker Compose

### 开发环境

```yaml
# docker-compose.dev.yml
version: '3.8'

services:
  backend:
    build:
      context: ./apps/backend
      dockerfile: Dockerfile
    ports:
      - "13001:8000"
    volumes:
      - ./apps/backend/app:/app/app
      - ./data:/app/data
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/aiasys
      - REDIS_URL=redis://redis:6379
      - DEBUG=true
    depends_on:
      - db
      - redis
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    build:
      context: ./apps/web
      dockerfile: Dockerfile
    ports:
      - "13000:80"
    depends_on:
      - backend

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: aiasys
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  postgres_data:
  redis_data:
```

### 生产环境

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  backend:
    build:
      context: ./apps/backend
      dockerfile: Dockerfile
    restart: unless-stopped
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - SECRET_KEY=***
    depends_on:
      db:
        condition: service_healthy
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M

  frontend:
    build:
      context: ./apps/web
      dockerfile: Dockerfile
    restart: unless-stopped
    depends_on:
      - backend

  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./infra/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./infra/nginx/ssl:/etc/nginx/ssl:ro
    depends_on:
      - frontend
      - backend

  db:
    image: postgres:15-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

|---

## Nginx 配置

### 基础配置

```nginx
# nginx.conf
upstream backend {
    server backend:8000;
}

upstream frontend {
    server frontend:80;
}

server {
    listen 80;
    server_name localhost;

    # 前端静态资源
    location / {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    # API 代理
    location /api/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # 超时设置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # 健康检查
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
```

### HTTPS 配置

```nginx
server {
    listen 80;
    server_name aiasys.example.com;
    
    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name aiasys.example.com;

    # SSL 证书
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    
    # SSL 配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # 其他配置同上...
}
```

### 负载均衡

```nginx
upstream backend_cluster {
    least_conn;  # 最少连接数策略
    
    server backend_1:8000 weight=5;
    server backend_2:8000 weight=5;
    server backend_3:8000 backup;  # 备用
    
    keepalive 32;
}
```

|---

## 部署脚本

### 部署脚本

```bash
#!/bin/bash
# deploy.sh

set -e

echo "=== AIASys 部署脚本 ==="

# 加载环境变量
export $(grep -v '^#' .env | xargs)

# 构建镜像
echo "[1/4] 构建 Docker 镜像..."
docker-compose -f docker-compose.prod.yml build

# 数据库迁移
echo "[2/4] 执行数据库迁移..."
docker-compose -f docker-compose.prod.yml run --rm backend alembic upgrade head

# 启动服务
echo "[3/4] 启动服务..."
docker-compose -f docker-compose.prod.yml up -d

# 健康检查
echo "[4/4] 健康检查..."
sleep 5

# 检查后端
if curl -s http://localhost:13001/health > /dev/null; then
    echo "(正确) 后端健康检查通过"
else
    echo "错误： 后端健康检查失败"
    exit 1
fi

# 检查前端
if curl -s -o /dev/null -w "%{http_code}" http://localhost:13000 | grep -q "200\|301\|302"; then
    echo "(正确) 前端健康检查通过"
else
    echo "错误： 前端健康检查失败"
    exit 1
fi

# 检查数据库
if docker-compose -f docker-compose.prod.yml exec -T db pg_isready -U postgres > /dev/null; then
    echo "(正确) 数据库健康检查通过"
else
    echo "错误： 数据库健康检查失败"
    exit 1
fi

echo "=== 部署完成 ==="
```

### 备份脚本

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="aiasys"

# 创建备份
docker-compose exec -T db pg_dump -U postgres $DB_NAME | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"

# 保留最近 7 天的备份
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +7 -delete

echo "备份完成: db_$DATE.sql.gz"
```

|---

## AIASys 部署标准

### 当前部署口径

- **生产环境**：源码部署 + PM2 + Nginx + Docker PostgreSQL
- **公网入口**：统一走 `Nginx :80`
- **内部端口**：前端 `13000`，后端 `13001`
- **前端构建**：本地构建 `dist`，远端只托管静态产物

### 部署后验证

```bash
# 必须验证的三条链路
curl http://localhost/health          # Nginx 健康
curl http://localhost:13001/health    # 后端健康
curl http://localhost:13001/api/graph/health  # Graph 服务健康
```

|---

## 快速检查清单

**编写 Dockerfile 时：**
- [ ] 使用多阶段构建
- [ ] 使用非 root 用户运行
- [ ] 配置健康检查
- [ ] 添加 .dockerignore

**配置 Docker Compose 时：**
- [ ] 服务有健康检查
- [ ] 敏感信息使用环境变量
- [ ] 数据使用 volumes 持久化
- [ ] 生产环境配置资源限制

**配置 Nginx 时：**
- [ ] 配置反向代理
- [ ] 添加安全头
- [ ] 配置 HTTPS（生产）
- [ ] 配置 gzip 压缩

|---

*基础设施是系统稳定的基石——可靠、安全、可维护。*

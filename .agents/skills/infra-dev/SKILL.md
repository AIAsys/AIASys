---
name: infra-dev
description: |
  AIASys 基础设施与部署配置开发。用于编写或修改 Docker 配置、部署脚本、Nginx 配置时。
  注意：AIASys 主应用当前不支持整站 Docker Compose 部署，优先参考 infra/deploy/README.md。
---

# 基础设施开发

AIASys 的部署与基础设施配置规范。

---

## AIASys 当前部署真相

在 AIASys 当前仓库里，优先遵守下面这组现实边界：

- 本地开发统一入口：`./dev.sh`
- 正式部署主线：源码部署 + PM2 + Nginx + Docker PostgreSQL，参考 `infra/deploy/README.md`
- 主应用当前**不支持**整站 Docker Compose 部署
- Docker 当前主要用于 PostgreSQL、分组件基础设施和运行时相关能力
- 公网入口统一走 Nginx `:80`
- 内部端口：前端 `13000`，后端 `13001`

如果用户要求"部署 AIASys 主应用"，不要默认去找整站 `docker compose`；先看 `infra/deploy/README.md` 与根目录启动脚本。

---

## 核心原则

1. **多阶段构建**：减小镜像体积，分离构建和运行环境
2. **安全优先**：敏感信息不进入镜像，使用非 root 用户
3. **健康检查**：所有服务必须配置健康检查端点
4. **日志收集**：结构化日志，便于集中收集

---

## 部署后验证

```bash
# 必须验证的三条链路
curl http://localhost/health                    # Nginx 健康
curl http://localhost:13001/health              # 后端健康
curl http://localhost:13001/api/graph/health    # Graph 服务健康
```

---

## 快速检查清单

**编写 Dockerfile 时：**
- [ ] 使用多阶段构建
- [ ] 使用非 root 用户运行
- [ ] 配置健康检查
- [ ] 添加 .dockerignore

**配置 Docker Compose 时：**
- [ ] 服务有健康检查
- [ ] 敏感信息使用环境变量，不硬编码
- [ ] 数据使用 volumes 持久化
- [ ] 生产环境配置资源限制

**配置 Nginx 时：**
- [ ] 配置反向代理
- [ ] 添加安全头（X-Frame-Options、X-Content-Type-Options 等）
- [ ] 配置 HTTPS（生产环境）
- [ ] 配置 gzip 压缩
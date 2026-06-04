# Docker 镜像构建说明

AIASys 当前使用官方运行环境镜像执行 Docker 模式下的代码请求。默认官方镜像为
`aiasys/python-data-analysis:0.3.9`。

## 当前原则

- 镜像初始化优先加载预构建的 tar 文件（见下方产物位置）
- tar 不可用或镜像校验失败时，按官方 Dockerfile 重建
- 不对官方环境做静默 fallback，避免用户误以为自己仍在使用目标环境
- `sandbox.default_mode=local` 且 `enabled_modes=["local"]` 时跳过 Docker 官方镜像初始化
- `sandbox.default_mode=docker` 且启用 Docker 时由后端启动后台触发初始化

## 构建命令

```bash
cd apps/backend

# 构建并保存默认官方环境（使用 Docker）
docker build -t aiasys/python-data-analysis:0.3.9 .
docker save aiasys/python-data-analysis:0.3.9 -o .docker-images/python_data_analysis.tar
```

## 产物位置

- Docker 镜像：`aiasys/python-data-analysis:0.3.9`
- tar 文件：`apps/backend/.docker-images/python_data_analysis.tar`

## 使用方式

- 后端启动或部署时自动初始化运行环境镜像
- 运行时通过后端 sandbox 初始化与执行链路校验目标环境镜像
- 当前宿主机工作区 `workspaces/{user_id}/{session_id}/` 会挂载到容器内 `/workspace/`

## 更新镜像时需要同步的内容

1. `apps/web/src/config/environments.json`
2. 相关部署 / 验收文档中的镜像标签
3. 如有行为变化，再补 changelog 与验证记录
#!/usr/bin/env bash

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

load_deploy_env
check_local_requirements

REMOTE_SCRIPT=$(cat <<'EOF'
set -euo pipefail

echo "========== 系统信息 =========="
echo "主机名: $(hostname)"
echo "系统: $(grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '"')"
echo ""

echo "========== 内存使用 =========="
free -h
echo ""

echo "========== 磁盘使用 =========="
df -h
echo ""

echo "========== Docker 容器 =========="
if command -v docker >/dev/null 2>&1; then
  docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
else
  echo "Docker 未安装"
fi
echo ""

echo "========== PM2 =========="
if command -v pm2 >/dev/null 2>&1; then
  pm2 status
else
  echo "PM2 未安装"
fi
echo ""

echo "========== 端口监听 =========="
ss -tlnp | grep -E ':(13000|13001|5433|5434)' || true
EOF
)

echo "=== 检查部署目标 ${DEPLOY_TARGET} / 服务器 ${SERVER_USER}@${SERVER_IP}:${SERVER_PORT} ==="
echo ""
run_remote_script "${REMOTE_SCRIPT}"
echo ""
echo "=== 检查完成 ==="

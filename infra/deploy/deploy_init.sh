#!/usr/bin/env bash

# AIASys 首次部署脚本
#
# 国内镜像支持：
#   UV_DEFAULT_INDEX 和 UV_PYTHON_INSTALL_MIRROR 由 uv 原生读取，
#   请在 uv 侧配置（~/.config/uv/config.toml 或环境变量）。
#   详见 https://docs.astral.sh/uv/configuration/
#
#   UV_INSTALLER_MIRROR 由本脚本处理：
#     export UV_INSTALLER_MIRROR="https://gh.chjina.com/https://github.com/astral-sh"

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

load_deploy_env
check_local_requirements

ARCHIVE_PATH="$(create_release_bundle)"
ARCHIVE_NAME="$(basename "${ARCHIVE_PATH}")"
ARCHIVE_DIR="$(dirname "${ARCHIVE_PATH}")"
cleanup() {
  rm -rf "${ARCHIVE_DIR}"
}
trap cleanup EXIT

echo "=========================================="
echo "  AIASys 首次部署"
echo "  目标: ${DEPLOY_TARGET}"
echo "  服务器: ${SERVER_USER}@${SERVER_IP}:${SERVER_PORT}"
echo "=========================================="
echo ""

log_info "上传部署包..."
copy_to_remote "${ARCHIVE_PATH}" "/tmp/${ARCHIVE_NAME}"
log_success "部署包上传完成"

REMOTE_SCRIPT=$(cat <<EOF
set -euo pipefail

REMOTE_DIR="${REMOTE_DIR}"
ARCHIVE_PATH="/tmp/${ARCHIVE_NAME}"
BACKEND_PORT="$(remote_backend_port)"
FRONTEND_PORT="$(remote_frontend_port)"
DB_PORT="$(remote_db_port)"
SANDBOX_DB_PORT="$(remote_sandbox_db_port)"

install_base_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    local packages=()
    command -v curl >/dev/null 2>&1 || packages+=(curl)
    command -v git >/dev/null 2>&1 || packages+=(git)
    command -v gcc >/dev/null 2>&1 || packages+=(build-essential)
    command -v make >/dev/null 2>&1 || packages+=(build-essential)
    command -v python3 >/dev/null 2>&1 || packages+=(python3 python3-pip python3-venv)

    if [ "\${#packages[@]}" -gt 0 ]; then
      apt-get update -y
      apt-get install -y "\${packages[@]}"
    fi
    return 0
  fi

  if command -v dnf >/dev/null 2>&1; then
    local packages=()
    command -v curl >/dev/null 2>&1 || packages+=(curl ca-certificates)
    command -v git >/dev/null 2>&1 || packages+=(git)
    command -v gcc >/dev/null 2>&1 || packages+=(gcc gcc-c++ make)
    command -v make >/dev/null 2>&1 || packages+=(make)
    command -v python3 >/dev/null 2>&1 || packages+=(python3 python3-pip)

    if [ "\${#packages[@]}" -gt 0 ]; then
      dnf install -y "\${packages[@]}"
    fi
    return 0
  fi
}

install_node() {
  if command -v node >/dev/null 2>&1 && [ "\$(node -v | sed 's/^v//;s/\..*//')" -ge 22 ]; then
    return 0
  fi

  if command -v apt-get >/dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y nodejs
    return 0
  fi

  if command -v dnf >/dev/null 2>&1; then
    curl -fsSL https://rpm.nodesource.com/setup_22.x | bash -
    dnf install -y nodejs
    return 0
  fi

  echo "[ERROR] 无法自动安装 Node.js 22+" >&2
  exit 1
}

install_docker() {
  if command -v docker >/dev/null 2>&1; then
    return 0
  fi

  echo "[ERROR] 服务器未安装 Docker，请先手动安装后重试" >&2
  exit 1
}

install_nginx() {
  if command -v nginx >/dev/null 2>&1 || [ -x /usr/sbin/nginx ]; then
    return 0
  fi

  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    apt-get install -y nginx
    return 0
  fi

  if command -v dnf >/dev/null 2>&1; then
    dnf install -y nginx || true
    if command -v nginx >/dev/null 2>&1 || [ -x /usr/sbin/nginx ]; then
      return 0
    fi
  fi

  return 1
}

use_host_nginx() {
  command -v nginx >/dev/null 2>&1 || [ -x /usr/sbin/nginx ]
}

apply_nginx() {
  local nginx_bin="nginx"
  [ -x /usr/sbin/nginx ] && nginx_bin="/usr/sbin/nginx"

  if use_host_nginx; then
    mkdir -p /etc/nginx/conf.d
    cp "\${REMOTE_DIR}/infra/deploy/nginx/aiasys.conf" /etc/nginx/conf.d/aiasys.conf
    rm -f /etc/nginx/conf.d/aiasys-frontend.conf
    "\${nginx_bin}" -t
    systemctl enable nginx || true
    systemctl reload nginx || systemctl restart nginx
    return 0
  fi

  if ss -ltnp 2>/dev/null | grep -q ':80 '; then
    pkill -x nginx >/dev/null 2>&1 || true
    fuser -k 80/tcp >/dev/null 2>&1 || true
    sleep 1
  fi

  docker rm -f aiasys-nginx >/dev/null 2>&1 || true
  docker run -d \
    --name aiasys-nginx \
    --restart unless-stopped \
    --network host \
    -v "\${REMOTE_DIR}/infra/deploy/nginx/aiasys.conf:/etc/nginx/conf.d/default.conf:ro" \
    nginx:1.27-alpine >/dev/null
}

install_base_packages

install_node
install_docker
install_nginx || true

if ! command -v uv >/dev/null 2>&1; then
  if [ -n "${UV_INSTALLER_MIRROR:-}" ]; then
    curl -LsSf "${UV_INSTALLER_MIRROR}/uv/install.sh" | sh
  else
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  export PATH="\$HOME/.local/bin:\$PATH"
fi

export PATH="\$HOME/.local/bin:\$PATH"

if ! command -v pm2 >/dev/null 2>&1; then
  npm install -g pm2
fi

mkdir -p "\${REMOTE_DIR}"
rm -rf "\${REMOTE_DIR}/.release_tmp"
mkdir -p "\${REMOTE_DIR}/.release_tmp"
tar xzf "\${ARCHIVE_PATH}" -C "\${REMOTE_DIR}/.release_tmp"

mkdir -p "\${REMOTE_DIR}/apps/backend/workspaces" "\${REMOTE_DIR}/apps/backend/logs" "\${REMOTE_DIR}/apps/backend/data"

cp -a "\${REMOTE_DIR}/.release_tmp/." "\${REMOTE_DIR}/"
rm -rf "\${REMOTE_DIR}/.release_tmp" "\${ARCHIVE_PATH}"

cd "\${REMOTE_DIR}/apps/backend"
if [ -x /opt/miniconda/envs/py312/bin/python ]; then
  UV_PYTHON=/opt/miniconda/envs/py312/bin/python uv sync --frozen --no-dev
else
  uv python install 3.12
  uv sync --frozen --no-dev
fi
.venv/bin/python scripts/init_runtime_env_images.py

cd "\${REMOTE_DIR}/apps/web"
if [ -f dist/index.html ]; then
  echo "[INFO] 检测到预构建前端产物，跳过远端 npm 安装与构建"
else
  if [ -f package-lock.json ]; then
    npm ci
    sha256sum package-lock.json > .deploy-package-lock.sha256
  else
    npm install
    if [ -f package-lock.json ]; then
      sha256sum package-lock.json > .deploy-package-lock.sha256
    fi
  fi
  npm run build
fi

cd "\${REMOTE_DIR}"
bash infra/docker/postgres/manage.sh start

apply_nginx

docker rm -f aiasys-sandbox-db >/dev/null 2>&1 || true
docker run -d \
  --name aiasys-sandbox-db \
  --restart unless-stopped \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=postgres \
  -p "\${SANDBOX_DB_PORT}:5432" \
  postgres:16-alpine >/dev/null

pm2 delete aiasys-backend >/dev/null 2>&1 || true
pm2 delete aiasys-frontend >/dev/null 2>&1 || true
pm2 start ecosystem.config.cjs --update-env
pm2 save

wait_for_http() {
  local target="\$1"
  local attempts="\${2:-30}"
  local sleep_seconds="\${3:-2}"

  for _ in \$(seq 1 "\${attempts}"); do
    if curl -fsS "\${target}" >/dev/null 2>&1; then
      return 0
    fi
    sleep "\${sleep_seconds}"
  done

  echo "[ERROR] 部署烟测失败: \${target}" >&2
  pm2 status >&2 || true
  return 1
}

for target in "http://127.0.0.1/health" "http://127.0.0.1/api/graph/health" "http://127.0.0.1/"; do
  wait_for_http "\${target}"
done

echo ""
echo "=========================================="
echo "部署完成"
echo "=========================================="
echo "前端: http://${SERVER_IP}:\${FRONTEND_PORT}"
echo "后端: http://${SERVER_IP}:\${BACKEND_PORT}"
echo "数据库: ${SERVER_IP}:\${DB_PORT}"
echo ""
EOF
)

log_info "执行远程初始化部署..."
run_remote_script "${REMOTE_SCRIPT}"
log_success "首次部署脚本执行完成"

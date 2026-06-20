#!/usr/bin/env bash

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
echo "  AIASys 更新部署"
echo "  目标: ${DEPLOY_TARGET}"
echo "  服务器: ${SERVER_USER}@${SERVER_IP}:${SERVER_PORT}"
echo "=========================================="
echo ""

log_info "上传更新包..."
copy_to_remote "${ARCHIVE_PATH}" "/tmp/${ARCHIVE_NAME}"
log_success "更新包上传完成"

REMOTE_SCRIPT=$(cat <<EOF
set -euo pipefail

REMOTE_DIR="${REMOTE_DIR}"
ARCHIVE_PATH="/tmp/${ARCHIVE_NAME}"

if ! command -v uv >/dev/null 2>&1; then
  echo "[ERROR] 目标服务器缺少 uv，请先执行 deploy_init.sh" >&2
  exit 1
fi

export PATH="\$HOME/.local/bin:\$PATH"

should_run_frontend_install() {
  if [ ! -f package-lock.json ]; then
    return 0
  fi
  if [ ! -d node_modules ]; then
    return 0
  fi
  if [ ! -f .deploy-package-lock.sha256 ]; then
    return 0
  fi
  if sha256sum --check --status .deploy-package-lock.sha256; then
    return 1
  fi
  return 0
}

use_host_nginx() {
  command -v nginx >/dev/null 2>&1 || [ -x /usr/sbin/nginx ]
}

apply_nginx() {
  local nginx_bin="nginx"
  [ -x /usr/sbin/nginx ] && nginx_bin="/usr/sbin/nginx"

  if use_host_nginx; then
    mkdir -p /etc/nginx/conf.d
    cp "./infra/deploy/nginx/aiasys.conf" /etc/nginx/conf.d/aiasys.conf
    rm -f /etc/nginx/conf.d/aiasys-frontend.conf
    "\${nginx_bin}" -t
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

if ! command -v pm2 >/dev/null 2>&1; then
  echo "[ERROR] 目标服务器缺少 pm2，请先执行 deploy_init.sh" >&2
  exit 1
fi

mkdir -p "\${REMOTE_DIR}/.release_tmp"
tar xzf "\${ARCHIVE_PATH}" -C "\${REMOTE_DIR}/.release_tmp"
cp -a "\${REMOTE_DIR}/.release_tmp/." "\${REMOTE_DIR}/"
rm -rf "\${REMOTE_DIR}/.release_tmp" "\${ARCHIVE_PATH}"

cd "\${REMOTE_DIR}/apps/backend"
uv sync --frozen --no-dev
.venv/bin/python scripts/init_runtime_env_images.py

cd "\${REMOTE_DIR}/apps/web"
if [ -f dist/index.html ]; then
  echo "[INFO] 检测到预构建前端产物，跳过远端 npm 安装与构建"
else
  if [ -f package-lock.json ] && should_run_frontend_install; then
    npm ci
    sha256sum package-lock.json > .deploy-package-lock.sha256
  elif [ -f package-lock.json ]; then
    echo "[INFO] 前端依赖未变化，跳过远端 npm ci"
  else
    npm install
    if [ -f package-lock.json ]; then
      sha256sum package-lock.json > .deploy-package-lock.sha256
    fi
  fi
  npm run build
fi

cd "\${REMOTE_DIR}"
apply_nginx

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

  echo "[ERROR] 更新部署烟测失败: \${target}" >&2
  pm2 status >&2 || true
  return 1
}

for target in "http://127.0.0.1/health" "http://127.0.0.1/api/graph/health" "http://127.0.0.1/"; do
  wait_for_http "\${target}"
done

echo "更新完成"
EOF
)

log_info "执行远程更新部署..."
run_remote_script "${REMOTE_SCRIPT}"
log_success "更新部署脚本执行完成"

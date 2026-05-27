#!/bin/bash

set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/../.." && pwd)"
DEPLOY_ENV_FILE="${DEPLOY_DIR}/.env"
BACKEND_CONFIG_FILE="${PROJECT_ROOT}/apps/backend/config.json"
BACKEND_CONFIG_EXAMPLE="${PROJECT_ROOT}/apps/backend/config.example.json"

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
  echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
  echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1" >&2
}

ensure_backend_config() {
  if [ -f "${BACKEND_CONFIG_FILE}" ]; then
    return 0
  fi

  if [ ! -f "${BACKEND_CONFIG_EXAMPLE}" ]; then
    log_error "缺少后端配置模板: ${BACKEND_CONFIG_EXAMPLE}"
    return 1
  fi

  cp "${BACKEND_CONFIG_EXAMPLE}" "${BACKEND_CONFIG_FILE}"
  log_warn "已创建 apps/backend/config.json，请先确认部署配置。"
}

load_deploy_env() {
  local deploy_target_override="${DEPLOY_TARGET:-}"

  if [ ! -f "${DEPLOY_ENV_FILE}" ]; then
    log_error "缺少部署配置: ${DEPLOY_ENV_FILE}"
    log_error "请先复制 infra/deploy/.env.example 为 infra/deploy/.env 并填写参数。"
    return 1
  fi

  set -a
  source "${DEPLOY_ENV_FILE}"
  set +a

  if [ -n "${deploy_target_override}" ]; then
    DEPLOY_TARGET="${deploy_target_override}"
  fi

  DEPLOY_TARGET="$(printf '%s' "${DEPLOY_TARGET:-test}" | tr '[:upper:]' '[:lower:]')"
  local target_prefix=""
  case "${DEPLOY_TARGET}" in
    test|testing|staging)
      DEPLOY_TARGET="test"
      target_prefix="TEST"
      ;;
    prod|production|release)
      DEPLOY_TARGET="prod"
      target_prefix="PROD"
      ;;
    single|default)
      DEPLOY_TARGET="single"
      ;;
    *)
      log_error "未知 DEPLOY_TARGET: ${DEPLOY_TARGET}"
      log_error "允许值: test, prod, single"
      return 1
      ;;
  esac

  if [ -n "${target_prefix}" ]; then
    local env_name prefixed_env value
    for env_name in \
      SERVER_IP SERVER_PORT SERVER_USER SERVER_PASS SSH_KEY_PATH REMOTE_DIR \
      REMOTE_FRONTEND_PORT REMOTE_BACKEND_PORT REMOTE_PUBLIC_API_BASE_URL \
      REMOTE_DB_HOST REMOTE_DB_PORT REMOTE_DB_USER REMOTE_DB_PASSWORD REMOTE_DB_NAME \
      REMOTE_SANDBOX_DB_HOST REMOTE_SANDBOX_DB_PORT REMOTE_SANDBOX_DB_USER REMOTE_SANDBOX_DB_PASSWORD \
      DEPLOY_AUTH_MODE DEPLOY_PACKAGE_NAME DEPLOY_BUILD_FRONTEND_LOCALLY \
      DEPLOY_SANDBOX_MODE DEPLOY_SANDBOX_ALLOW_LOCAL DEPLOY_SANDBOX_DEFAULT_MODE DEPLOY_SANDBOX_ENABLED_MODES \
      DEPLOY_JWT_SECRET; do
      prefixed_env="${target_prefix}_${env_name}"
      value="${!prefixed_env:-${!env_name:-}}"
      if [ -n "${value}" ]; then
        printf -v "${env_name}" '%s' "${value}"
        export "${env_name}"
      fi
    done
  fi

  if [ -z "${SERVER_IP:-}" ] || [ -z "${SERVER_USER:-}" ]; then
    log_error "部署目标 ${DEPLOY_TARGET} 缺少服务器配置。"
    if [ -n "${target_prefix}" ]; then
      log_error "请在 infra/deploy/.env 中配置通用 SERVER_*，或直接配置 ${target_prefix}_SERVER_*。"
    else
      log_error "请在 infra/deploy/.env 中配置 SERVER_*。"
    fi
    return 1
  fi

  SERVER_PORT="${SERVER_PORT:-22}"
  REMOTE_DIR="${REMOTE_DIR:-/opt/aiasys}"
  DEPLOY_PACKAGE_NAME="${DEPLOY_PACKAGE_NAME:-aiasys-release}"

  if [ -n "${SSH_KEY_PATH:-}" ]; then
    SSH_KEY_PATH="${SSH_KEY_PATH/#\~/$HOME}"
    if [ ! -f "${SSH_KEY_PATH}" ]; then
      log_error "SSH_KEY_PATH 不存在: ${SSH_KEY_PATH}"
      return 1
    fi
  elif [ -z "${SERVER_PASS:-}" ]; then
    if [ -n "${target_prefix}" ]; then
      log_error "请在 infra/deploy/.env 中配置 SSH_KEY_PATH / SERVER_PASS，或直接配置 ${target_prefix}_SSH_KEY_PATH / ${target_prefix}_SERVER_PASS"
    else
      log_error "请在 infra/deploy/.env 中配置 SSH_KEY_PATH 或 SERVER_PASS"
    fi
    return 1
  fi
}

require_command() {
  local name="$1"
  if command -v "${name}" >/dev/null 2>&1; then
    return 0
  fi
  log_error "缺少命令: ${name}"
  return 1
}

check_local_requirements() {
  require_command tar
  require_command ssh
  require_command scp
  require_command python3

  if [ "${DEPLOY_BUILD_FRONTEND_LOCALLY:-1}" = "1" ]; then
    require_command npm
  fi

  if [ -z "${SSH_KEY_PATH:-}" ]; then
    require_command sshpass
  fi
}

json_get() {
  local path="$1"
  local default_value="${2:-}"

  python3 - "$BACKEND_CONFIG_FILE" "$path" "$default_value" <<'PY'
import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
path = sys.argv[2]
default = sys.argv[3]

if not config_path.exists():
    print(default)
    raise SystemExit(0)

with config_path.open("r", encoding="utf-8") as fh:
    value = json.load(fh)

for key in path.split("."):
    if isinstance(value, dict) and key in value:
        value = value[key]
    else:
        print(default)
        raise SystemExit(0)

if value is None:
    print(default)
elif isinstance(value, bool):
    print("true" if value else "false")
else:
    print(value)
PY
}

remote_backend_port() {
  echo "${REMOTE_BACKEND_PORT:-$(json_get server.port 13001)}"
}

remote_frontend_port() {
  echo "${REMOTE_FRONTEND_PORT:-13000}"
}

remote_db_port() {
  echo "${REMOTE_DB_PORT:-$(json_get database.port 5433)}"
}

remote_sandbox_db_port() {
  echo "${REMOTE_SANDBOX_DB_PORT:-$(json_get sandbox.postgres.port 5434)}"
}

remote_auth_mode() {
  echo "${DEPLOY_AUTH_MODE:-$(json_get auth.mode local)}"
}

remote_sandbox_default_mode() {
  echo "${DEPLOY_SANDBOX_DEFAULT_MODE:-${DEPLOY_SANDBOX_MODE:-docker}}"
}

remote_sandbox_enabled_modes() {
  if [ -n "${DEPLOY_SANDBOX_ENABLED_MODES:-}" ]; then
    echo "${DEPLOY_SANDBOX_ENABLED_MODES}"
    return 0
  fi

  local default_mode allow_local
  default_mode="$(remote_sandbox_default_mode)"
  allow_local="$(printf '%s' "${DEPLOY_SANDBOX_ALLOW_LOCAL:-false}" | tr '[:upper:]' '[:lower:]')"

  if [ "${allow_local}" = "true" ]; then
    if [ "${default_mode}" = "local" ]; then
      echo '["local","docker"]'
    else
      echo '["docker","local"]'
    fi
    return 0
  fi

  if [ "${default_mode}" = "local" ]; then
    echo '["local"]'
  else
    echo '["docker"]'
  fi
}

remote_public_api_base_url() {
  echo "${REMOTE_PUBLIC_API_BASE_URL:-http://${SERVER_IP}:$(remote_backend_port)}"
}

ssh_base_cmd() {
  if [ -n "${SSH_KEY_PATH:-}" ]; then
    printf "ssh -i %q -p %q -o StrictHostKeyChecking=no %q@%q" \
      "${SSH_KEY_PATH}" "${SERVER_PORT}" "${SERVER_USER}" "${SERVER_IP}"
  else
    printf "sshpass -p %q ssh -p %q -o StrictHostKeyChecking=no %q@%q" \
      "${SERVER_PASS}" "${SERVER_PORT}" "${SERVER_USER}" "${SERVER_IP}"
  fi
}

scp_base_cmd() {
  if [ -n "${SSH_KEY_PATH:-}" ]; then
    printf "scp -i %q -P %q -o StrictHostKeyChecking=no" \
      "${SSH_KEY_PATH}" "${SERVER_PORT}"
  else
    printf "sshpass -p %q scp -P %q -o StrictHostKeyChecking=no" \
      "${SERVER_PASS}" "${SERVER_PORT}"
  fi
}

run_remote_script() {
  local script_content="$1"
  local ssh_cmd
  ssh_cmd="$(ssh_base_cmd)"
  eval "${ssh_cmd}" <<EOF
${script_content}
EOF
}

run_remote_command() {
  local command="$1"

  run_remote_script "$(cat <<EOF
set -euo pipefail
export PATH="\$HOME/.local/bin:\$PATH"
cd "${REMOTE_DIR}"
${command}
EOF
)"
}

open_remote_shell() {
  local ssh_cmd
  ssh_cmd="$(ssh_base_cmd)"
  eval "${ssh_cmd}" -t "export PATH=\$HOME/.local/bin:\$PATH && cd ${REMOTE_DIR} && exec \${SHELL:-/bin/bash} -l"
}

copy_to_remote() {
  local local_path="$1"
  local remote_path="$2"
  local scp_cmd
  scp_cmd="$(scp_base_cmd)"
  eval "${scp_cmd}" "${local_path}" "${SERVER_USER}@${SERVER_IP}:${remote_path}"
}

prepare_frontend_dist() {
  if [ "${DEPLOY_BUILD_FRONTEND_LOCALLY:-1}" != "1" ]; then
    return 0
  fi

  local web_dir="${PROJECT_ROOT}/apps/web"

  if [ ! -f "${web_dir}/package.json" ]; then
    log_warn "未找到前端 package.json，跳过本地前端构建。"
    return 0
  fi

  log_info "本地构建前端产物..."
  if [ ! -d "${web_dir}/node_modules" ]; then
    (cd "${web_dir}" && npm ci)
  fi
  (cd "${web_dir}" && npm run build)
  log_success "前端产物构建完成"
}

create_release_bundle() {
  ensure_backend_config >&2
  prepare_frontend_dist >&2

  local bundle_root
  bundle_root="$(mktemp -d "/tmp/${DEPLOY_PACKAGE_NAME}.XXXXXX")"
  local stage_dir="${bundle_root}/stage"
  mkdir -p "${stage_dir}"

  local -a tar_excludes=(
    --exclude='.git'
    --exclude='.logs'
    --exclude='archive'
    --exclude='node_modules'
    --exclude='.venv'
    --exclude='__pycache__'
    --exclude='.pytest_cache'
    --exclude='.mypy_cache'
    --exclude='apps/backend/.venv'
    --exclude='apps/backend/.docker-images'
    --exclude='apps/backend/example_datas'
    --exclude='apps/backend/workspaces'
    --exclude='apps/backend/logs'
    --exclude='apps/backend/data/app.db'
    --exclude='apps/backend/data/graphs'
    --exclude='apps/backend/data/uploads'
    --exclude='infra/deploy/.env'
  )

  if [ "${DEPLOY_BUILD_FRONTEND_LOCALLY:-1}" != "1" ]; then
    tar_excludes+=(--exclude='dist')
  fi

  tar \
    "${tar_excludes[@]}" \
    -cf - -C "${PROJECT_ROOT}" . | tar -xf - -C "${stage_dir}"

  render_backend_config "${stage_dir}/apps/backend/config.json"
  render_frontend_env "${stage_dir}/apps/web/.env.production"
  render_ecosystem_config "${stage_dir}/ecosystem.config.cjs"
  render_nginx_config "${stage_dir}/infra/deploy/nginx/aiasys.conf"

  local archive_path="${bundle_root}/${DEPLOY_PACKAGE_NAME}.tar.gz"
  tar -czf "${archive_path}" -C "${stage_dir}" .

  echo "${archive_path}"
}

render_backend_config() {
  local output_path="$1"
  local backend_port auth_mode sandbox_default_mode sandbox_enabled_modes
  backend_port="$(remote_backend_port)"
  auth_mode="$(remote_auth_mode)"
  sandbox_default_mode="$(remote_sandbox_default_mode)"
  sandbox_enabled_modes="$(remote_sandbox_enabled_modes)"

  python3 - "$BACKEND_CONFIG_FILE" "$output_path" "$backend_port" "$auth_mode" \
    "${sandbox_default_mode}" "${sandbox_enabled_modes}" "${DEPLOY_JWT_SECRET:-}" <<'PY'
import json
import sys
from pathlib import Path

(
    source_path,
    output_path,
    backend_port,
    auth_mode,
    sandbox_default_mode_override,
    sandbox_enabled_modes_override,
    jwt_secret_override,
) = sys.argv[1:]

with Path(source_path).open("r", encoding="utf-8") as fh:
    config = json.load(fh)

config.setdefault("server", {})
config.setdefault("auth", {})
config.setdefault("sandbox", {})

config["server"]["host"] = "0.0.0.0"
config["server"]["port"] = int(backend_port)
config["server"]["debug"] = False

config["auth"]["mode"] = auth_mode
if jwt_secret_override:
    config["auth"]["jwt_secret"] = jwt_secret_override

supported_modes = ("docker", "local")
enabled_modes = []
try:
    parsed_modes = json.loads(sandbox_enabled_modes_override)
    if isinstance(parsed_modes, list):
        for mode in parsed_modes:
            mode = str(mode).lower()
            if mode in supported_modes and mode not in enabled_modes:
                enabled_modes.append(mode)
except json.JSONDecodeError:
    pass

default_mode = str(sandbox_default_mode_override).lower() if sandbox_default_mode_override else ""
if default_mode not in supported_modes:
    default_mode = enabled_modes[0] if enabled_modes else "docker"
if default_mode not in enabled_modes:
    enabled_modes.insert(0, default_mode)
if not enabled_modes:
    enabled_modes = [default_mode]

config["sandbox"]["default_mode"] = default_mode
config["sandbox"]["enabled_modes"] = enabled_modes
# 同步旧字段，便于旧版本回退时仍能读懂同一份配置。
config["sandbox"]["mode"] = default_mode
config["sandbox"]["allow_local"] = "local" in enabled_modes

output = Path(output_path)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

render_frontend_env() {
  local output_path="$1"
  cat >"${output_path}" <<EOF
VITE_API_BASE_URL=$(remote_public_api_base_url)
VITE_AUTH_MODE=$(remote_auth_mode)
EOF
}

render_nginx_config() {
  local output_path="$1"
  local backend_port frontend_port
  backend_port="$(remote_backend_port)"
  frontend_port="$(remote_frontend_port)"

  mkdir -p "$(dirname "${output_path}")"

  cat >"${output_path}" <<EOF
server {
  listen 80;
  server_name ${SERVER_IP} _;

  client_max_body_size 100m;

  location = /health {
    proxy_pass http://127.0.0.1:${backend_port}/health;
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
  }

  location /api/ {
    proxy_pass http://127.0.0.1:${backend_port}/api/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade \$http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_read_timeout 86400;
  }

  location /ws {
    proxy_pass http://127.0.0.1:${backend_port}/ws;
    proxy_http_version 1.1;
    proxy_set_header Upgrade \$http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_read_timeout 86400;
  }

  location / {
    proxy_pass http://127.0.0.1:${frontend_port}/;
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
  }
}
EOF
}

render_ecosystem_config() {
  local output_path="$1"
  local backend_port frontend_port
  backend_port="$(remote_backend_port)"
  frontend_port="$(remote_frontend_port)"

  cat >"${output_path}" <<EOF
module.exports = {
  apps: [
    {
      name: "aiasys-backend",
      cwd: "./apps/backend",
      script: "bash",
      args: "-lc 'export PATH=\$HOME/.local/bin:\$PATH && uv run uvicorn app.main:app --host 0.0.0.0 --port ${backend_port}'",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      env: {
        NODE_ENV: "production"
      }
    },
    {
      name: "aiasys-frontend",
      cwd: "./apps/web",
      script: "bash",
      args: "-lc 'export PATH=\$HOME/.local/bin:\$PATH && ../backend/.venv/bin/python ../../infra/deploy/static_web_server.py --dir dist --host 0.0.0.0 --port ${frontend_port}'",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "512M",
      env: {
        NODE_ENV: "production"
      }
    }
  ]
};
EOF
}

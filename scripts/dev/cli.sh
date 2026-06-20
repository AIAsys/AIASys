#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_PORT="${AIASYS_FRONTEND_PORT:-13000}"
BACKEND_PORT="${AIASYS_BACKEND_PORT:-13001}"
BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"
FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}"

command_name="${1:-start}"
if [[ "$#" -gt 0 ]]; then
  shift
fi

print_usage() {
  cat <<EOF
Usage:
  ./dev.sh              启动前后端开发服务
  ./dev.sh start        启动前后端开发服务
  ./dev.sh status       查看前后端端口与健康状态
  ./dev.sh design-lint  校验根目录 DESIGN.md
  ./dev.sh design-export-css [output]
                        从 DESIGN.md 生成 Tailwind 4 CSS 变量草案
  ./dev.sh design-export-runtime
                        生成当前运行时变量候选主题和映射说明
  ./dev.sh setup-hooks  启用仓库内置 Git hooks
EOF
}

check_url_ready() {
  local url="$1"
  curl -fsS "$url" >/dev/null 2>&1
}

# 端口探测：返回 0 表示空闲，1 表示被占用
probe_port() {
  local host="$1" port="$2"
  local nc_rc=0 py_rc=0

  if command -v nc >/dev/null 2>&1; then
    if nc -z "$host" "$port" 2>/dev/null; then
      return 1  # 端口可达 = 被占用
    else
      return 0  # 端口不可达 = 空闲
    fi
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "
import socket
s = socket.socket()
s.settimeout(1)
try:
    s.connect(('$host', $port))
    s.close()
except:
    exit(1)
" 2>/dev/null
    py_rc=$?
    if [[ $py_rc -eq 0 ]]; then
      return 1  # 端口可达 = 被占用
    else
      return 0  # 端口不可达 = 空闲
    fi
  else
    return 1
  fi
}

# 查找可用端口
find_available_port() {
  local host="$1" start="$2" max="${3:-200}"
  for ((p = start; p < start + max; p++)); do
    if probe_port "$host" "$p"; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

status_command() {
  local frontend_status="down"
  local backend_status="down"

  if check_url_ready "${FRONTEND_URL}/"; then
    frontend_status="up"
  fi

  if check_url_ready "${BACKEND_URL}/health"; then
    backend_status="up"
  fi

  echo "frontend ${FRONTEND_URL}: ${frontend_status}"
  echo "backend  ${BACKEND_URL}: ${backend_status}"

  if [[ "${frontend_status}" == "up" && "${backend_status}" == "up" ]]; then
    return 0
  fi

  return 1
}

start_backend() {
  (
    cd "${PROJECT_ROOT}/apps/backend"
    exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${BACKEND_PORT}"
  ) &
  BACKEND_PID=$!
}

start_frontend() {
  (
    cd "${PROJECT_ROOT}/apps/web"
    export VITE_API_TARGET="${BACKEND_URL}"
    exec npm run dev -- --host 0.0.0.0 --port "${FRONTEND_PORT}"
  ) &
  FRONTEND_PID=$!
}

cleanup_children() {
  local exit_code=$?

  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "${FRONTEND_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "${BACKEND_PID}" >/dev/null 2>&1 || true
  fi

  wait "${FRONTEND_PID:-}" >/dev/null 2>&1 || true
  wait "${BACKEND_PID:-}" >/dev/null 2>&1 || true

  exit "${exit_code}"
}

case "${command_name}" in
  start)
    trap cleanup_children EXIT INT TERM

    # 检查后端端口
    BACKEND_LOCKED=false
    if [[ -n "${AIASYS_BACKEND_PORT:-}" ]]; then
      BACKEND_LOCKED=true
    fi
    if ! probe_port "127.0.0.1" "${BACKEND_PORT}"; then
      if ${BACKEND_LOCKED}; then
        echo "❌ 后端端口 ${BACKEND_PORT} 已被占用，且 AIASYS_BACKEND_PORT 已锁定" >&2
        exit 1
      fi
      NEW_BACKEND_PORT=$(find_available_port "127.0.0.1" "$((BACKEND_PORT + 1))")
      if [[ -z "${NEW_BACKEND_PORT}" ]]; then
        echo "❌ 无法为后端找到可用端口（起始: ${BACKEND_PORT}）" >&2
        exit 1
      fi
      echo "⚠ 后端端口 ${BACKEND_PORT} 被占用，自动切换到 ${NEW_BACKEND_PORT}"
      BACKEND_PORT="${NEW_BACKEND_PORT}"
      BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"
    fi

    # 检查前端端口
    FRONTEND_LOCKED=false
    if [[ -n "${AIASYS_FRONTEND_PORT:-}" ]]; then
      FRONTEND_LOCKED=true
    fi
    if ! probe_port "127.0.0.1" "${FRONTEND_PORT}"; then
      if ${FRONTEND_LOCKED}; then
        echo "❌ 前端端口 ${FRONTEND_PORT} 已被占用，且 AIASYS_FRONTEND_PORT 已锁定" >&2
        exit 1
      fi
      NEW_FRONTEND_PORT=$(find_available_port "127.0.0.1" "$((FRONTEND_PORT + 1))")
      if [[ -z "${NEW_FRONTEND_PORT}" ]]; then
        echo "❌ 无法为前端找到可用端口（起始: ${FRONTEND_PORT}）" >&2
        exit 1
      fi
      echo "⚠ 前端端口 ${FRONTEND_PORT} 被占用，自动切换到 ${NEW_FRONTEND_PORT}"
      FRONTEND_PORT="${NEW_FRONTEND_PORT}"
      FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}"
    fi

    start_backend
    start_frontend
    # Wait for any background job to finish (bash 3.2 compatible alternative to wait -n)
    while true; do
      for pid in $(jobs -p); do
        if ! kill -0 "$pid" 2>/dev/null; then
          break 2
        fi
      done
      sleep 0.5
    done
    ;;
  status)
    status_command
    ;;
  design-lint)
    exec "${PROJECT_ROOT}/scripts/design/validate-design-md.sh" "$@"
    ;;
  design-export-css)
    exec node "${PROJECT_ROOT}/scripts/design/export-tailwind4-css.mjs" "$@"
    ;;
  design-export-runtime)
    exec node "${PROJECT_ROOT}/scripts/design/export-runtime-theme-candidate.mjs" "$@"
    ;;
  setup-hooks)
    exec "${PROJECT_ROOT}/scripts/dev/setup-hooks.sh"
    ;;
  help|-h|--help)
    print_usage
    ;;
  *)
    echo "Unknown command: ${command_name}" >&2
    print_usage >&2
    exit 1
    ;;
esac

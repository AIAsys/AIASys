#!/bin/bash

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
    start_backend
    start_frontend
    wait -n "${BACKEND_PID}" "${FRONTEND_PID}"
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

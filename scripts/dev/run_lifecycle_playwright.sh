#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WEB_ROOT="${PROJECT_ROOT}/apps/web"
DEV_LOG_FILE="$(mktemp -t aiasys-playwright-dev-XXXX.log)"
STARTED_DEV_STACK=0
DEV_STACK_PID=""

cleanup() {
  local exit_code=$?

  if [[ "${STARTED_DEV_STACK}" -eq 1 && -n "${DEV_STACK_PID}" ]]; then
    kill "${DEV_STACK_PID}" >/dev/null 2>&1 || true
    wait "${DEV_STACK_PID}" >/dev/null 2>&1 || true
  fi

  rm -f "${DEV_LOG_FILE}"
  exit "${exit_code}"
}

wait_for_stack_ready() {
  local deadline=$((SECONDS + 240))

  until "${PROJECT_ROOT}/dev.sh" status >/dev/null 2>&1; do
    if [[ -n "${DEV_STACK_PID}" ]] && ! kill -0 "${DEV_STACK_PID}" >/dev/null 2>&1; then
      echo "开发服务提前退出，日志如下：" >&2
      cat "${DEV_LOG_FILE}" >&2
      return 1
    fi

    if (( SECONDS >= deadline )); then
      echo "等待开发服务就绪超时，日志如下：" >&2
      cat "${DEV_LOG_FILE}" >&2
      return 1
    fi

    sleep 1
  done
}

trap cleanup EXIT INT TERM

if ! "${PROJECT_ROOT}/dev.sh" status >/dev/null 2>&1; then
  STARTED_DEV_STACK=1
  (
    cd "${PROJECT_ROOT}"
    exec ./dev.sh
  ) >"${DEV_LOG_FILE}" 2>&1 &
  DEV_STACK_PID=$!
  wait_for_stack_ready
fi

cd "${WEB_ROOT}"
npx playwright test -c playwright.lifecycle.config.ts "$@"

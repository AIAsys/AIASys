#!/bin/bash

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

load_deploy_env
check_local_requirements

ACTION="${1:-status}"
shift || true

SERVICE="all"
LINES="${PM2_LOG_LINES:-100}"
FOLLOW=0

while [ $# -gt 0 ]; do
  case "$1" in
    --service)
      SERVICE="${2:-all}"
      shift 2
      ;;
    --lines)
      LINES="${2:-100}"
      shift 2
      ;;
    --follow)
      FOLLOW=1
      shift
      ;;
    *)
      log_error "未知参数: $1"
      echo "用法: ./remote_pm2.sh [status|logs|restart|stop|start] [--service <name|all>] [--lines N] [--follow]"
      exit 1
      ;;
  esac
done

case "${ACTION}" in
  status)
    run_remote_command "pm2 status"
    ;;
  logs)
    if [ "${FOLLOW}" = "1" ]; then
      run_remote_command "pm2 logs ${SERVICE} --lines ${LINES}"
    else
      run_remote_command "pm2 logs ${SERVICE} --lines ${LINES} --nostream"
    fi
    ;;
  restart)
    if [ "${SERVICE}" = "all" ]; then
      run_remote_command "pm2 restart all"
    else
      run_remote_command "pm2 restart ${SERVICE}"
    fi
    ;;
  stop)
    if [ "${SERVICE}" = "all" ]; then
      run_remote_command "pm2 stop all"
    else
      run_remote_command "pm2 stop ${SERVICE}"
    fi
    ;;
  start)
    run_remote_command "pm2 startOrReload ecosystem.config.cjs"
    ;;
  *)
    log_error "未知动作: ${ACTION}"
    echo "支持动作: status, logs, restart, stop, start"
    exit 1
    ;;
esac

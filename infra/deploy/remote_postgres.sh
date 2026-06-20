#!/usr/bin/env bash

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

load_deploy_env
check_local_requirements

ACTION="${1:-status}"
shift || true

TARGET="all"

while [ $# -gt 0 ]; do
  case "$1" in
    --target)
      TARGET="${2:-all}"
      shift 2
      ;;
    *)
      log_error "未知参数: $1"
      echo "用法: ./remote_postgres.sh [status|start|stop|restart|logs] [--target app|sandbox|all]"
      exit 1
      ;;
  esac
done

REMOTE_SCRIPT=$(cat <<EOF
set -euo pipefail
export PATH="\$HOME/.local/bin:\$PATH"
cd "${REMOTE_DIR}"

target="${TARGET}"
action="${ACTION}"

handle_app() {
  bash infra/docker/postgres/manage.sh "\${action}"
}

handle_sandbox() {
  case "\${action}" in
    status)
      docker ps -a --filter "name=aiasys-sandbox-db"
      ;;
    start)
      if docker ps --format '{{.Names}}' | grep -q '^aiasys-sandbox-db$'; then
        echo "sandbox postgres already running"
      elif docker ps -a --format '{{.Names}}' | grep -q '^aiasys-sandbox-db$'; then
        docker start aiasys-sandbox-db
      else
        docker run -d \
          --name aiasys-sandbox-db \
          --restart unless-stopped \
          -e POSTGRES_USER=postgres \
          -e POSTGRES_PASSWORD=postgres \
          -e POSTGRES_DB=postgres \
          -p "$(remote_sandbox_db_port):5432" \
          postgres:16-alpine >/dev/null
      fi
      docker ps --filter "name=aiasys-sandbox-db"
      ;;
    stop)
      docker stop aiasys-sandbox-db >/dev/null 2>&1 || true
      echo "sandbox postgres stopped"
      ;;
    restart)
      docker restart aiasys-sandbox-db >/dev/null
      docker ps --filter "name=aiasys-sandbox-db"
      ;;
    logs)
      docker logs --tail 100 aiasys-sandbox-db
      ;;
    *)
      echo "unsupported sandbox action: \${action}" >&2
      exit 1
      ;;
  esac
}

case "\${target}" in
  app)
    handle_app
    ;;
  sandbox)
    handle_sandbox
    ;;
  all)
    echo "=== app postgres ==="
    handle_app
    echo
    echo "=== sandbox postgres ==="
    handle_sandbox
    ;;
  *)
    echo "unsupported target: \${target}" >&2
    exit 1
    ;;
esac
EOF
)

run_remote_script "${REMOTE_SCRIPT}"

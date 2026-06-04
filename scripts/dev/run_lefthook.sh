#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

resolve_lefthook_bin() {
  if [[ -n "${LEFTHOOK_BIN:-}" && -x "${LEFTHOOK_BIN}" ]]; then
    printf '%s\n' "${LEFTHOOK_BIN}"
    return 0
  fi

  if [[ -x "${REPO_ROOT}/apps/web/node_modules/.bin/lefthook" ]]; then
    printf '%s\n' "${REPO_ROOT}/apps/web/node_modules/.bin/lefthook"
    return 0
  fi

  local os_arch
  local cpu_arch
  os_arch="$(uname | tr '[:upper:]' '[:lower:]')"
  cpu_arch="$(uname -m | sed 's/aarch64/arm64/;s/x86_64/x64/')"

  if [[ -x "${REPO_ROOT}/apps/web/node_modules/lefthook-${os_arch}-${cpu_arch}/bin/lefthook" ]]; then
    printf '%s\n' "${REPO_ROOT}/apps/web/node_modules/lefthook-${os_arch}-${cpu_arch}/bin/lefthook"
    return 0
  fi

  if command -v lefthook >/dev/null 2>&1; then
    command -v lefthook
    return 0
  fi

  return 1
}

LEFTHOOK_BIN_PATH="$(resolve_lefthook_bin || true)"
if [[ -z "${LEFTHOOK_BIN_PATH}" ]]; then
  echo "[lefthook] 找不到可执行文件。请先在 apps/web 执行 npm ci，再运行 ./dev.sh setup-hooks。" >&2
  exit 1
fi

exec "${LEFTHOOK_BIN_PATH}" "$@"

#!/usr/bin/env bash

set -euo pipefail

aiasys_repo_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd
}

aiasys_load_staged_files() {
  local repo_root="$1"
  local -n output_ref="$2"

  mapfile -d '' output_ref < <(
    cd "${repo_root}" &&
      git diff --cached --name-only --diff-filter=ACMRD -z
  )
}

aiasys_is_sensitive_path() {
  local path="$1"

  case "${path}" in
    .env|.env.*|*.pem|*.key|*.p12|*.pfx|*.crt|*.cer|*.der|*.asc)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

aiasys_find_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi

  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi

  return 1
}

aiasys_file_size() {
  local path="$1"

  if stat -c %s "${path}" >/dev/null 2>&1; then
    stat -c %s "${path}"
    return 0
  fi

  wc -c <"${path}"
}

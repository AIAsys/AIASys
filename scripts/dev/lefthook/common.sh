#!/usr/bin/env bash

set -euo pipefail

aiasys_repo_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd
}

aiasys_load_staged_files() {
  local repo_root="$1"
  local array_name="$2"
  local _files=()

  while IFS= read -r -d '' line; do
    _files+=("$line")
  done < <(cd "${repo_root}" && git diff --cached --name-only --diff-filter=ACMRD -z)

  eval "${array_name}=(\"\${_files[@]}\")"
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

  if [[ "$(uname)" == "Darwin" ]]; then
    stat -f%z "${path}" 2>/dev/null || wc -c <"${path}"
  else
    stat -c %s "${path}" 2>/dev/null || wc -c <"${path}"
  fi
}

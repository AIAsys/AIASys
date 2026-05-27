#!/usr/bin/env bash

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

REPO_ROOT="$(aiasys_repo_root)"
cd "${REPO_ROOT}"

declare -a STAGED_FILES=()
aiasys_load_staged_files "${REPO_ROOT}" STAGED_FILES

if [[ "${#STAGED_FILES[@]}" -eq 0 ]]; then
  exit 0
fi

declare -a BLOCKED_FILES=()
declare -a EXISTING_FILES=()
declare -a PYTHON_FILES=()
declare -a LARGE_FILES=()

for path in "${STAGED_FILES[@]}"; do
  if aiasys_is_sensitive_path "${path}"; then
    BLOCKED_FILES+=("${path}")
  fi

  if [[ -e "${path}" ]]; then
    EXISTING_FILES+=("${path}")
  fi

  if [[ -f "${path}" && "${path}" == *.py ]]; then
    PYTHON_FILES+=("${path}")
  fi
done

if [[ "${#BLOCKED_FILES[@]}" -gt 0 ]]; then
  echo "[lefthook] 检测到敏感文件，已阻止提交：" >&2
  printf '  - %s\n' "${BLOCKED_FILES[@]}" >&2
  exit 1
fi

ADDED_LINES="$(git diff --cached --no-color --unified=0 -- . | awk '/^\+[^+]/ { sub(/^\+/, ""); print }')"
SECRET_PATTERN='sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----'
SECRET_HITS="$(printf '%s\n' "${ADDED_LINES}" | grep -nE "${SECRET_PATTERN}" || true)"

if [[ -n "${SECRET_HITS}" ]]; then
  echo "[lefthook] 检测到疑似密钥内容，已阻止提交：" >&2
  printf '%s\n' "${SECRET_HITS}" >&2
  exit 1
fi

for path in "${EXISTING_FILES[@]}"; do
  if [[ ! -f "${path}" ]]; then
    continue
  fi

  if [[ "$(aiasys_file_size "${path}")" -gt 5242880 ]]; then
    LARGE_FILES+=("${path}")
  fi
done

if [[ "${#PYTHON_FILES[@]}" -gt 0 ]]; then
  PYTHON_BIN="$(aiasys_find_python || true)"
  if [[ -n "${PYTHON_BIN}" ]]; then
    "${PYTHON_BIN}" -m py_compile "${PYTHON_FILES[@]}"
  fi
fi

if [[ "${#LARGE_FILES[@]}" -gt 0 ]]; then
  echo "[lefthook] 提示：本次提交包含大文件（超过 5MB）：" >&2
  printf '  - %s\n' "${LARGE_FILES[@]}" >&2
fi

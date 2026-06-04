#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "${REPO_ROOT}"

git config --local core.hooksPath .git/hooks
"${REPO_ROOT}/scripts/dev/run_lefthook.sh" install pre-commit -f >/dev/null

for hook_name in pre-push prepare-commit-msg commit-msg; do
  hook_path="${REPO_ROOT}/.git/hooks/${hook_name}"
  if [[ -f "${hook_path}" ]] && grep -q "lefthook" "${hook_path}"; then
    rm -f "${hook_path}"
  fi
done

echo "已为当前仓库安装 pre-commit hook"
echo "当前仓库 hooksPath 已固定为 .git/hooks"
echo "旧的 lefthook pre-push / prepare-commit-msg / commit-msg 噪音脚本也已清理"

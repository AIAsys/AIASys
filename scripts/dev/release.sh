#!/bin/bash
# scripts/dev/release.sh -- AIASys 发布辅助脚本
#
# 用法：
#   ./scripts/dev/release.sh 0.4.17          # 正式发布
#   ./scripts/dev/release.sh --dry-run 0.4.17 # 演练，不实际提交/tag
#
# 规范：
#   - 必须在 main 分支上执行
#   - 工作区必须干净
#   - 必须已存在 docs/changelog/v{version}_{YYYY-MM-DD}.md
#   - 版本号会同步到 web/desktop/pyproject.toml
#   - 自动提交、打 tag v{version} 并推送到 upstream

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DRY_RUN=false

usage() {
  cat <<EOF
Usage:
  ./scripts/dev/release.sh [--dry-run] <version>

Examples:
  ./scripts/dev/release.sh 0.4.17
  ./scripts/dev/release.sh --dry-run 0.4.17
EOF
  exit 1
}

# 解析参数
if [[ "$#" -eq 0 ]]; then
  usage
fi

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      VERSION="$1"
      shift
      ;;
  esac
done

if [[ -z "${VERSION:-}" ]]; then
  echo "错误：未指定版本号" >&2
  usage
fi

# 版本号格式校验：X.Y.Z 或 X.Y.Z-beta.N
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]]; then
  echo "错误：版本号格式不正确，期望 X.Y.Z 或 X.Y.Z-beta.N，得到 '$VERSION'" >&2
  exit 1
fi

TAG="v${VERSION}"
TODAY="$(date +%Y-%m-%d)"
CHANGELOG_FILE="docs/changelog/${TAG}_${TODAY}.md"

cd "$PROJECT_ROOT"

# 1. 分支检查
current_branch="$(git branch --show-current)"
if [[ "$current_branch" != "main" ]]; then
  echo "错误：必须在 main 分支上执行发布，当前分支为 '$current_branch'" >&2
  exit 1
fi

# 2. 工作区检查
if [[ -n "$(git status --short)" ]]; then
  echo "错误：工作区不干净，请先提交或 stash 改动" >&2
  git status --short
  exit 1
fi

# 3. 远程同步检查（可选但建议）
echo "==> 拉取 upstream/main 最新状态..."
git fetch upstream main >/dev/null 2>&1 || {
  echo "错误：无法 fetch upstream/main，请确认 remote 配置" >&2
  exit 1
}

local_main="$(git rev-parse main)"
upstream_main="$(git rev-parse upstream/main)"
if [[ "$local_main" != "$upstream_main" ]]; then
  echo "错误：本地 main ($local_main) 与 upstream/main ($upstream_main) 不一致" >&2
  echo "请先执行：git pull upstream main" >&2
  exit 1
fi

# 4. changelog 检查
if [[ ! -f "$CHANGELOG_FILE" ]]; then
  echo "错误：未找到 changelog 文件 '$CHANGELOG_FILE'" >&2
  echo "请先按 docs/changelog/README.md 规范编写 changelog，再执行发布。" >&2
  exit 1
fi
echo "==> 找到 changelog: $CHANGELOG_FILE"

# 5. 版本号同步
echo "==> 同步版本号到 $VERSION ..."

update_json_version() {
  local file="$1"
  local version="$2"
  node -e "
    const fs = require('fs');
    const p = JSON.parse(fs.readFileSync('$file', 'utf8'));
    p.version = '$version';
    fs.writeFileSync('$file', JSON.stringify(p, null, 2) + '\n');
  "
}

update_toml_version() {
  local file="$1"
  local version="$2"
  python3 -c "
import re
with open('$file', 'r') as f:
    content = f.read()
content = re.sub(r'^version = \".*?\"', 'version = \"$version\"', content, count=1, flags=re.MULTILINE)
with open('$file', 'w') as f:
    f.write(content)
"
}

update_json_version "apps/web/package.json" "$VERSION"
update_json_version "apps/desktop/package.json" "$VERSION"
update_toml_version "apps/backend/pyproject.toml" "$VERSION"

# 6. 检查版本号是否真的改了
if [[ -n "$(git status --short)" ]]; then
  echo "==> 版本号变更如下："
  git diff -- apps/web/package.json apps/desktop/package.json apps/backend/pyproject.toml
else
  echo "==> 版本号已是 $VERSION，无需变更"
fi

# 7. 演练模式：不实际提交和 tag
if [[ "$DRY_RUN" == true ]]; then
  echo ""
  echo "==> [DRY RUN] 演练完成，不会执行提交、打 tag 和推送"
  echo "    版本号已临时修改，请手动 reset 或继续真实发布"
  echo ""
  echo "    如需继续真实发布，请重新执行（去掉 --dry-run）："
  echo "      ./scripts/dev/release.sh $VERSION"
  exit 0
fi

# 8. 提交版本号变更
read -r -p "确认提交版本号变更并打 tag $TAG 推送到 upstream? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
  echo "已取消"
  exit 1
fi

git add apps/web/package.json apps/desktop/package.json apps/backend/pyproject.toml
git commit -m "chore(release): bump version to $VERSION"

# 9. 打 tag 并推送
git tag "$TAG"
git push upstream main
# git push upstream "$TAG"  # 由 CI 监听 v* tag 触发桌面构建
echo "==> 已推送 main 分支"
echo "==> 请手动推送 tag 触发 CI：git push upstream $TAG"
echo ""
echo "发布流程："
echo "  1. git push upstream $TAG"
echo "  2. 等待 .github/workflows/ci-desktop.yml 完成"
echo "  3. 检查 release 产物：gh release view $TAG --json assets"

#!/usr/bin/env bash
#
# Pre-commit hook：扫描暂存区中的潜在敏感信息。
# 用法：由 .pre-commit-config.yaml 自动调用

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# 颜色
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 要拦截的模式（只匹配新增/修改的行）
PATTERNS=(
    'sk-[a-f0-9]{32}'                    # Kimi / DashScope / DeepSeek 32位
    'sk-kimi-[a-zA-Z0-9]{20,}'           # Kimi 长格式
    'sk-[a-zA-Z0-9]{48}'                 # OpenAI 48位
    'sk-ant-[a-zA-Z0-9]{20,}'            # Anthropic
    'SG\.[a-zA-Z0-9]{22}\.[a-zA-Z0-9]{43}' # SendGrid
    'ghp_[a-zA-Z0-9]{36}'                # GitHub Classic
    'github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}' # GitHub Fine-grained
    'AKIA[0-9A-Z]{16}'                   # AWS Access Key
)

# 误报排除（示例、占位符、文档说明）
EXCLUDE_REGEX='(your-|YOUR_|example|EXAMPLE|placeholder|PLACEHOLDER|REDACTED|redacted|xxxxxxxx|XXXXXXXX|abc123|abcdefghijklmnopqrstuvwxyz|test-secret|test_key|demo-|DEMO-|sample|SAMPLE|fake-|FAKE-|mock-|MOCK-|preview-token|local-jwt-token|none-mode-token|App Secret|Verify Token|Client Secret|Bot Token|App Token|Access Token|Password|Auth Token|\$GITHUB_TOKEN|\$KIMI_API_KEY|sha256=|api_key\.py|api-key)'

HITS=0

for pattern in "${PATTERNS[@]}"; do
    # 只扫描暂存区中的文本文件（新增或修改的内容）
    matches=$(git diff --cached --no-color | grep -E "^[+]" | grep -vE "^\+\+\+" | grep -E "$pattern" | grep -vE "$EXCLUDE_REGEX" || true)

    if [ -n "$matches" ]; then
        HITS=$((HITS + 1))
        echo "${RED}[BLOCKED]${NC} 暂存区检测到可疑模式: $pattern"
        echo "$matches" | head -5 | while IFS= read -r line; do
            echo "  $line"
        done
        echo ""
    fi
done

if [ "$HITS" -gt 0 ]; then
    echo "${RED}发现 $HITS 条潜在敏感信息。${NC}"
    echo "如果确认是误报，可用 git commit --no-verify 跳过本次检查。"
    echo "但请不要将真实 API key、密码、token 提交到仓库。"
    exit 1
fi

exit 0

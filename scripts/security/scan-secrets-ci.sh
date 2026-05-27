#!/usr/bin/env bash
#
# CI 环境轻量扫描：只检查本次 push/PR 引入的变更

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 扫描模式
PATTERNS=(
    'sk-[a-f0-9]{32}'
    'sk-kimi-[a-zA-Z0-9]{20,}'
    'sk-[a-zA-Z0-9]{48}'
    'sk-ant-[a-zA-Z0-9]{20,}'
    'SG\.[a-zA-Z0-9]{22}\.[a-zA-Z0-9]{43}'
    'ghp_[a-zA-Z0-9]{36}'
    'github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}'
    'AKIA[0-9A-Z]{16}'
)

EXCLUDE_REGEX='(your-|YOUR_|example|EXAMPLE|placeholder|PLACEHOLDER|REDACTED|redacted|xxxxxxxx|XXXXXXXX|abc123|abcdefghijklmnopqrstuvwxyz|test-secret|test_key|demo-|DEMO-|sample|SAMPLE|fake-|FAKE-|mock-|MOCK-|preview-token|local-jwt-token|none-mode-token|App Secret|Verify Token|Client Secret|Bot Token|App Token|Access Token|Password|Auth Token|\$GITHUB_TOKEN|\$KIMI_API_KEY|sha256=|api_key\.py|api-key|正则表达式|前缀特征|示例|应该被检测|不应该被误报|格式1:)'

# 确定扫描范围：PR 时扫描 base..head，push 时扫描最近 20 个提交
if [ -n "${GITHUB_BASE_REF:-}" ]; then
    RANGE="origin/${GITHUB_BASE_REF}...HEAD"
else
    RANGE="HEAD~20..HEAD"
fi

echo "扫描范围: $RANGE"

HITS=0
for pattern in "${PATTERNS[@]}"; do
    matches=$(git log --format="" --patch "$RANGE" | grep -E "^[+]" | grep -vE "^\+\+\+" | grep -E "$pattern" | grep -vE "$EXCLUDE_REGEX" || true)
    if [ -n "$matches" ]; then
        HITS=$((HITS + 1))
        echo "${RED}[ALERT]${NC} 检测到可疑模式: $pattern"
        echo "$matches" | head -5
        echo ""
    fi
done

if [ "$HITS" -gt 0 ]; then
    echo "${RED}发现 $HITS 条潜在敏感信息，请人工复核。${NC}"
    exit 1
fi

echo "${YELLOW}本次变更未检测到明显的敏感信息泄露。${NC}"
exit 0

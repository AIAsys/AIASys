#!/usr/bin/env bash
#
# 扫描 git 历史中的潜在敏感信息泄露。
# 用法: cd /home/ke/projects/AIASys && bash scripts/security/scan-secrets.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# 颜色
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

# 已知的误报模式（示例、占位符、文档说明）
EXCLUDE_PATTERNS=(
    # 文档/注释中的占位符
    'your-'
    'YOUR_'
    'example'
    'EXAMPLE'
    'placeholder'
    'PLACEHOLDER'
    'REDACTED'
    'redacted'
    'xxxxxxxx'
    'XXXXXXXX'
    'abc123'
    'abcdefghijklmnopqrstuvwxyz'
    'test-secret'
    'test_key'
    'demo-'
    'DEMO_'
    'sample'
    'SAMPLE'
    'fake-'
    'FAKE_'
    'mock-'
    'MOCK_'
    'none-mode-token'
    'local-jwt-token'
    'preview-token'
    'App Secret'
    'Verify Token'
    'Client Secret'
    'Bot Token'
    'App Token'
    'Access Token'
    'Password'
    'Auth Token'
    # 环境变量引用
    '\$GITHUB_TOKEN'
    '\$KIMI_API_KEY'
    # 脚本中的变量名
    'api_key_encrypted'
    # 格式说明
    '正则表达式'
    '前缀特征'
    '示例'
    '应该被检测'
    '不应该被误报'
    # SHA256 哈希（非 key）
    'sha256='
    # 文件路径中的 key 字样
    'api_key.py'
    'api-key'
)

# 构建 grep 排除参数
EXCLUDE_ARGS=()
for pat in "${EXCLUDE_PATTERNS[@]}"; do
    EXCLUDE_ARGS+=("--exclude")
    EXCLUDE_ARGS+=("$pat")
done

echo "========================================"
echo "Git 历史敏感信息扫描"
echo "仓库: $REPO_ROOT"
echo "========================================"
echo ""

# 要扫描的正则模式
PATTERNS=(
    # Kimi (32位十六进制)
    'sk-[a-f0-9]{32}'
    # Kimi (长格式)
    'sk-kimi-[a-zA-Z0-9]{20,}'
    # OpenAI (48位)
    'sk-[a-zA-Z0-9]{48}'
    # Anthropic
    'sk-ant-[a-zA-Z0-9]{20,}'
    # DashScope / DeepSeek (32位)
    'sk-[a-f0-9]{32}'
    # SendGrid
    'SG\.[a-zA-Z0-9]{22}\.[a-zA-Z0-9]{43}'
    # GitHub Token (经典)
    'ghp_[a-zA-Z0-9]{36}'
    # GitHub Token (细粒度)
    'github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}'
    # AWS Access Key
    'AKIA[0-9A-Z]{16}'
    # 通用 UUID-like API key (32位十六进制，带 key/secret/token 上下文)
    '(api[_-]?key|secret|token|password)\s*[:=]\s*["'\''"'\''`][a-f0-9]{32}["'\''"'\''`"]'
)

TOTAL_HITS=0
SUSPICIOUS_HITS=0

for pattern in "${PATTERNS[@]}"; do
    echo "--- 扫描模式: $pattern ---"

    # 从 git 历史中扫描（所有提交的 patch）
    # 使用 git log -p 输出所有提交的 diff，然后 grep 匹配
    # 限制输出前 50 条，避免太多
    hits=$(git log --all -p 2>/dev/null | grep -nE "^[+-].*$pattern" | head -50 || true)

    if [ -z "$hits" ]; then
        echo "  ${GREEN}未命中${NC}"
        continue
    fi

    line_count=$(echo "$hits" | wc -l)
    TOTAL_HITS=$((TOTAL_HITS + line_count))

    # 过滤误报
    filtered="$hits"
    for pat in "${EXCLUDE_PATTERNS[@]}"; do
        filtered=$(echo "$filtered" | grep -vF "$pat" || true)
    done

    if [ -z "$filtered" ]; then
        echo "  ${GREEN}命中 $line_count 条，全部确认为误报/示例${NC}"
        continue
    fi

    filtered_count=$(echo "$filtered" | wc -l)
    SUSPICIOUS_HITS=$((SUSPICIOUS_HITS + filtered_count))

    echo "  ${YELLOW}命中 $line_count 条，其中 $filtered_count 条需要人工复核${NC}"
    echo "$filtered" | while IFS= read -r line; do
        # 截断过长的行
        if [ "${#line}" -gt 200 ]; then
            line="${line:0:200}..."
        fi
        echo "    $line"
    done
    echo ""
done

echo ""
echo "========================================"
echo "扫描完成"
echo "总命中数: $TOTAL_HITS"
echo "需复核数: $SUSPICIOUS_HITS"

if [ "$SUSPICIOUS_HITS" -gt 0 ]; then
    echo ""
    echo "${RED}发现 $SUSPICIOUS_HITS 条可疑记录，请逐一人工复核。${NC}"
    echo "如果确认是真实 key，请："
    echo "  1. 立即到对应平台撤销（rotate）该 key"
    echo "  2. 用 git-filter-repo 或 BFG 清理 git 历史"
    echo "  3. 通知所有团队成员重新 clone 仓库"
    exit 1
else
    echo "${GREEN}未发现需要复核的可疑记录。${NC}"
    echo ""
    echo "建议后续配置："
    echo "  1. 安装 git-secrets: apt install git-secrets"
    echo "  2. 配置 pre-commit hook 阻止含 key 的提交"
    exit 0
fi

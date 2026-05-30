#!/bin/bash
# 完成任务会话
# Usage: ./complete-session.sh <filepath> [--archive]
#
# 示例:
#   ./complete-session.sh .agents/task-sessions/active/2026-02-27-feature-mcp.md
#   ./complete-session.sh .agents/task-sessions/active/2026-02-27-feature-mcp.md --archive

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_SESSIONS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(cd "$TASK_SESSIONS_DIR/../.." && pwd)"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 参数检查
if [ $# -lt 1 ]; then
    echo -e "${RED}错误: 请提供文件路径${NC}"
    echo "用法: $0 <filepath> [--archive]"
    echo ""
    echo "示例:"
    echo "  $0 .agents/task-sessions/active/2026-02-27-feature-mcp.md"
    exit 1
fi

FILEPATH="$1"
ARCHIVE=false
if [ "$2" = "--archive" ]; then
    ARCHIVE=true
fi

# 检查文件是否存在
if [ ! -f "$FILEPATH" ]; then
    echo -e "${RED}错误: 文件不存在${NC}"
    echo "  $FILEPATH"
    exit 1
fi

# 获取文件名和目录
FILENAME=$(basename "$FILEPATH")
DIR=$(dirname "$FILEPATH")

# 确定目标目录
if [ "$ARCHIVE" = true ]; then
    TARGET_DIR="$TASK_SESSIONS_DIR/archive"
    TARGET_DESC="归档"
else
    TARGET_DIR="$TASK_SESSIONS_DIR/completed"
    TARGET_DESC="已完成"
fi

# 检查当前位置
if [[ "$DIR" == *"/completed"* ]] || [[ "$DIR" == *"/archive"* ]]; then
    echo -e "${YELLOW}警告: 文件已在 completed/ 或 archive/ 目录中${NC}"
    echo "  $FILEPATH"
    exit 0
fi

# 检查 Summary 部分是否已填写
echo -e "${BLUE}检查任务完成状态...${NC}"

if ! grep -q "7.1 完成情况" "$FILEPATH"; then
    echo -e "${YELLOW}警告: 未找到 Summary 部分${NC}"
    read -p "是否继续? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}已取消${NC}"
        exit 0
    fi
fi

# 询问是否已同步文档
echo ""
echo -e "${BLUE}文档同步检查:${NC}"
echo "完成任务会话前，请确保已同步以下文档:"
echo "  ☐ 当前 task session 已补齐 Goal / Scope / AC / 风险 / 验证证据"
echo "  ☐ 如形成长期规则，已按需回写到对应 skill"
echo "  ☐ 如用户明确要求，人类文档已同步到新的 docs/ 结构"
echo ""
read -p "是否已完成文档同步? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}请先完成文档同步，然后再运行此脚本${NC}"
    exit 0
fi

# 更新时间戳
current_time=$(date '+%Y-%m-%d %H:%M')
if command -v sed &>/dev/null; then
    # 更新最后更新时间
    sed -i "s/| \*\*最后更新\*\* | .* |/| **最后更新** | ${current_time} |/" "$FILEPATH" 2>/dev/null || true
    # 更新状态
    sed -i 's/| \*\*状态\*\* | 🔄 active |/| **状态** | ✅ completed |/' "$FILEPATH" 2>/dev/null || true
fi

# 移动文件
echo -e "${BLUE}移动文件到 ${TARGET_DESC}目录...${NC}"
mkdir -p "$TARGET_DIR"
mv "$FILEPATH" "$TARGET_DIR/"

echo -e "${GREEN}✅ 任务会话已标记为 ${TARGET_DESC}!${NC}"
echo ""
echo -e "${BLUE}文件信息:${NC}"
echo "  原路径: .agents/task-sessions/active/${FILENAME}"
echo "  新路径: .agents/task-sessions/$(basename "$TARGET_DIR")/${FILENAME}"
echo ""
echo -e "${BLUE}后续操作:${NC}"
echo "  1. 提交代码变更"
echo "  2. 创建 PR（如适用）"
echo ""

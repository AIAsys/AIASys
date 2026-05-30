#!/bin/bash
# 列出所有任务会话
# Usage: ./list-sessions.sh [status]
#   status: active | completed | all (默认: all)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_SESSIONS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(cd "$TASK_SESSIONS_DIR/../.." && pwd)"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
GRAY='\033[0;90m'
NC='\033[0m'

STATUS="${1:-all}"

# 统计函数
count_sessions() {
    local dir="$1"
    if [ -d "$dir" ]; then
        ls -1 "$dir"/*.md 2>/dev/null | wc -l
    else
        echo 0
    fi
}

# 列出会话函数
list_sessions() {
    local dir="$1"
    local label="$2"
    local color="$3"
    
    echo -e "${color}== ${label} ==${NC}"
    
    if [ ! -d "$dir" ]; then
        echo -e "${GRAY}  目录不存在${NC}"
        echo ""
        return
    fi
    
    local count=0
    for file in "$dir"/*.md; do
        if [ -f "$file" ]; then
            count=$((count + 1))
            filename=$(basename "$file")
            
            # 提取元数据
            local task_type=$(grep -E '^\| \*\*任务类型\*\*' "$file" 2>/dev/null | sed 's/.*| \([^|]*\) |$/\1/' | tr -d '[:space:]' || echo "unknown")
            local task_status=$(grep -E '^\| \*\*状态\*\*' "$file" 2>/dev/null | sed 's/.*| \([^|]*\) |$/\1/' | tr -d '[:space:]' || echo "unknown")
            local version=$(grep -E '^\| \*\*关联版本\*\*' "$file" 2>/dev/null | sed 's/.*| \([^|]*\) |$/\1/' | tr -d '[:space:]' || echo "unknown")
            
            # 提取标题（Task Session: 后面的内容）
            local title=$(grep -E '^# Task Session:' "$file" 2>/dev/null | sed 's/# Task Session: //' | cut -c1-40 || echo "$filename")
            
            # 格式化输出
            printf "  ${GRAY}%-10s${NC} %-8s %-10s %s\n" "$version" "$task_type" "$task_status" "$title"
        fi
    done
    
    if [ $count -eq 0 ]; then
        echo -e "${GRAY}  无${label}${NC}"
    fi
    echo ""
}

# 主逻辑
echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}    Task Sessions 列表${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

if [ "$STATUS" = "all" ] || [ "$STATUS" = "active" ]; then
    list_sessions "$TASK_SESSIONS_DIR/active" "🔄 进行中" "$YELLOW"
fi

if [ "$STATUS" = "all" ] || [ "$STATUS" = "completed" ]; then
    list_sessions "$TASK_SESSIONS_DIR/completed" "✅ 已完成" "$GREEN"
fi

# 统计
echo -e "${BLUE}== 统计 ==${NC}"
active_count=$(count_sessions "$TASK_SESSIONS_DIR/active")
completed_count=$(count_sessions "$TASK_SESSIONS_DIR/completed")
total_count=$((active_count + completed_count))

echo -e "  进行中: ${YELLOW}${active_count}${NC}"
echo -e "  已完成: ${GREEN}${completed_count}${NC}"
echo -e "  总计: ${BLUE}${total_count}${NC}"
echo ""

# 使用提示
echo -e "${GRAY}提示:${NC}"
echo -e "  创建新会话: ${GRAY}bash .agents/task-sessions/scripts/init-session.sh feature '任务描述'${NC}"
echo -e "  只查看进行中: ${GRAY}$0 active${NC}"
echo ""

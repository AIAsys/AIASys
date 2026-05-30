#!/bin/bash
# 归档旧的任务会话
# Usage: ./archive-old-sessions.sh [days]
#   days: 多少天前的会话会被归档（默认: 30）

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

DAYS="${1:-30}"
ARCHIVE_DIR="$TASK_SESSIONS_DIR/archive"
COMPLETED_DIR="$TASK_SESSIONS_DIR/completed"

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}    归档旧任务会话${NC}"
echo -e "${BLUE}================================${NC}"
echo ""
echo -e "归档条件: ${DAYS} 天前的已完成会话"
echo ""

# 确保归档目录存在
mkdir -p "$ARCHIVE_DIR"

# 计算截止日期
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    CUTOFF_DATE=$(date -v-${DAYS}d +%Y-%m-%d 2>/dev/null || date -d "${DAYS} days ago" +%Y-%m-%d)
else
    # Linux
    CUTOFF_DATE=$(date -d "${DAYS} days ago" +%Y-%m-%d)
fi

echo -e "截止日期: ${GRAY}${CUTOFF_DATE}${NC}"
echo ""

# 查找并归档旧文件
archived_count=0

if [ -d "$COMPLETED_DIR" ]; then
    for file in "$COMPLETED_DIR"/*.md; do
        if [ -f "$file" ]; then
            filename=$(basename "$file")
            # 从文件名提取日期 (YYYY-MM-DD-type-...)
            file_date=$(echo "$filename" | grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2}' || echo "")
            
            if [ -n "$file_date" ]; then
                # 比较日期
                if [[ "$file_date" < "$CUTOFF_DATE" ]] || [ "$file_date" = "$CUTOFF_DATE" ]; then
                    echo -e "  ${GRAY}归档: ${filename}${NC}"
                    mv "$file" "$ARCHIVE_DIR/"
                    archived_count=$((archived_count + 1))
                fi
            fi
        fi
    done
fi

echo ""
if [ $archived_count -eq 0 ]; then
    echo -e "${YELLOW}没有需要归档的会话${NC}"
else
    echo -e "${GREEN}✅ 已归档 ${archived_count} 个会话${NC}"
fi
echo ""

# 显示当前统计
echo -e "${BLUE}当前统计:${NC}"
active_count=$(ls -1 "$TASK_SESSIONS_DIR/active"/*.md 2>/dev/null | wc -l || echo 0)
completed_count=$(ls -1 "$TASK_SESSIONS_DIR/completed"/*.md 2>/dev/null | wc -l || echo 0)
archive_count=$(ls -1 "$ARCHIVE_DIR"/*.md 2>/dev/null | wc -l || echo 0)

echo -e "  进行中: ${YELLOW}${active_count}${NC}"
echo -e "  已完成: ${GREEN}${completed_count}${NC}"
echo -e "  已归档: ${GRAY}${archive_count}${NC}"
echo ""

#!/bin/bash
# Task Session 初始化脚本
# Usage: ./init-session.sh <type> "任务描述" [version]
#
# 参数:
#   type: feature | bugfix | research | spike | refactor | docs
#   任务描述: 简要描述任务内容（支持中文）
#   version: 关联版本号（可选，默认使用 current）
#
# 示例:
#   ./init-session.sh feature "MCP 集成实现" current
#   ./init-session.sh bugfix "修复会话超时问题"
#   ./init-session.sh research "调研向量数据库方案"

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_SESSIONS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(cd "$TASK_SESSIONS_DIR/../.." && pwd)"

# 参数解析
if [ $# -lt 2 ]; then
    echo -e "${RED}错误: 参数不足${NC}"
    echo "用法: $0 <type> '任务描述' [version]"
    echo ""
    echo "类型 (type):"
    echo "  feature  - 新功能开发"
    echo "  bugfix   - Bug 修复"
    echo "  research - 研究探索"
    echo "  spike    - 技术预研"
    echo "  refactor - 重构优化"
    echo "  docs     - 文档任务"
    echo ""
    echo "示例:"
    echo "  $0 feature 'MCP 集成实现' v0.1.6"
    echo "  $0 bugfix '修复会话超时问题'"
    exit 1
fi

TYPE="$1"
DESCRIPTION="$2"
VERSION="${3:-}"

# 验证类型
VALID_TYPES=("feature" "bugfix" "research" "spike" "refactor" "docs")
if [[ ! " ${VALID_TYPES[@]} " =~ " ${TYPE} " ]]; then
    echo -e "${RED}错误: 无效的任务类型 '$TYPE'${NC}"
    echo "有效类型: ${VALID_TYPES[*]}"
    exit 1
fi

# 生成文件名
DATE=$(date +%Y-%m-%d)

# 先保留原描述中的可读字符，再按 ASCII slug 退化。
# 这样中文标题不会直接变成空文件名。
NORMALIZED_DESCRIPTION=$(printf '%s' "$DESCRIPTION" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[[:space:]]+/-/g; s#[/\\:*?"<>|]#-#g; s/-+/-/g; s/^-+//; s/-+$//')

ASCII_SLUG=$(printf '%s' "$NORMALIZED_DESCRIPTION" \
    | LC_ALL=C tr -cd '[:alnum:]-' \
    | sed -E 's/-+/-/g; s/^-+//; s/-+$//' \
    | cut -c1-50)

if [ -n "$ASCII_SLUG" ]; then
    DESCRIPTION_SLUG="$ASCII_SLUG"
elif [ -n "$NORMALIZED_DESCRIPTION" ]; then
    DESCRIPTION_SLUG=$(printf '%s' "$NORMALIZED_DESCRIPTION" | cut -c1-50)
else
    DESCRIPTION_SLUG="task-$(date +%H%M%S)"
fi

FILENAME="${DATE}-${TYPE}-${DESCRIPTION_SLUG}.md"
FILEPATH="${TASK_SESSIONS_DIR}/active/${FILENAME}"

# task-session 目录已改为本地工作产物，不再依赖仓库内的 .gitkeep。
mkdir -p "${TASK_SESSIONS_DIR}/active"

# 检查文件是否已存在
if [ -f "$FILEPATH" ]; then
    echo -e "${YELLOW}警告: 文件已存在${NC}"
    echo "  $FILEPATH"
    read -p "是否覆盖? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}已取消${NC}"
        exit 0
    fi
fi

# 处理关联版本（如果未提供，则标记为 current）
if [ -z "$VERSION" ]; then
    VERSION="current"
fi

# 获取当前时间
CURRENT_TIME=$(date '+%Y-%m-%d %H:%M')

# 生成描述的中文/英文映射
TYPE_DESC=""
case "$TYPE" in
    "feature") TYPE_DESC="功能开发" ;;
    "bugfix") TYPE_DESC="Bug 修复" ;;
    "research") TYPE_DESC="研究探索" ;;
    "spike") TYPE_DESC="技术预研" ;;
    "refactor") TYPE_DESC="重构优化" ;;
    "docs") TYPE_DESC="文档任务" ;;
esac

# 创建文件
echo -e "${BLUE}正在创建任务会话...${NC}"
cat > "$FILEPATH" << EOF
# Task Session: ${DESCRIPTION}

<!-- 
  说明: 这是 AI 任务执行的上下文持久化文件
  用途: 将 AI 的"工作记忆"从易失的上下文窗口转移到持久化的文件系统
-->

---

## Metadata

| 字段 | 内容 |
|------|------|
| **任务类型** | ${TYPE} (${TYPE_DESC}) |
| **关联版本** | ${VERSION} |
| **关联任务** | - [ ] ${DESCRIPTION}（对应专项 skill / 当前任务决策入口） |
| **创建时间** | ${CURRENT_TIME} |
| **最后更新** | ${CURRENT_TIME} |
| **预计耗时** | _h |
| **实际耗时** | _h |
| **状态** | 🔄 active |
| **执行者** | AI |

---

## 1. Goal（目标）

**一句话目标**: [清晰、可衡量的目标陈述]

**成功标准**:
- [ ] 标准 1: [可验证的结果]
- [ ] 标准 2: [可验证的结果]
- [ ] 标准 3: [可验证的结果]

---

## 2. Context（上下文）

### 2.1 问题背景
[描述为什么要做这项任务]

### 2.2 相关入口
| 入口 | 说明 | 链接 |
|------|------|------|
| 需求基线 | 当前目标、范围、验收口径 | \`当前 active task session\` + \`.agents/skills/aiasys-product-requirements/SKILL.md\` |
| 系统设计 | 信息架构、能力边界、分层规则 | \`.agents/skills/aiasys-system-design/SKILL.md\` |
| 状态流 | 生命周期、交互流、锁定时机 | \`.agents/skills/state-flow/SKILL.md\` |
| 执行流程 | 实施、验证、交付要求 | \`.agents/skills/sop-workflow/SKILL.md\`, \`.agents/skills/git-workflow/SKILL.md\` |
| 相关代码 | 已有实现 | \`apps/backend/...\`, \`apps/web/...\` |

### 2.3 约束条件
- [约束 1: 技术限制、时间限制等]
- [约束 2]

---

## 3. Plan（计划）

### Phase 1: 需求理解与准备
- **目标**: 理解需求，收集必要信息
- **状态**: 🔄 in_progress
- **预计时间**: _m

- [ ] 阅读相关入口（skill、当前 session、相关代码）
- [ ] 理解现有代码结构
- [ ] 识别潜在风险和依赖
- [ ] **检查点**: 能够回答"我要做什么"和"为什么这样做"

**执行记录**:
-

### Phase 2: 设计与方案
- **目标**: 确定技术方案
- **状态**: ⏳ pending
- **预计时间**: _m

- [ ] 评估可选方案
- [ ] 确定最终方案
- [ ] 记录决策理由
- [ ] **检查点**: 方案通过内部评审（如有需要）

**执行记录**:
-

### Phase 3: 实现
- **目标**: 完成代码实现
- **状态**: ⏳ pending
- **预计时间**: _m

- [ ] [具体实现步骤 1]
- [ ] [具体实现步骤 2]
- [ ] [具体实现步骤 3]
- [ ] **检查点**: 代码完成，自测通过

**执行记录**:
-

### Phase 4: 测试与验证
- **目标**: 验证功能正确性
- **状态**: ⏳ pending
- **预计时间**: _m

- [ ] 单元测试（如适用）
- [ ] 集成测试
- [ ] 手动验证
- [ ] **检查点**: 所有验收标准满足

**测试记录**:
| 测试项 | 输入 | 预期输出 | 实际输出 | 状态 |
|--------|------|----------|----------|------|
| | | | | |

### Phase 5: 交付与同步
- **目标**: 完成任务，同步文档
- **状态**: ⏳ pending
- **预计时间**: _m

- [ ] 代码提交（遵循 Git 规范）
- [ ] 按需更新当前 task session 中的 Goal / Scope / AC / 风险 / 验证证据
- [ ] 如形成长期规则，按需回写到对应 skill
- [ ] 如用户明确要求，再同步到新的 \`docs/\` 人类文档
- [ ] 关闭任务会话
- [ ] **检查点**: 所有当前主入口已更新

---

## 4. Findings（发现）

### 4.1 技术发现
| 发现 | 来源 | 影响 | 记录时间 |
|------|------|------|----------|
| | | | |

### 4.2 决策记录
| 决策 | 可选方案 | 选择理由 | 决策时间 |
|------|----------|----------|----------|
| | | | |

### 4.3 关联规范
| 规范文件 | 适用场景 | 关键要点 |
|----------|----------|----------|
| | | |

### 4.4 资源链接
-

---

## 5. Issues & Risks（问题与风险）

### 5.1 已解决问题
| 问题 | 严重程度 | 解决方案 | 解决时间 |
|------|----------|----------|----------|
| | | | |

### 5.2 待解决问题
| 问题 | 严重程度 | 计划解决 | 阻塞状态 |
|------|----------|----------|----------|
| | | | |

### 5.3 潜在风险
| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| | | | |

### 5.4 错误日志
| 时间 | 错误 | 尝试次数 | 最终解决 |
|------|------|----------|----------|
| | | | |

---

## 6. Progress Log（进度日志）

### Session ${DATE}

**开始时间**: $(date '+%H:%M')  
**结束时间**: _  
**持续时间**: _h _m

**本次目标**: [本次会话要完成的子目标]

**完成工作**:
- [ ]

**遇到的问题**:
-

**下一步计划**:
-

**文件变更**:
| 文件 | 操作 | 说明 |
|------|------|------|
| | | |

---

## 7. Summary（总结）

<!-- 任务完成后填写 -->

### 7.1 完成情况
- **目标达成**: ⬜ 完全达成 / ⬜ 部分达成 / ⬜ 未达成
- **达成说明**: 

### 7.2 交付物
| 交付物 | 位置 | 状态 |
|--------|------|------|
| | | |

### 7.3 经验教训
- **做得好的**: 
- **可以改进的**: 
- **知识沉淀**: 

### 7.4 后续工作
- [ ] 

### 7.5 文档同步检查清单
- [ ] 当前 task session 已补齐 Goal / Scope / AC / 风险 / 验证证据
- [ ] 如形成长期规则，已按需回写到对应 skill
- [ ] 如用户明确要求，人类文档已同步到新的 \`docs/\` 结构
- [ ] 代码已提交（遵循提交规范）
- [ ] 本文件已移动到 \`completed/\`

---

*任务会话模板 v1.0.0 | 创建于 ${CURRENT_TIME}*
EOF

echo -e "${GREEN}✅ 任务会话创建成功!${NC}"
echo ""
echo -e "${BLUE}文件信息:${NC}"
echo "  路径: .agents/task-sessions/active/${FILENAME}"
echo "  类型: ${TYPE} (${TYPE_DESC})"
echo "  版本: ${VERSION}"
echo ""
echo -e "${BLUE}下一步:${NC}"
echo "  1. 编辑文件，填写 Goal 和 Plan"
echo "  2. 开始执行任务"
echo "  3. 定期更新进度"
echo ""
echo -e "${BLUE}快捷命令:${NC}"
echo "  查看: cat .agents/task-sessions/active/${FILENAME}"
echo "  编辑: code .agents/task-sessions/active/${FILENAME}"
echo "  完成: mv .agents/task-sessions/active/${FILENAME} .agents/task-sessions/completed/"
echo ""

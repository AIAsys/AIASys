---
name: aiasys-git-workflow
description: |
  AIASys 项目专属 Git 工作流。当在 AIASys 项目中执行 git commit、创建分支、
  准备 PR、审计 worktree、整理提交历史时触发。
  适用于 AIASys 仓库内的版本控制规范，不适用于其他项目或个人仓库。
---

# AIASys Git 工作流

Git 提交、分支管理和 PR 协作的规范，确保代码历史清晰、安全、可追溯。

`git-workflow` 现在也是以下旧入口的 canonical skill：

- `pull-request`
- `worktree-status`

如果用户显式提到这些旧名字，允许通过 compatibility alias 触发，但执行时应回到本 skill。

---

## 核心原则

1. **精确暂存**：禁止 `git add .`，显式指定文件
2. **原子提交**：每批提交只做一件事
3. **安全第一**：提交前检查敏感信息
4. **清晰历史**：提交信息简洁明了

---

## 提交规范

### 精确暂存

```bash
# (正确) 正确：显式指定文件
git add apps/backend/app/api/file_router.py
git add apps/web/src/components/Button.tsx

# (错误) 错误：一键添加所有
git add .
```

### 提交信息格式

```
<type>(<scope>): <subject>

<body>
```

**类型（Type）：**

| 类型 | 用途 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(agent): 添加 Worker 汇报功能` |
| `fix` | 修复 bug | `fix(api): 修复 MCP 配置保存失败` |
| `docs` | 文档更新 | `docs: 更新 API 文档` |
| `style` | 代码格式 | `style: 格式化代码` |
| `refactor` | 重构 | `refactor: 重构会话管理` |
| `perf` | 性能优化 | `perf: 优化数据库查询` |
| `test` | 测试相关 | `test: 添加单元测试` |
| `chore` | 构建/工具 | `chore: 更新依赖` |
| `revert` | 回滚 | `revert: 回滚错误提交` |

**范围（Scope）：**

```
agent      - Agent 相关
api        - API 接口
frontend   - 前端代码
database   - 数据库
infra      - 基础设施
docs       - 文档
```

**示例：**

```bash
git commit -m "feat(mcp): 添加 MCP 配置批量导入功能

- 支持 CSV/JSON 格式导入
- 提供导入预览功能
- 记录导入日志

Closes: #123"
```

### 作者身份

```bash
# 使用当前仓库配置的用户
git config user.name "Your Name"
git config user.email "your.email@example.com"

# 提交时自动使用上述身份
# 禁止使用 "AI Developer" 等占位身份
```

---

## 分批次提交工作流

### 适用场景

- 工作区文件较多且杂乱
- 需要按逻辑分组提交
- 准备 PR 前整理提交历史

### 执行流程

**1. 检查当前状态**

```bash
git status --short
git log --oneline -5
```

**2. 分析文件分组**

按以下逻辑分组：
- **配置类**：`.gitignore`, `.env.example`, `lefthook.yml`
- **文档类**：`README.md`, `docs/**/*.md`
- **代码类**：按模块/功能分组
- **测试类**：`tests/**/*`, `**/*.test.ts`
- **资源类**：示例数据、图片
- **工具类**：脚本、CI/CD 配置

**3. 分批提交**

```bash
# 批次 1: 配置更新
git add .gitignore lefthook.yml
git commit -m "chore: 更新项目配置"

# 批次 2: 文档更新
git add docs/ README.md
git commit -m "docs: 更新文档"

# 批次 3: 功能代码
git add apps/backend/app/services/
git add apps/web/src/components/
git commit -m "feat: 添加 MCP 配置管理功能"

# 批次 4: 测试代码
git add tests/
git commit -m "test: 添加 MCP 服务单元测试"
```

---

## 提交前检查

### 安全检查（必须）

```bash
#!/bin/bash
# 提交前安全检查脚本

echo "(安全) 安全检查..."

# 1. 检查敏感文件
echo "检查敏感文件..."
SENSITIVE=$(git diff --cached --name-only | grep -E '\.(env|key|pem|p12|pfx)$' || true)
if [ -n "$SENSITIVE" ]; then
    echo "(错误) 发现敏感文件:"
    echo "$SENSITIVE"
    echo "请取消暂存: git reset HEAD <file>"
    exit 1
fi

# 2. 检查硬编码密钥
echo "检查硬编码密钥..."
KEYS=$(git diff --cached | grep -iE '(api_key|apikey|secret|password|sk-[a-zA-Z0-9]{32,}|ghp_[a-zA-Z0-9]{36})' || true)
if [ -n "$KEYS" ]; then
    echo "(警告) 发现可能的密钥:"
    echo "$KEYS"
    read -p "确认要继续吗? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 3. 检查大文件
echo "检查大文件..."
LARGE=$(git diff --cached --numstat | awk '$1 > 100 || $2 > 100 {print $3}' || true)
if [ -n "$LARGE" ]; then
    echo "(警告) 发现大改动文件:"
    echo "$LARGE"
fi

# 4. 检查空文件
echo "检查空文件..."
for file in $(git diff --cached --name-only --diff-filter=A); do
    if [ -f "$file" ] && [ ! -s "$file" ]; then
        echo "(警告) 空文件: $file"
    fi
done

echo "(正确) 安全检查完成"
```

### 代码检查

```bash
# 前端检查
cd apps/web
npm run lint
npm run type-check
npm run build

# 后端检查
cd apps/backend
ruff check app/
ruff format --check app/
```

---

## 分支管理

### 分支命名

```
feature/description   - 新功能
bugfix/description    - Bug 修复
hotfix/description    - 紧急修复
refactor/description  - 重构
docs/description      - 文档
```

### 活跃分支

- `main` — 生产分支，由主管理员管理
- `dev` — 开发分支，日常开发合并目标
- `feature/*`、`fix/*` — 功能/修复分支，从 dev 切出

**工作流**：
1. 从 `dev` 切出功能分支
2. 开发完成后合并回 `dev`
3. 需要发布时，从 `dev` 提 PR 到 `main`，由主管理员合并

### 工作流

```bash
# 1. 创建功能分支
git checkout -b feature/mcp-config

# 2. 开发并提交
git add ...
git commit -m "feat(mcp): ..."

# 3. 保持与主分支同步
git fetch origin
git rebase origin/dev

# 4. 推送分支
git push -u origin feature/mcp-config

# 5. 创建 PR（GitHub/GitLab）

# 6. 合并后清理
git checkout main
git pull origin main
git branch -d feature/mcp-config
```

---

## Worktree 工作流（高级）

### 何时使用

- 需要同时处理多个任务
- 需要维护多个版本
- 用户明确要求并行开发

### 使用规范

```bash
# 1. 创建 worktree
git worktree add ../aiasys-feature-mcp feature/mcp-config

# 2. 进入 worktree 工作
cd ../aiasys-feature-mcp

# 3. 完成后合并
git checkout main
git merge feature/mcp-config

# 4. 清理 worktree
git worktree remove ../aiasys-feature-mcp
git branch -d feature/mcp-config
```

**注意事项：**
- 每个 worktree 必须有独立分支
- 明确修改范围边界
- 主控掌握合并顺序

### Worktree 状态审计

当用户问：

- 哪些 worktree 可以清理
- 哪些 worktree 已合并
- 哪些分支还脏着

不要临时发明检查步骤，直接读取：

- `references/worktree-audit.md`

该参考稿承接了旧 `worktree-status` skill 的具体审计流程和输出表格格式。

---

## 变更记录更新

当前仓库可能不存在稳定的 `docs/changelog/` 主入口。

因此默认规则改为：

- 先以 Git 提交本身作为交付记录主链
- 需要 AI 侧持续追踪时，优先写入当前 active task session
- 只有当仓库当前明确保留人类可维护的 changelog 目录时，才额外补写 changelog 文件
- 如果 `docs/changelog/` 已被清空或重建中，不要为了一条提交重新造一套旧目录结构

---

## 完整提交示例

```bash
# 1. 检查状态
git status

# 2. 分批提交
git add apps/backend/app/api/mcp.py
git add apps/backend/app/services/mcp_service.py
git commit -m "feat(mcp): 添加 MCP 配置 CRUD 接口

- 实现配置增删改查
- 添加参数验证
- 统一错误处理"

git add apps/web/src/pages/MCPConfig/
git commit -m "feat(ui): 添加 MCP 配置管理页面

- 配置列表展示
- 新增/编辑表单
- 删除确认对话框"

git add tests/
git commit -m "test: 添加 MCP 功能测试

- 单元测试
- 集成测试"

# 3. 安全检查
git diff --cached --name-only | grep -E '\.(env|key|pem)$'
# Windows 替代: git diff --cached --name-only | findstr /R "\.(env|key|pem)$"
# 应无输出

# 4. 代码检查
# 如果项目提供跨平台检查脚本，运行它；否则手动执行等价检查
./.agents/skills/aiasys-workflow/scripts/check.sh  # Linux / macOS
# Windows 上若脚本不可用，直接运行脚本内的等价命令

# 5. Push
git push origin feature/mcp-config
```

---

## 快速检查清单

**提交前：**
- [ ] 使用 `git add <具体文件>` 而非 `git add .`
- [ ] 提交信息符合 `<type>(<scope>): <subject>` 格式
- [ ] 作者身份正确（非 AI Developer）

**安全检查：**
- [ ] 无敏感文件（.env, *.key, *.pem）
- [ ] 无硬编码密钥
- [ ] 无意外的大文件

**代码检查：**
- [ ] Lint 通过
- [ ] 类型检查通过
- [ ] 测试通过

**Push 前：**
- [ ] 已更新 Changelog
- [ ] 已同步文档
- [ ] 无 TODO/FIXME 遗留

---

## 应急处理

### 撤销提交

```bash
# 撤销最后一次提交，保留修改
git reset --soft HEAD~1

# 撤销最后一次提交，丢弃修改（危险！）
git reset --hard HEAD~1

# 撤销已 push 的提交（团队慎用）
git revert HEAD
git push
```

### 修改历史

```bash
# 修改最后一次提交
git commit --amend

# 修改多个提交（交互式）
git rebase -i HEAD~3
```

### 密钥泄露应急

```bash
# 1. 立即撤销密钥（在服务商控制台）

# 2. 从历史中移除
pip install git-filter-repo
git filter-repo --path .env --invert-paths

# 3. 强制推送
git push origin --force --all

# 4. 通知协作者
```

---

*清晰的 Git 历史是团队协作的基础——每个提交都应该是可理解、可回滚的原子单元。*

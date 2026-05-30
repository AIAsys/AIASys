---
name: github-project-management
description: GitHub 项目管理全流程指南。覆盖从代码提交到版本发布的完整链路：commit 决策框架、分批提交策略、PR 创建与 Review、Issue 管理、Tag 与 Release 发布。使用 gh CLI 完成所有 GitHub 操作。Use when committing code, creating PRs, reviewing PRs, managing issues, tagging releases, or organizing git history.
---

# Git 工作流

Git 提交、分支管理和 PR 协作的规范，确保代码历史清晰、安全、可追溯。

---

## 核心原则

1. **精确暂存**：禁止 `git add .`，显式指定文件
2. **原子提交**：每批提交只做一件事
3. **安全第一**：提交前检查敏感信息
4. **清晰历史**：提交信息简洁明了

---

## 提交规范

### AI 提交 message 约束

**AI 在构造 commit message 时，必须遵守以下硬性规则：**

- message 必须准确描述本次改动的内容和目的，不能笼统、不能跑题
- 反例：把"上传全部代码"写成 `docs: 更新分支策略...`（内容与主题完全不符）
- 正例：`feat: 上传全部代码至 li-xiu-qi 分支` 或 `chore: 将 AGENTS.md 等入口文件移入 .gitignore`
- 禁止写"修复若干问题""更新代码""各种改动"这类空泛描述
- 如果一次 commit 包含多种改动，优先拆分提交；确实不能拆分时，message 要覆盖所有主要改动

### Commit 后悔与修补

**当上一个 commit 还没"关闭"时（用户没有明确说"开始下一个 commit"），发现遗漏或需要修补，应该 amend 而不是新增 commit。**

Commit 后悔分两类：

**1. Message 问题（message 写错了）**
- 直接 `git commit --amend -m "正确的 message"`
- 然后 `git push --force`

**2. 内容问题（漏了文件、多了不该有的改动、代码写错了等）**
- 先修内容（改代码/删文件/补文件）
- `git add` 变更内容
- `git commit --amend --no-edit`（不改 message）或 `git commit --amend -m "..."`（同时改 message）
- 然后 `git push --force`

判断标准：
- 用户说"修复一下刚才那个 commit"、"这个也合到上一个 commit 里"、"还没开启下一个 commit" → amend
- 修补内容与上一个 commit 是同一主题的完善（如补充遗漏文件、修复 message、追加同类改动） → amend
- 修补内容与上一个 commit 主题无关，且用户明确说"这个单独提交" → 新 commit

**禁止行为**：
- 上一个 commit 还没收尾就擅自新建 commit
- 用"先提交再说，后面再 squash"的思路处理遗漏（0-1 阶段保持干净历史，不做 squash 债）

### CI 检查与 push 前置条件

**push 到远程之前，必须确保本地改动能通过 CI 等价的检查。CI 未通过的提交不应 push 到远程。**

CI 等价检查清单（push 前必须全部通过）：

- 后端：`ruff check app/` + `ruff format --check app/`
- 前端：`npm run lint` + `npm run type-check`
- 如有 test 则必须跑过
- 如有新文件需确认 `.gitignore` 规则正确（不会被误排除）
- 如有 lock 文件变更需确认依赖安装成功

**为什么 push 前必须本地验证（而非 push 后看 CI）：**

CI 失败后逐个修 commit 会导致：
1. 产生碎片化的 fix(ci) commit，污染 git 历史
2. 多次 force push，浪费 CI 资源
3. 给 reviewer 留下不专业的印象

正确做法是：本地跑等价检查 → 确认通过 → 一次性 push → CI 绿 → 提 PR。

**CI 失败的场景处理：**

如果已经 push 了但 CI 报红（或本地检查发现没通过就还没 push），按以下流程处理：

1. **撤销当前 commit**：`git reset --soft HEAD~1`（保留改动，回到暂存态）
2. **修复问题**：改代码直到本地检查通过
3. **重新提交**：`git add` 变更内容，`git commit` 或 `git commit --amend`（视情况）
4. **重新 push**：`git push --force`

如果改动已经在本地 commit 但还没 push，则直接 amend 修复：

1. 修复代码
2. `git add` 变更内容
3. `git commit --amend --no-edit`（或 `-m "新 message"`）
4. `git push --force`

**多轮 CI 修复的 squash 策略：**

如果已经产生了多个 fix(ci) commit（无论是历史遗留还是操作失误），**在 push 到 dev 之前**必须将它们 squash 成一个：

```bash
# 假设最近的 N 个 commit 都是 CI 修复
git rebase -i HEAD~N
# 将第 2~N 个标记为 squash/fixup
# 然后 force push
git push --force
```

目标：dev 分支上的 CI 修复应该是一个干净的 commit，而不是一串碎片。

**禁止行为**：
- CI 红了不管，直接 push 新的修复 commit 叠在上面
- 用"先提交看看 CI 过不过"的方式试探（应该本地先跑过等价检查）
- 多个 CI 修复 commit 不 squash 就直接 push 到 dev
- 在非本仓库 clone 中操作 git 前不检查 user.name/user.email（会导致 commit 作者变成 "Test User"）

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

## Commit 决策框架

分批提交的前提是知道**什么时候该 commit、什么时候不该 commit、一个主题是否值得独立成批**。这个决策框架在操作流程之前，是方法论层面的前置判断。

### 什么时候该 commit

改动规模不同，commit 的节奏也不同。核心原则是：**commit 时仓库必须处于可运行状态**。

**小改动（修 bug、改文案、单文件调整）：**

这类改动本身就是完整的。发现即修复、修复即验证、验证通过即 commit。不需要等整个功能模块做完。

- 典型场景：修一个拼写错误、改一个 API 返回字段名、补一个遗漏的 import
- 判断标准：改动范围小（通常 1-3 个文件）、影响边界清晰、不依赖其他未完成的改动

**大规模改动（新功能、重构、跨模块调整）：**

这类改动必须等整批完备后才能 commit。不能拆成碎片化的"先提交一部分、后面再补"。

- 典型场景：新增一个工具模块（涉及 tool.py、models.py、routes、tests）、全仓库类名重构、跨前后端的 API 改造
- 判断标准：改动跨多个文件或模块、文件间有逻辑依赖、单独提交任一部分都会让仓库处于"半成品"状态

**无论规模大小，以下条件必须全部满足：**

- **完整性**：这批改动构成一个逻辑上完整的单元，不会让仓库处于"半成品"状态。反例：只写了后端 API 没写前端调用方，且前端调用方是本次任务的必要部分
- **可验证性**：这批改动能独立通过 CI 检查（lint + type-check + test），不依赖尚未提交的其他改动
- **独立性**：这批改动不包含与主题无关的文件，不会把多个不相关的改动混在一起
- **非 WIP**：代码不是临时调试状态，没有注释掉的代码、调试日志、`console.log`/`print` 语句、临时 `TODO` 标记（正式记录的 TODO 除外）

### 什么时候不该 commit

**绝对不能 commit 的情况：**

- 代码无法通过 lint / type-check / test
- 包含调试用的临时代码（`console.log`、`print`、注释掉的代码块）
- 包含敏感信息（密钥、token、密码、API key）
- 改动依赖另一个尚未 commit 的改动（会导致 CI 失败）
- 改动主题混杂，无法用一句 commit message 说清楚

**建议暂缓 commit 的情况：**

- 当前正在等待另一个并行子任务的产出（如后端接口还没定，前端先写了 mock），commit 后 mock 代码会进入历史
- 改动规模太小（只改了一行格式化、一个拼写），除非是独立的格式修复任务
- 用户明确说"先别 commit"

### 如何判断一个主题是否足够独立成批

四个判断标准，全部满足即可独立成批：

1. **文件边界清晰**：这批文件不会和另一批共享同一个文件的同一段逻辑。如果一个文件被两个主题同时修改，要么合并为一批，要么先提交一批再在另一批中基于最新版本修改
2. **可独立 revert**：如果将来需要回滚这批改动，不会破坏其他功能
3. **可独立 review**：reviewer 只看这批 commit 就能理解改了什么、为什么改，不需要翻其他 commit
4. **commit message 能说清楚**：如果发现 commit message 需要用"和/以及/同时"连接多个不相关的动词，说明该拆分

**正例（适合作为一批）：**

- 全仓库把 `XxxTool` 类名改为 `Xxx`（同一主题，纯机械改动，无逻辑变更）
- 新增 `ask_user` 工具的 `description.md` 和对应 `tool.py` 改动（同一功能，文件间有直接依赖）
- 更新 `docs/` 下所有用户指南文档的 API 示例代码（同一类文档更新）

**反例（不应该作为一批）：**

- 把"修复 bug A"和"顺便改了变量命名风格"放在一起（两个独立主题，revert 风险高）
- 把"后端 API 改动"和"前端调用适配"放在一批（虽然逻辑相关，但 reviewer 需要同时理解两层代码；且如果 API 改坏了，前端适配也得一起回滚）
- 把"新增功能模块"和"删除废弃的旧模块"放在一批（两个方向相反的改动，review 时容易漏看删除部分）

---

## 分批提交操作流程

> 在执行分批之前，先过一遍 [Commit 决策框架](#commit-决策框架) 确认每批改动满足 commit 条件。

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

## 大规模改动的分批策略

> 大规模改动更需要先在 [Commit 决策框架](#commit-决策框架) 中逐批过一遍完整性和独立性。三步法帮你从 diff 全貌中提取逻辑分组，但每批是否值得独立 commit 的判断标准不变。

当一次开发任务产生了大量跨模块改动（几十上百个文件），直接按文件类型分组不够用。核心问题是：**改动之间有依赖关系，提交顺序必须保证每一批都能独立通过测试**。

### 三步法

**第一步：分析 diff 全貌**

```bash
git diff --stat          # 看文件数量和改动规模
git diff --name-only     # 看完整文件列表
```

关键动作：把文件列表过一遍，识别每个文件改动的大致主题。可以用 explore subagent 并行读 diff 来加速。

**第二步：提取逻辑分组**

不是按文件类型分，而是按改动主题分。常见主题模式：

| 模式 | 特征 | 示例 |
|------|------|------|
| 机械重命名 | 大量文件做同一类替换，无逻辑变更 | 工具类名去 `Tool` 后缀 |
| 级联适配 | 因改名导致的引用方同步更新 | system_presets 里的工具名字符串 |
| 架构变更 | 数据存储路径、模块拆分等结构性改动 | GraphRAG 从全局目录迁到工作区 |
| 新功能 | 独立的新增能力，不依赖其他改动 | 文件变更面板 |
| 测试适配 | 纯测试文件的 import/路径/mock 更新 | 测试里的类名从 `XxxTool` 改为 `Xxx` |
| 配置/文档 | prompt、manifest、模板等非代码文件 | host_prompt 简化 |

分组时注意：
- 一个文件可能涉及多个主题（如 `graphrag_tool.py` 既做了改名又改了路径逻辑），这时要判断：改名的部分和路径逻辑能拆开吗？不能拆就归入架构变更那批，因为那是实质改动
- 同名改动（如全仓库去 `Tool` 后缀）应该归为一批，不要按目录拆散

**第三步：决定提交顺序**

依赖关系决定顺序：

```
改名 → 级联适配 → 测试适配
         ↓
      架构变更（如果改了同名类）
```

原则：
- 被依赖的先提交（如改名在被引用方之前）
- 代码先于测试（测试引用了代码中的类名）
- 无依赖的批次可以任意顺序，但建议把风险最低的放前面（如纯文档改动）
- 每批提交后立即 push，不要攒到最后一起推

### 实操检查清单

提交前逐批确认：
- [ ] 这批改动有统一主题，一句话能说清楚
- [ ] 这批文件之间没有循环依赖（不会出现"B 依赖 A 但 B 先提交"的情况）
- [ ] 提交信息用 `refactor:` / `feat:` / `test:` / `docs:` 前缀准确描述主题
- [ ] 如果是纯机械改动，在 commit message 里注明"无逻辑变更"

### 反模式

- 不要按目录分组（`apps/backend/` 一批、`apps/web/` 一批），这会把无关改动混在一起
- 不要把一个主题的改动拆成多批（如工具改名分 3 批提交），review 时看不到全貌
- 不要等所有批次准备好再一起 push，每批 push 后远程就是可运行状态
- 不要在 commit message 里写"修复若干问题"这类模糊描述

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
uv run ruff check app/
uv run ruff format --check app/
uv run mypy app/ || true   # mypy 当前为 warn-only，不阻断
uv run pytest -v
```

---

## 分支管理

### 文档引用约束

**被 `.gitignore` 排除的文件和目录不应在仓库对外可见的文档中引用。**

当前被 gitignore 且不应被引用的内容：
- 根目录入口文件：`AGENTS.md`、`CLAUDE.md`、`GEMINI.md`
- AI 协作目录：`.agents/`（含 skills、task-sessions 等）
- 设计产物目录：`design-draft/`（含 design、archive 等）

规则：
- 对外文档（`README.md`、`CONTRIBUTING.md`、`docs/`、`apps/*/README.md` 等）不得引用上述被 gitignore 的内容
- 不要写 `[AGENTS.md](AGENTS.md)`、`详见 .agents/skills/`、`参考 design-draft/design/` 这类指向
- 被 gitignore 的文件之间互相引用（如 CLAUDE.md 引用 AGENTS.md）是允许的，因为它们同为本地 AI 入口文件
- `.gitignore` 文件本身引用被 gitignore 的内容是允许的，因为它的职责就是声明排除规则
- 历史 changelog 中记录当时事实的提及可以保留，因为那是历史档案不是当前指导
- 内置 skill 中提到的"项目 AGENTS.md"（如竞赛工作区内的 AGENTS.md）与仓库根 AGENTS.md 不同，不需要清理

### 当前仓库分支策略

**主仓库**：`https://github.com/AIAsys/AIASys`

当前仓库有三条分支，各自有不同的权责边界：

| 分支 | 角色 | 权责 |
|------|------|------|
| `main` | 正式发布分支 | 由 main 维护者管理。`dev → main` 的合入、正式 Release 发布由他们负责。**我们不动 main** |
| `dev` | 开发集成分支 | 由我们（ke）管理。`li-xiu-qi → dev` 的 PR 合入、dev 上的 tag 和 Pre-release 由我们负责 |
| `li-xiu-qi` | ke 的个人开发分支 | 日常开发在此进行，分批 commit 后 push，然后提 PR 合入 dev |

**数据流向：**

```
li-xiu-qi ──(PR)──> dev ──(PR)──> main
   ↑ 我们写代码      ↑ 我们合入+发pre-release   ↑ main维护者合入+发正式release
```

**我们的操作范围（仅限以下操作）：**

- 在 `li-xiu-qi` 上开发、commit、push
- 创建 `li-xiu-qi → dev` 的 PR
- 在 `dev` 的 merge commit 上打 tag、创建 Pre-release
- Review 别人向 `dev` 提的 PR

**我们不动的东西：**

- `main` 分支：不 push、不 merge、不打 tag、不创建正式 Release
- 其他非上述三条分支以外的分支：可能是其他人创建的，不查看、不修改、不删除

**禁止事项**：
- 禁止直接 push 到 `dev` 或 `main`
- 禁止在本地 merge 后 push dev
- 所有合入 dev 的操作必须走 GitHub PR
- 禁止动 `main` 分支上的任何东西
- 禁止操作 `main`、`dev`、`li-xiu-qi` 以外的任何分支

### 分支命名

```
feature/description   - 新功能
bugfix/description    - Bug 修复
hotfix/description    - 紧急修复
refactor/description  - 重构
docs/description      - 文档
```

### 工作流

```bash
# 1. 创建功能分支
git checkout -b feature/mcp-config

# 2. 开发并提交
git add ...
git commit -m "feat(mcp): ..."

# 3. 保持与主分支同步
git fetch origin
git rebase origin/main

# 4. 推送分支
git push -u origin feature/mcp-config

# 5. 创建 PR（GitHub/GitLab）

# 6. 合并后清理
git checkout main
git pull origin main
git branch -d feature/mcp-config
```

---

## PR 管理

PR 的创建和审核统一使用 `gh` CLI，不再依赖浏览器手动操作。

### 创建 PR

**前置条件（必须全部满足）：**

1. 当前分支是 `li-xiu-qi`，所有改动已 commit 并 push
2. CI 等价检查通过（lint + type-check + test）
3. 没有未推送的本地 commit
4. changelog 已更新（如果是功能变更）

**操作步骤：**

```bash
# 1. 确认当前状态
git status
git log origin/dev..HEAD --oneline   # 查看 dev 之后的新 commit

# 2. 确认 CI 等价检查通过
cd apps/backend && uv run ruff check app/ && uv run ruff format --check app/
cd apps/web && npm run lint && npx tsc --noEmit

# 3. 创建 PR
gh pr create \
  --base dev \
  --head li-xiu-qi \
  --title "feat(scope): 简短描述" \
  --body "## 改动内容
- 要点 1
- 要点 2

## 测试情况
- [x] 后端 pytest 通过
- [x] 前端 lint + type-check 通过

## 关联 Changelog
docs/changelog/vX.Y.Z_YYYY-MM-DD.md"
```

**标题规范**：沿用 commit message 的 `<type>(<scope>): <subject>` 格式。

**内容模板（功能/重构类改动）：**

```markdown
## 改动内容
- 要点 1
- 要点 2

## 测试情况
- [x] 后端 pytest
- [x] 前端 lint + type-check
- [x] 浏览器 smoke（如涉及 UI）

## 关联 Changelog
docs/changelog/vX.Y.Z_YYYY-MM-DD.md
```

小改动（修 bug、改文案）可以精简，不需要完整模板，但至少要写清楚改了什么。

**禁止行为**：
- 在 PR 描述中写"修复若干问题""各种改动"等空泛描述
- CI 等价检查未通过就创建 PR
- changelog 未更新就提功能变更的 PR

### Review PR

**第一步：获取 PR 信息**

```bash
# 列出 open 的 PR
gh pr list --state open

# 查看指定 PR 的详细信息（含已有评论）
gh pr view <number> --comments

# 查看 PR 的 diff
gh pr diff <number>
```

**第二步：代码审查**

Agent 需要逐文件审查 diff，检查以下维度：

- **逻辑正确性**：改动是否解决了预期问题，是否有遗漏的边界情况
- **规范符合性**：是否符合项目代码规范（ruff、ESLint、TypeScript 严格模式）
- **安全风险**：是否有密钥泄漏、注入风险、敏感信息暴露
- **性能问题**：是否有明显的 N+1 查询、不必要的重渲染、大文件读取
- **测试覆盖**：改动是否有对应的测试

**第三步：提交 Review**

```bash
# 通过
gh pr review <number> --approve --body "审核了 xxx 改动，逻辑正确，CI 通过，无安全风险。"

# 评论（中立，指出问题但不拒绝）
gh pr review <number> --comment --body "几点意见：
1. apps/backend/app/api/xxx.py:42 - 这里缺少参数校验
2. apps/web/src/components/Xxx.tsx:18 - 建议抽取为独立 hook"

# 请求修改
gh pr review <number> --request-changes --body "需要修改以下问题后才能合入：

**必须改：**
- apps/backend/app/services/xxx.py:30 - 存在 SQL 注入风险，需使用参数化查询

**建议改：**
- apps/web/src/pages/Xxx.tsx:55 - 变量命名不够清晰"
```

**Review 评论规范：**

- `--approve`：简要说明审核了什么、为什么通过，不能只写 "LGTM"
- `--comment`：逐条列出发现的问题，每条标注文件路径和行号
- `--request-changes`：明确区分"必须改"和"建议改"，必须改的项要说明原因

**安全检查清单（每次 Review 必须过一遍）：**

- [ ] 有没有 `.env`、密钥、token 泄漏
- [ ] 有没有 `console.log`、`print`、注释掉的调试代码
- [ ] 有没有意外的大文件改动（>500 行新增）
- [ ] 有没有对 `.gitignore` 之外敏感路径的引用

---

## Issue 管理

Issue 是仓库级别的任务跟踪单位，不绑定特定分支。使用 `gh` CLI 管理。

### 查看 Issue

```bash
# 列出所有 open 的 issue
gh issue list --state open

# 按 label 筛选
gh issue list --label bug
gh issue list --label enhancement

# 查看指定 issue 的详细内容和评论
gh issue view <number> --comments
```

### 创建 Issue

```bash
# 创建 issue
gh issue create \
  --title "简短描述问题或需求" \
  --body "## 问题描述
...

## 复现步骤
1. ...
2. ...

## 期望行为
..."

# 带 label 创建
gh issue create --title "..." --body "..." --label bug
```

仓库已配置 issue 模板（`.github/ISSUE_TEMPLATE/`），包含 Bug Report 和 Feature Request 两种模板。在 GitHub 网页端创建时会自动加载模板，`gh issue create` 走命令行则需手动写 body。

### 关闭和重开

```bash
# 关闭（通常附上关闭原因）
gh issue close <number> --comment "已在 #PR_NUMBER 中修复"

# 重开
gh issue reopen <number> --comment "问题复现，需要重新处理"
```

### Issue 与 PR 联动

在 PR 描述中使用 `Closes #123` 或 `Fixes #123`，PR 合入后对应 issue 会自动关闭。

---

## Tag 管理

Tag 是版本发布的锚点，让每个 changelog 版本在 Git 历史中可定位、可回溯。

### 版本号规则

沿用语义化版本号 `vMAJOR.MINOR.PATCH`：

- **MAJOR**：不兼容的 API 变更、架构大改。当前 0-1 阶段锁定为 `0`
- **MINOR**：向后兼容的新功能、新模块
- **PATCH**：向后兼容的 bug 修复、小优化

0-1 阶段版本号锁定在 `0.x.y`，MAJOR 升到 `1` 意味着产品达到稳定发布状态。

### Tag 打在哪个分支

Tag 按发布层级打在对应分支上：

| 分支 | Tag 类型 | 负责方 | 示例 |
|------|---------|--------|------|
| `dev` | 预发布版本 tag | ke（li-xiu-qi → dev 方向） | `v0.4.0` |
| `main` | 正式发布版本 tag | main 分支维护者（dev → main 方向） | `v0.4.0` |
| `main` | PATCH 版本 tag | main 分支维护者 | `v0.3.10` |

关键约束：

- **你在 dev 上打 tag**：`li-xiu-qi` 合入 `dev` 后，在 dev 的 merge commit 上打附注 tag，对应 dev 上的 pre-release
- **main 维护者在 main 上打 tag**：`dev` 合入 `main` 后，在 main 的 merge commit 上打附注 tag，对应正式 release
- 同一个版本号（如 `v0.4.0`）会先后出现在 dev 和 main 上：dev 上是预发布，main 上是正式发布。两者不冲突，因为 main 的 tag 在 dev 的 tag 之后，且 main 包含了 dev 的全部内容
- **禁止在 `li-xiu-qi` 上打 tag**，所有 tag 都在合入目标分支后打在 merge commit 上

### Tag 与 Changelog 的关系

- 打 tag 之前，对应版本的 changelog 文件必须已经存在且版本号匹配
- changelog 文件名格式：`vX.Y.Z_YYYY-MM-DD.md`
- tag message 第一行写版本号 + 日期，后面附 changelog 要点摘要
- 如果某个版本有多天 changelog，tag message 里汇总关键条目

### 操作规范

**在 dev 上打 tag（预发布，由你负责）：**

```bash
# li-xiu-qi 合入 dev 后，在 dev 分支上
git checkout dev
git pull origin dev

# 打附注 tag
git tag -a v0.4.0 -m "v0.4.0 - 2026-05-28

新功能:
- 新增 xxx 模块
- 新增 yyy 工具

修复:
- 修复 zzz 问题"

# 推送 tag 到远程
git push origin v0.4.0
```

**在 main 上打 tag（正式发布，由 main 维护者负责）：**

```bash
git checkout main
git pull origin main

git tag -a v0.4.0 -m "v0.4.0 - 2026-05-28

（从 dev 的 changelog 汇总正式发布内容）"

git push origin v0.4.0
```

**禁止行为：**

- 在 `li-xiu-qi` 分支上打 tag
- 打 tag 后不推送（本地 tag 没有分发价值）
- 对已推送的 tag 做 `--force` 覆盖（除非是立即发现打错且确认无人拉取）
- 用 `git push --tags` 推送所有本地 tag（容易把实验性 tag 推上去）

### 删除或修正 tag

```bash
# 删除本地 tag
git tag -d v0.4.0

# 删除远程 tag
git push --delete origin v0.4.0

# 仅在确认无人拉取时重新打
git tag -a v0.4.0 -m "..."
git push origin v0.4.0
```

### Tag 与 Release

Tag 推送后，需要在 GitHub 上创建对应的 Release，上传桌面版打包产物供用户下载。

**发布分层：**

```
你负责:    li-xiu-qi → dev (PR) → dev 上打 tag → Pre-release（预发布）
main 维护者: dev → main (PR) → main 上打 tag → 正式 Release
```

**Release 与 Tag 的对应关系：**

| 分支 | Tag | Release 类型 | 说明 |
|------|-----|-------------|------|
| `dev` | `v0.4.0` | Pre-release | 由你创建，上传打包产物，标记为预发布 |
| `main` | `v0.4.0` | 正式 Release | 由 main 维护者创建，上传打包产物 |
| `main` | `v0.3.10` | 正式 Release | PATCH 版本 |

注意：同一个版本号 `v0.4.0` 会先后出现在 dev（pre-release）和 main（正式 release）。dev 上的 pre-release 是给测试用户试用的，main 上的正式 release 是面向所有用户的稳定版本。

**Release 内容规范：**

- **标题**：版本号（如 `v0.4.0`）
- **描述**：从 changelog 文件中提取的版本更新摘要
- **附件**：三平台打包产物（产物在 `apps/desktop/dist/` 下，已被 `.gitignore` 排除，不进 Git 仓库）
  - Linux: 将 `dist/` 下的目录打包为 `.tar.gz`
  - Windows: NSIS 安装包 (`.exe`) + 便携版 (`.zip`)
  - macOS: DMG 镜像 (`.dmg`) + 便携版 (`.zip`)

**0-1 阶段手动发布步骤（dev 上的 pre-release）：**

1. 在各平台机器上构建打包产物：
   ```bash
   cd apps/desktop
   npm run dist:linux:dir   # Linux
   npm run dist:win         # Windows
   npm run dist:mac         # macOS
   ```
2. 确认产物在 `apps/desktop/dist/` 下
3. `li-xiu-qi` 合入 `dev` 后，在 dev 分支上打 tag 并推送（见上文操作规范）
4. 在 GitHub 仓库页面进入 Releases → "Draft a new release"
5. 选择对应的 tag，填写标题和 changelog 摘要
6. 勾选 "Set as a pre-release"
7. 拖拽上传三平台打包产物
8. 点击 "Publish release"

**禁止行为：**

- 把打包产物（`apps/desktop/dist/` 下的任何文件）提交到 Git 仓库
- 在 Release 中上传非构建产物的文件（源码、临时文件等）
- 创建没有对应 tag 的 Release
- 在 dev 上创建正式 Release（dev 上的 release 必须标记为 pre-release）

### CI 自动 Beta Release 策略

`ci-desktop.yml` 在 push to `dev` 时自动构建三平台桌面版并发布 pre-release。以下规则避免版本混乱：

**触发条件：**
- 仅当 `apps/desktop/**`、`apps/backend/**`、`apps/web/**`、`.github/workflows/ci-desktop.yml` 变更时触发
- 纯文档（`docs/`）、skill（`.agents/skills/`）、配置（`.gitignore`）变更**不会**触发

**版本号模型：**

```
package.json version = 0.3.9        ← 产品稳定版本号（三端一致）
                                   ↓
Beta tag = v0.3.9-beta.{N}        ← N 为递增序号（从 1 开始，不是 commit SHA）
                                   ↓
正式 release tag = v0.3.9         ← dev → main 合入后由 main 维护者发布
```

**关键规则：**

| 规则 | 说明 |
|------|------|
| `package.json` version 只在正式 release 前 bump | Beta 期间不动版本号，靠 beta 序号区分 |
| Beta tag 格式 | `v{VERSION}-beta.{N}`，N 自动递增（查询已有 tag 数量） |
| 同一 base version 的 beta 可以覆盖 | `v0.3.9-beta.1` → `v0.3.9-beta.2` → ...，直到 `v0.3.9` 正式发布 |
| 正式发布后 bump 版本 | 如 `v0.3.9` → `v0.3.10`，下一轮 beta 从 `v0.3.10-beta.1` 开始 |
| 非代码变更不触发构建 | 改 README、skill、changelog 等不产生新 beta |

**完整生命周期示例：**

```
v0.3.9-beta.1 → v0.3.9-beta.2 → v0.3.9-beta.3 → v0.3.9 (正式)
                                                        ↓
                                                v0.3.10-beta.1 → ...
```

**手动发布：**
- `workflow_dispatch` 不受 paths 限制，随时可手动触发构建
- 可用于验证 CI 配置或紧急发布

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
- 当前 active task session 必须同步登记 `worktree / branch / 负责人 / 状态 / 写集边界`

当用户明确要求并发 worktree 开发，或者你准备派多个 worker 时，不要只看上面的 4 行示例，继续读取：

- `references/parallel-worktree-development.md`

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

`docs/changelog/` 是对外发布版本的精修 changelog。日常迭代的原始记录放在 `design-draft/change-log/drafts/`（不进入版本控制）。

流程：

- 日常开发时，在 `design-draft/change-log/drafts/` 下按日期或功能模块创建草稿，随手记录改动
- 准备发布时，从草稿中挑选对外值得说的条目，精修后写入 `docs/changelog/vX.Y.Z_YYYY-MM-DD.md`
- 文件名格式：`vX.Y.Z_YYYY-MM-DD.md`
- 编写规范见 `docs/changelog/README.md`

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
# 应无输出

# 4. 代码检查
./.agents/skills/aiasys-workflow/scripts/check.sh

# 5. Push 到个人分支
git push origin li-xiu-qi

# 6. 如需合入 dev，在 GitHub 上创建 PR：li-xiu-qi → dev
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
- [ ] 后端 ruff check + ruff format check 通过
- [ ] 前端 lint + type-check 通过
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

---
name: pr-check
description: |
  PR 提交前与合并前检查。当需要创建 PR、审查 PR、合并 PR、
  或检查代码是否准备好提交到 dev/main 时触发。
  覆盖：gitignore 违规、大文件、敏感文件、task-session 泄漏、
  commit message 规范、二进制文件检查、冲突标记残留、
  行尾符一致性、skill 注册完整性。
  适用于 AIASys 项目的所有 PR 审查场景。
---

# PR Check — 提交与合并前检查清单

## 定位

本 Skill 提供一套可编程执行的 PR 质量检查规则，供 Agent 在以下节点自动执行：

- 提交代码前（pre-commit 补充检查）
- 创建 PR 前
- 合并 PR 前
- 用户要求"检查一下能不能提交/合并"时

所有检查均基于 Shell 命令实现，不依赖外部 CI 服务。

## 检查清单

### 1. Gitignore 违规检查

被 `.gitignore` 规则排除的文件不应出现在仓库中。

```bash
# 列出所有被 gitignore 但已被跟踪的文件
git ls-files -i --exclude-standard
```

**判定**：有任何输出 → 违规。这些文件应从仓库移除并更新 `.gitignore`。

---

### 2. 大文件检查

GitHub 单文件 50MB 触发警告，100MB 硬拒绝。

```bash
# 列出当前分支新增/修改的大文件（>10MB 值得关注）
git diff --stat origin/dev...HEAD | awk '{print $1}' | while read f; do
  if [ -f "$f" ]; then
    size=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null)
    if [ "$size" -gt 10485760 ]; then
      echo "$(echo "scale=1; $size/1048576" | bc)MB $f"
    fi
  fi
done
```

**判定**：
- >100MB → 阻断，必须使用 Git LFS 或改为按需下载
- >50MB → 警告，建议改为按需下载脚本
- <50MB 但为平台二进制 → 警告，应放 `vendor/` 并由下载脚本管理

---

### 3. 敏感文件检查

以下文件类型不应提交到仓库：

| 模式 | 说明 |
|------|------|
| `*.pem`、`*.key`、`*.crt` | 证书与私钥 |
| `.env`、`.env.*` | 环境变量文件 |
| `*credentials*`、`*secret*` | 凭证文件 |
| `*.token` | Token 文件 |

```bash
# 检查是否有敏感文件被提交
git diff --name-only origin/dev...HEAD | grep -iE '\.(pem|key|crt)$|\.env$|\.env\.|credential|secret|\.token$'
```

**判定**：有任何输出 → 阻断，必须撤销提交并从历史中清除。

---

### 4. Task-session 文件泄漏检查

`.agents/task-sessions/` 目录下的文件不应提交（已在 `.gitignore` 中配置）。

```bash
git ls-files .agents/task-sessions/ 2>/dev/null
```

**判定**：有任何输出 → 违规。移除文件，用 `filter-repo` 或 `filter-branch` 清理历史。

---

### 5. Commit Message 规范检查

AIASys 项目的 commit message 约定（见 `CONTRIBUTING.md` 与 `.team-skills/aiasys-git-workflow/SKILL.md`）：

- 采用 Conventional Commits 格式：`type(scope): subject`
- 中英文均可，但避免无意义占位符
- 常用 type：`feat`、`fix`、`refactor`、`chore`、`docs`、`test`、`style`、`perf`
- 一个 commit 只做一个逻辑单元，禁止把前端 UI、后端 API、bugfix、文档混在一个 commit

```bash
# 检查当前分支待合并的 commit message
git log origin/dev..HEAD --oneline
```

**判定**：
- 包含英文占位符（`update code`、`fix bug`、`WIP`）→ 建议修改
- 包含 `TODO`、`FIXME` 作为主要描述 → 建议修改
- 无 type 前缀 → 建议补上
- 一个 commit 涉及多个不相关领域 → 建议拆分

---

### 6. 合并冲突标记检查

`<<<<<<<`、`=======`、`>>>>>>>` 不应出现在任何已提交的文件中。

```bash
git diff origin/dev...HEAD | grep -nE '^(<<<<<<<|=======|>>>>>>>)'
```

**判定**：有任何输出 → 阻断。存在未解决的合并冲突。

---

### 7. 行尾符一致性检查

CRLF/LF 混用的文件会在跨平台协作中产生不必要的 diff 噪音。仓库配置了 `.gitattributes` 自动处理，但仍需检查新增文件。

```bash
# 检查本次 PR 中是否有 CRLF/LF 混用的文件
git diff --name-only origin/dev...HEAD | while read f; do
  if [ -f "$f" ]; then
    crlf=$(grep -U $'\r' "$f" | wc -l)
    lf=$(grep -c '' "$f" 2>/dev/null || echo 0)
    [ "$crlf" -gt 0 ] && [ "$crlf" -ne "$lf" ] && echo "MIXED: $f (CRLF:$crlf LF:$lf)"
  fi
done
```

**判定**：有输出 → 建议修复。

---

### 8. 平台二进制文件检查

平台特定二进制文件不应直接提交，应通过按需下载脚本管理（参考 `vendor/uv/`、`vendor/node/` 的处理方式）。

```bash
# 检出新增的二进制文件
git diff --name-only --diff-filter=A origin/dev...HEAD | while read f; do
  if [ -f "$f" ] && file "$f" | grep -qE 'ELF|Mach-O|PE32'; then
    echo "BINARY: $f"
  fi
done
```

**判定**：有输出 → 阻断。应改为下载脚本 + `.gitignore` 排除模式。

---

### 9. Changelog 与版本号检查

#### Changelog 检查

任何用户可感知的功能新增、bug 修复、性能优化、接口不兼容修改，必须随 PR 同步更新 `docs/changelog/`。

```bash
# 检查本次 PR 是否涉及用户 facing 改动（示例：新增/修改 app/、web/src/ 下代码）
git diff --name-only origin/dev...HEAD | grep -E '^(apps/backend/app/|apps/web/src/|apps/desktop/src/)'

# 如涉及用户 facing 改动，检查是否同步了 changelog
git diff --name-only origin/dev...HEAD | grep '^docs/changelog/'
```

**判定**：
- 有代码改动但无对应 changelog 更新 → 建议补充（release PR 必须）
- 纯文档/格式/配置改动 → 可跳过

#### 版本号检查（release PR）

若本次 PR 是 release PR（`dev` → `main`），必须确认三端版本号一致：

```bash
grep '"version":' apps/web/package.json | head -1
grep '"version":' apps/desktop/package.json | head -1
grep '^version = ' apps/backend/pyproject.toml
```

**判定**：三处版本号不一致 → 阻断，必须同步。

---

### 10. Skill 注册完整性检查

新增或修改 Skill 时，需确认相关注册文件同步更新。

**新增 Skill 检查项**：
- `SKILL.md` 包含有效的 frontmatter（`name`、`description` 字段）
- Skill 目录在 `.team-skills/` 下
- 如果属于 capability 体系，对应的 `manifest.toml` 已更新
- `team-skill-guide/SKILL.md` 中的快速选择表已更新（如适用）

**修改 Skill 检查项**：
- 改了 AGENTS.md 约束 → 检查受影响的 Skill 是否需要同步更新
- 改了用户-facing 功能 → `docs/guides/` 是否同步

```bash
# 列出本次变更涉及的 skill 目录
git diff --name-only origin/dev...HEAD | grep '\.team-skills/' | cut -d'/' -f1-2 | sort -u
```

---

### 10. AGENTS.md 影响检查

如果 PR 修改了与 `AGENTS.md` 规则相关的代码，需确认 AGENTS.md 已同步更新。

```bash
# 检查是否修改了 AGENTS.md 关注的核心模块
git diff --name-only origin/dev...HEAD | grep -E 'apps/backend/app/core/|apps/backend/app/models/|apps/backend/app/services/|apps/web/src/types/'
```

**判定**：有输出 → 提醒审查者确认 AGENTS.md 是否需要更新。

---

### 11. 临时文件/调试脚本残留检查

开发过程中会产生大量临时脚本和调试产物。如果不清理就提交，会导致仓库膨胀、混淆正式代码。

**检测模式**：

| 模式 | 特征 | 示例 |
|------|------|------|
| 数字后缀迭代 | 同一脚本名 + 递增数字 | `sidebar-review.mjs` ~ `sidebar-review12.mjs` |
| 调试前缀 | `debug-*`、`test-*`（非正式测试） | `debug-cdp.mjs`、`debug-fonts.mjs` |
| 分析前缀 | `analyze-*` | `analyze-menu-entry.mjs` |
| 一次性检查 | `check-*`、`*-check` | `check-indicator.mjs`、`homepage-check.mjs` |
| 功能重复 | `.cjs` 和 `.mjs` 做同一件事 | `screenshot-tabs.cjs` + `screenshot-tabs.mjs` |
| 大体积产物 | >500KB 的非代码文件 | `subagent-sidebar-review` (1.2MB) |
| 硬编码过期 ID | 含 `workspace_id=xxx&session_id=xxx` | 过期后无法复用 |

```bash
# 检查未跟踪文件中的临时脚本/调试产物
git ls-files --others --exclude-standard | grep -iE '(debug-|analyze-|check-|review[0-9]|screenshot-|verify-|inspect-|homepage-|test-settings|test-simple|diagnose-)' 2>/dev/null

# 检查大体积产物（>500KB）
find . -path ./node_modules -prune -o -path ./.venv -prune -o -path ./.git -prune -o -type f -size +500k -print 2>/dev/null | while read f; do
  if ! file "$f" | grep -qE 'image|archive|data|PDF'; then
    echo "LARGE_ARTIFACT: $f ($(du -h "$f" | cut -f1))"
  fi
done

# 检查功能重复的脚本（.cjs 和 .mjs 同名）
git ls-files --others --exclude-standard | grep -oP '.*(?=\.(cjs|mjs))' | sort | uniq -d | while read base; do
  echo "DUPLICATE: $base.cjs + $base.mjs"
done
```

**判定标准**：

| 判定 | 条件 | 处理 |
|------|------|------|
| 可复用 | 功能完整、可配置（环境变量）、无硬编码过期 ID | 移到正式目录 |
| 一次性 | 硬编码过期 ID、仅验证当前状态 | 删除 |
| 中间迭代 | 同一功能有多个版本号递增的文件 | 只保留最终版，删除中间版本 |

**文件落位规范**：

| 文件类型 | 落位目录 |
|----------|----------|
| 项目级工具脚本 | `scripts/` |
| 前端开发工具 | `apps/web/scripts/committed/` |
| 正式 E2E 测试 | `apps/web/e2e/`（`.spec.ts` 格式） |
| 设计/视觉评审 | `scripts/design/` |
| 临时证据图 | `design-draft/archive/artifacts/`（已 gitignore） |

---

## 执行流程

Agent 在创建/审查 PR 时应按以下顺序执行：

1. **快速阻断检查**（1-4）：gitignore 违规、敏感文件、冲突标记 → 任一命中则阻断
2. **质量检查**（5-7）：commit message、行尾符、大文件 → 建议修复
3. **完整性检查**（8-10）：二进制文件、Skill 注册、AGENTS.md 影响 → 按情况判断
4. **卫生检查**（11）：临时文件/调试脚本残留 → 清理后提交

## 自动执行脚本

可将上述检查封装为单条命令执行：

```bash
# 快速阻断检查（预期零输出）
echo "=== gitignore violations ===" && git ls-files -i --exclude-standard 2>/dev/null
echo "=== task-sessions ===" && git ls-files .agents/task-sessions/ 2>/dev/null
echo "=== sensitive files ===" && git diff --name-only origin/dev...HEAD | grep -iE '\.(pem|key|crt)$|\.env$|\.env\.|credential|secret|\.token$' 2>/dev/null
echo "=== conflict markers ===" && git diff origin/dev...HEAD | grep -nE '^(<<<<<<<|=======|>>>>>>>)' 2>/dev/null
echo "=== binary files ===" && git diff --name-only --diff-filter=A origin/dev...HEAD | while read f; do [ -f "$f" ] && file "$f" 2>/dev/null | grep -qE 'ELF|Mach-O|PE32' && echo "BINARY: $f"; done
echo "=== commit messages ===" && git log origin/dev..HEAD --oneline
echo "=== temp/debug scripts ===" && git ls-files --others --exclude-standard | grep -iE '(debug-|analyze-|check-|review[0-9]|screenshot-|verify-|inspect-|homepage-|test-settings|test-simple|diagnose-)' 2>/dev/null
```

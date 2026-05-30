---
name: gen-docs
description: |
  Canonical documentation maintenance skill for this repo family.
  Use when the user asks to update user docs, tutorials, changelogs, release notes,
  or bilingual documentation; it absorbs the old `gen-changelog` and `translate-docs`
  entrypoints and should be the single workflow for doc updates before release or handoff.
---

# gen-docs

`gen-docs` is the canonical skill for documentation maintenance in this repo family.

It now absorbs three previously separate asks:

1. 更新用户文档
2. 生成 / 同步 changelog
3. 中英双语同步
4. 归档和下沉已经过时的文档

If the task is mainly:

- 需求定义和 PRD 对齐，优先用 `aiasys-product-requirements`
- 旧文档归档，也从这里进入，但按“归档模式”执行
- 单纯把文档翻译成另一种语言，仍从这里进入，但按“翻译模式”执行

---

## 执行原则

### 1. 先看真实变更，再写文档

不要只根据 commit message 改 docs。

至少确认：

- 当前 diff / 最近提交
- 真实代码路径
- 用户可见行为是否真的变化

### 2. changelog 先写草稿，再精修发布

如果任务涉及 release notes / changelog：

1. 日常迭代时先在 `design-draft/change-log/drafts/` 记录原始改动
2. 发布时从草稿中挑选对外条目，精修后写入 `docs/changelog/vX.Y.Z_YYYY-MM-DD.md`

不要跳过草稿直接写对外 changelog，也不要只写草稿不发精修版。

### 3. 双语同步要明确方向

默认方向：

- `Changelog / release notes`：以英文源为准，同步到中文
- 其他产品/用户文档：以仓库当前主语种为准，再同步另一语言

如果仓库本身已有 `docs/AGENTS.md` 或术语表，优先服从那里的语言约定。

### 4. 只写用户能感知到的变化

不要把纯内部重构写进用户文档或 changelog。

应该优先覆盖：

- 新入口
- 行为变化
- 生命周期变化
- 配置变更
- 破坏性变更

---

## 标准流程

### 模式 A：更新现有用户文档

适用：

- README
- getting-started
- 教程页
- 功能说明页

步骤：

1. 读取仓库级 `AGENTS.md` 和局部 docs 规则
2. 核对代码和当前界面/接口真相
3. 更新受影响页面
4. 如果页面有多语言版本，同步另一语言
5. 复查链接、截图、命令和路径

### 模式 B：changelog / release notes

适用：

- `docs/changelog/vX.Y.Z_YYYY-MM-DD.md`（对外精修版）
- release notes
- breaking changes

步骤：

1. 分析相对主分支的有效用户变更
2. 在 `design-draft/change-log/drafts/` 下创建或追加草稿记录（日常迭代时）
3. 发布时从草稿中挑选对外值得说的条目，精修后写入 `docs/changelog/vX.Y.Z_YYYY-MM-DD.md`
4. 确认术语、标题层级和版本节奏一致
5. **在 dev 分支上打 tag**（详见 `github-project-management` skill 的 Tag 管理章节）：
   - 确认 changelog 文件版本号与 tag 版本号一致
   - 使用附注 tag，message 中附 changelog 要点摘要
   - `git tag -a vX.Y.Z -m "..."` 然后 `git push origin vX.Y.Z`
6. **创建 GitHub Pre-release**（详见 `github-project-management` skill 的 Tag 与 Release 章节）：
   - 构建各平台打包产物（`npm run dist:linux:dir` / `dist:win` / `dist:mac`）
   - 在 GitHub Releases 页面基于 dev 的 tag 创建 release
   - 勾选 "Set as a pre-release"
   - 上传三平台打包产物作为附件

### 模式 C：双语同步

适用：

- 中英 README
- 产品说明
- 教程

步骤：

1. 先确认哪一边是事实源
2. 按段落同步而不是只做整页机翻
3. 保持结构、示例、标题和代码块一致
4. 必要时回看代码，避免术语漂移

### 模式 D：文档归档 / 历史材料下沉

适用：

- 用户明确要求“归档”“下沉历史文档”“收口旧 docs”
- 某些文档已经只剩追溯价值，却还占着 `docs/` 主入口

步骤：

1. 先判断文档是否真的不该继续留在 `docs/`
2. 物理移动到 `archive/`，而不是只在原地写“已归档”
3. 修 README / 索引 / 入口链接
4. 如内容本质上是 AI 规则，则迁入 skill / AGENTS / task session

详细规则见：

- `references/docs-archiving.md`

---

## 兼容别名

以下旧 skill 名现在都应回到本 skill：

- `gen-changelog`
- `translate-docs`
- `docs-archiving`

如果这些 alias 被触发：

1. 先加载本 skill
2. 再按对应模式执行

---

## 模式 E：文档审计

在更新文档之前，先审计现有文档与代码之间的一致性。文档不一致的方向几乎总是文档落后于代码。

### 7 种不一致模式

**1. 版本号漂移**：文档里写死了版本号，代码升级后没人同步。检测方式：搜索文档中的 `v\d+\.\d+`，和 `package.json`/`pyproject.toml` 对比。

**2. 文件路径腐烂**：文档引用的文件被移动、重命名或删除后引用变成死链。检测方式：从文档中提取所有文件路径引用，逐一用 `test -f` / `test -d` 校验。子类型包括重命名、移动、删除、相对路径算错。

**3. 命名体系迁移残留**：项目进行过命名统一，但部分文档/代码/注释没跟上。检测方式：搜索旧术语（按项目的术语表），对照 AGENTS.md 或 `terminology/` 判断是否应替换。

**4. API 契约断裂**：文档描述的 API 端点、参数、响应格式与实际路由不匹配。检测方式：提取文档中的 HTTP 方法和路径，和 FastAPI 路由注册代码对比，检查端口号、路径前缀、请求/响应字段名。

**5. 架构概念过时**：文档描述的是已被替换的架构方案。检测方式：检查文档是否有"已废弃""不成立""历史材料"标记，没有标记但内容明显偏离当前实现的属于遗漏归档。

**6. 配置/环境参数过期**：文档中的端口号、环境变量、认证方式与运行时不一致。检测方式：搜索文档中的端口号、环境变量名，和 `config.json`/`.env`/`vite.config.ts` 对比。

**7. Skill/能力清单不同步**：文档列的 Skill 列表和实际目录不一致。检测方式：`ls` 实际目录后和文档表格逐行对比。

### 审计流程

1. 确定审计范围：哪些目录的文档需要检查（docs/、design-draft/、apps/*/docs/、AGENTS.md 等）
2. 并行启动 explore Agent：按目录拆分，每个 explore Agent 负责一个子目录
3. 逐个文件读取内容，不是只扫文件名
4. 交叉验证：文档声明 vs 代码事实（用 Shell/Grep/Glob 验证）
5. 按严重程度分级：高（影响正确性/可操作性）、中（陈旧但不阻塞）、低（历史残留/轻微偏差）
6. 先汇报后修复：列出所有发现，让用户确认后再批量修改

### 修复策略

| 文档状态 | 策略 |
|---|---|
| 全文描述已废弃的架构/认证/API | 归档到 `design-draft/archive/` 或删除 |
| 局部过时但仍有参考价值 | 标注"已废弃"并指向当前文档 |
| 版本号/端口号/路径过期 | 直接更新 |
| 命名体系迁移残留 | 批量替换（注意不要误伤 changelog 历史记录） |

注意事项：changelog 中的旧术语和旧版本号是历史记录，不应修改；已标注"历史材料""不成立"的文档不需要再标注一次；断链修复时注意相对路径的 `../` 层级；删除文件前向用户确认。

---

## 交付检查

完成一次 docs 维护，至少确认：

- 已核对真实代码/行为，不是只看 commit message
- changelog 改动先落草稿（`design-draft/change-log/drafts/`），发布时精修到 `docs/changelog/`
- 如有多语言版本，方向已明确且已同步
- 路径、命令、截图、标题、链接没有明显漂移

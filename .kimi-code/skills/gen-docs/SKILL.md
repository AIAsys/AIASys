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

### 2. changelog 先改源，再改派生页

如果任务涉及 release notes / changelog：

1. 先改根源 CHANGELOG
2. 再同步英文 docs 页
3. 最后同步中文 docs 页

不要先改派生页再回填源文件。

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

- `CHANGELOG.md`
- release notes
- breaking changes

步骤：

1. 分析相对主分支的有效用户变更
2. 更新源 `CHANGELOG.md`
3. 如仓库存在 changelog 同步脚本，运行它
4. 更新中文 release notes / breaking changes
5. 确认术语、标题层级和版本节奏一致

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

## Kimi Code CLI / vendored docs 特别规则

如果当前任务落在 Kimi Code CLI 文档体系：

- 先看 `docs/AGENTS.md`
- changelog 英文页优先用 `node docs/scripts/sync-changelog.mjs` 同步
- 再处理中文 release notes / breaking changes

如果当前任务不是 Kimi Code CLI 文档，不要机械执行这些脚本。

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

## 交付检查

完成一次 docs 维护，至少确认：

- 已核对真实代码/行为，不是只看 commit message
- changelog 改动先落源文件
- 如有多语言版本，方向已明确且已同步
- 路径、命令、截图、标题、链接没有明显漂移

---
name: doc-sync
description: |
  Maintain consistency between user-facing documentation and code.
  Use when: (1) code changes affect documented behavior, (2) auditing
  docs for staleness, (3) establishing/updating the doc-code mapping
  index. Complements `gen-docs` by providing the mapping infrastructure
  and sync-trigger rules.
---

# doc-sync

## 为什么需要这个 Skill

AIASys 的 `docs/guides/` 下有 30+ 个用户文档，覆盖 35+ 功能点。代码持续迭代时，文档和代码之间必然出现漂移。`gen-docs` 的审计模式（模式 E）能检测 7 种不一致，但缺少一个关键基础设施：文档-代码映射索引。

没有这个索引：
- 改了某段代码后，不知道该检查哪些文档
- 审计只能全量扫描，效率低
- 新增功能后，不知道该创建什么文档

## 核心机制

### 1. 文档-代码映射索引

`docs/guides/DOC_CODE_MAP.md` 是核心索引文件，记录每个文档对应的代码路径。

格式：

```markdown
# 文档-代码映射索引

> 随代码变更持续更新

## file-management.md
- 覆盖功能: 文件浏览、编辑、预览、上传、历史版本、差异对比
- 前端组件:
  - apps/web/src/components/layout/WorkspaceSidebar/WorkspaceContextPanel.tsx (文件树)
  - apps/web/src/components/layout/WorkspaceSidebar/FileTreeView.tsx (树视图)
  - apps/web/src/components/editor/CodeEditorPanel.tsx (代码编辑器)
  - apps/web/src/components/layout/WorkspaceSidebar/FileHistoryDialog.tsx (版本历史)
  - apps/web/src/components/diff/DiffViewer.tsx (差异对比)
- 后端路由:
  - apps/backend/app/api/routes/files.py (文件 CRUD)
  - apps/backend/app/api/routes/files_core.py (文件读写、导出)
  - apps/backend/app/api/routes/diff.py (差异对比)
- 关键配置:
  - apps/backend/app/services/file_tree_config.py (editable_extensions 字段)

## agent-chat.md
- 覆盖功能: 对话发起、会话管理、模型选择、富文本聊天、AskUser
- 前端组件:
  - apps/web/src/components/layout/ConversationDock.tsx (对话容器)
  - apps/web/src/components/chat/DockChatView.tsx (聊天视图)
  - apps/web/src/components/chat/InputArea.tsx (输入区)
  - apps/web/src/components/chat/ModelSelector.tsx (模型选择器)
  - apps/web/src/components/AskUserDialog/ (确认弹窗)
- 后端路由:
  - apps/backend/app/api/routes/agent.py (Agent 执行)
  - apps/backend/app/api/routes/sessions.py (会话管理)
  - apps/backend/app/api/routes/ask_user.py (AskUser 响应)
```

### 2. 代码变更触发文档检查

| 变更类型 | 触发条件 | 动作 |
|---------|---------|------|
| 新增前端组件 | 组件对应已有文档覆盖的功能 | 更新对应文档，在映射索引中追加组件路径 |
| 新增 API 端点 | 端点属于已有文档覆盖的域 | 更新 API_REFERENCE.md 和对应功能文档 |
| 修改 UI 交互流程 | 用户可见行为变化 | 更新对应功能文档的操作步骤描述 |
| 新增功能 | 完整的新功能模块 | 创建新文档，在 SYSTEM_USAGE.md 和 README.md 添加索引 |
| 删除功能/API | 功能下线 | 标记文档对应章节为"已废弃"，归档旧描述 |
| 纯重构 | 无行为变化 | 不触发文档更新 |
| 修改配置文件默认值 | 默认值变化 | 更新文档中的配置示例和默认值说明 |

**与提交流程的衔接**：上述检查不是独立步骤，而是嵌入到 `github-project-management` skill 的"提交前文档与 skill 同步检查"中。代码改动完成后、commit 之前，按该检查清单确认文档同步状态，未同步的文档不得提交。

### 3. 文档编写时自动建立映射

创建新文档时，同时建立映射索引：

1. 写文档内容
2. 确认文档覆盖的功能点
3. 列出涉及的前端组件路径和后端路由文件
4. 在 `DOC_CODE_MAP.md` 中添加映射条目
5. 在 `SYSTEM_USAGE.md` 中添加索引链接

### 4. 过期检测机制

定期审计时，按以下优先级检测：

**高优先级**（阻塞性不一致）：
- 文档描述的操作步骤与实际 UI 不一致（入口变了、按钮名变了、流程变了）
- 文档引用的 API 端点不存在或参数不匹配
- 文档中的端口号、环境变量名与配置不一致

**中优先级**（陈旧但不阻塞）：
- 文档描述的功能仍存在但细节过时
- 文档列表不完整（新增的子功能未列入）

**低优先级**（可延后）：
- 文档版本号未更新
- "当前版本"标注过期

检测方法：
1. 读取 `DOC_CODE_MAP.md` 获取映射关系
2. 对每个文档，检查其对应的前端组件和后端路由是否仍然存在
3. 对比文档描述和代码实际行为
4. 生成不一致报告

## 执行流程

### 场景 A：代码变更后同步文档

步骤：
1. 读取 `DOC_CODE_MAP.md`，找到变更文件对应的文档
2. 读取对应文档当前内容
3. 对比代码实际行为，确定需要修改的章节
4. 更新文档
5. 如有新增/删除的代码文件，更新映射索引

### 场景 B：全量审计

步骤：
1. 读取 `DOC_CODE_MAP.md`
2. 并行启动 explore Agent，每个 Agent 负责 5-8 个文档
3. 对每个文档：验证组件路径存在、API 端点匹配、配置默认值一致
4. 生成审计报告（按严重程度分级）
5. 用户确认后批量修复

### 场景 C：新建功能文档

步骤：
1. 确认功能的前端组件和后端路由
2. 按 `gen-docs` 模式 A 写文档
3. 在 `DOC_CODE_MAP.md` 添加映射条目
4. 在 `SYSTEM_USAGE.md` 和 README.md 添加索引

## 与其他 Skill 的关系

| Skill | 分工 |
|-------|------|
| `gen-docs` | 文档编写、更新、归档、双语同步、7 种不一致检测 |
| `doc-sync`（本 skill） | 文档-代码映射索引、变更触发规则、过期检测流程 |
| `aiasys-product-requirements` | 需求文档与 PRD 对齐 |

`gen-docs` 的审计模式（模式 E）偏"检测"，本 skill 偏"索引 + 触发规则"。两者配合使用：本 skill 提供"改了什么代码就该查哪些文档"的映射，`gen-docs` 执行具体的审计检测和修复。

## 维护约束

1. 新增功能文档时，必须在 `DOC_CODE_MAP.md` 中注册映射
2. 删除或重命名代码文件时，必须同步更新映射索引
3. 每次代码变更涉及用户可见行为时，按触发规则检查是否需要更新文档
4. 映射索引本身也是文档，同样受 `gen-docs` 审计覆盖
5. 文档同步检查是提交前置条件的一部分，未同步的文档变更不得进入 commit（见 `github-project-management` skill "提交前文档与 skill 同步检查"）
# Workspace 与会话存储现状

本文档说明 `apps/backend` 当前真实使用的工作区、会话副产物和兼容旧结构的逻辑，而不是历史理想化结构。

## 总体结构

当前会话工作目录仍然以用户和会话分层：

```text
workspaces/
├── {user_id}/
│   ├── .preferences/
│   │   ├── .enabled
│   │   └── PREFERENCES.md
│   ├── .data_sources/
│   │   └── <user library files>
│   └── {session_id}/
│       ├── metadata.json
│       ├── history.json
│       ├── file_snapshots.json
│       ├── .mcp_session.json
│       ├── .cleanup_marker
│       ├── report.md
│       ├── charts/figure.png
│       ├── .preference.md
│       ├── workspace/                  # legacy 兼容目录，存在时会迁移 / 回退读取
│       └── .session/
│           └── {session_id}/
│               ├── context.jsonl
│               └── display_history.jsonl
```

需要特别注意：

1. 当前“逻辑工作区”与“物理目录”不是完全一比一。
2. 新文件的主存放位置已经是会话根目录 `workspaces/{user_id}/{session_id}/`。
3. 旧结构里的 `workspace/` 子目录仍被兼容，但当前真实任务偏好和新文件都应落在会话根目录。
4. `.session/` 是 SDK 内部状态目录，不属于前端工作区可见文件集。

## 当前各层职责

### 用户级目录

`workspaces/{user_id}/` 下目前至少承载三类内容：

| 路径 | 职责 |
| --- | --- |
| `.preferences/` | 全局偏好记忆，面向未来新会话初始化 |
| `.data_sources/` | 用户级数据源库，不绑定单个会话 |
| `{session_id}/` | 单个会话的工作区、历史和副产物 |

### 会话级目录

`workspaces/{user_id}/{session_id}/` 当前同时承担三种角色：

1. Agent 沙盒挂载根目录，容器内映射到 `/workspace/`
2. 会话元数据与历史副产物存储目录
3. 前端工作区逻辑根目录

换句话说，前端今天看到的“工作区”，不是单独挂在 `workspace/` 子目录上的一块新空间，而是会话根目录的逻辑投影。

## 关键文件说明

| 文件 | 当前用途 | 是否在工作区列表中展示 |
| --- | --- | --- |
| `metadata.json` | 会话标题、创建时间、消息数、环境信息 | 否 |
| `history.json` | 简单结构化历史，供会话管理使用 | 否 |
| `file_snapshots.json` | 文件列表快照，供历史回顾 | 否 |
| `.mcp_session.json` | 会话级 MCP 配置 | 否 |
| `.cleanup_marker` | 空草稿快速清理标记 | 否 |
| `.session/{session_id}/context.jsonl` | SDK 原始历史 | 否 |
| `.session/{session_id}/display_history.jsonl` | UI 展示补充历史 | 否 |
| `.preference.md` | 当前任务偏好文件（容器内映射为 `/workspace/.preference.md`） | 是 |
| `workspace/*` | legacy 历史文件目录，仅兼容回退读取 | 视同逻辑根目录内容 |
| 其他普通文件 | 用户上传或 Agent 生成结果 | 是 |

## 逻辑工作区如何解析

当前 `files.py` 的逻辑不是“只看一个目录”，而是做兼容式合并：

1. 先遍历会话根目录。
2. 再回退遍历旧的 `workspace/` 子目录。
3. 输出时统一按“逻辑根目录”展示。
4. 如果同名文件同时存在，会话根目录优先。

这也是为什么：

- 当前 `.preference.md` 物理上就在会话根目录
- 即使 legacy `workspace/` 中还残留历史文件，前端工作区也仍按逻辑根目录展示

## 文件可见性和安全边界

当前文件 API 对工作区有几层明确限制：

1. 屏蔽 `.session` 目录及其全部内容。
2. 屏蔽 `.sessions` 目录及其全部内容。
3. 屏蔽根级 `metadata.json`、`history.json`、`file_snapshots.json` 和 `.cleanup_marker`。
4. 所有相对路径都要经过规范化，不允许绝对路径和 `..` 跳目录。

对应结果是：

- 前端不会直接看到内部会话状态文件。
- 工作区树像普通文件树一样展示，`.` 开头的普通文件和目录默认可见，例如 `.preference.md`、`.vscode/`、`.env.example`。
- 工作区路径现在支持子目录，但仍有严格的越界校验。

## 当前上传、读取与导出路径

### 上传

`POST /api/files/upload/{user_id}/{session_id}` 现在默认把上传文件保存到会话根目录：

```text
workspaces/{user_id}/{session_id}/{filename}
```

这与容器内路径的关系是：

```text
宿主机: workspaces/{user_id}/{session_id}/
容器内: /workspace/
```

因此新上传文件在容器中通常直接对应 `/workspace/{filename}`。

### 读取

后端解析工作区路径时，会按下面顺序查找：

1. 会话根目录
2. 旧的 `workspace/` 子目录

这保证了历史文件迁移前后，前端仍可以用统一的逻辑路径访问。

### 导出

当前与工作区最相关的导出接口有两个：

- `GET /api/files/export/{user_id}/{session_id}`
  导出整个逻辑工作区 ZIP
- `GET /api/files/export-document/{user_id}/{session_id}/{filename:path}?format=md|docx|pdf`
  导出单个 Markdown 文件，支持 Pandoc 转换

## 偏好记忆在工作区中的位置

当前偏好设计是“两级”：

| 级别 | 物理位置 | 作用 |
| --- | --- | --- |
| 全局偏好 | `workspaces/{user_id}/.preferences/PREFERENCES.md` | 影响未来新会话初始化 |
| 任务偏好 | `workspaces/{user_id}/{session_id}/.preference.md` | 绑定当前会话，容器内映射为 `/workspace/.preference.md` |

当前实现细节：

1. 全局偏好存储在 user memory 中，通过 `/api/preferences` 接口读写。
2. 会话级偏好由会话元数据直接承载，不再单独维护任务偏好文件。

## 会话删除和草稿清理

当前会话目录不仅会被“手动删除”，也会参与草稿清理生命周期：

### 删除会话

`DELETE /api/sessions/{user_id}/{session_id}` 的当前顺序是：

1. 尝试中断活跃 Agent 会话
2. 停止关联容器
3. 清理运行环境实例绑定
4. 删除整个会话目录

### 草稿清理

空草稿会话还会使用：

- `/api/sessions/available-draft`
- `/api/sessions/cleanup-drafts`
- `/api/sessions/mark-draft-for-cleanup`

`.cleanup_marker` 只是快速清理辅助文件，不属于工作区业务文件。

## 当前不应再写进文档的旧说法

下面这些说法已经不准确：

- “工作文件全部存放在 `{session_id}/workspace/`”
- “任务偏好物理上仍固定在 `workspace/.preference.md`”
- “工作区列表直接映射物理目录，不做兼容合并”
- “`.preference.md` 只有首次执行后才会出现”
- “删除会话只删元数据，不影响容器与运行环境绑定”

## 推荐源码入口

当你要确认某个工作区行为时，优先看这些文件：

- `app/api/routes/files.py`
- `app/api/routes/sessions.py`
- `app/services/session_manager.py`
- `app/services/agent_service.py`
- `app/preferences/manager.py`

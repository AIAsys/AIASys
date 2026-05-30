# 任务运行态状态与设置读模型契约

状态: 主线专题
更新时间: 2026-04-22
适用版本: v0.3.9 当前主线

---

## 1. 文档目标

本文档用于统一 AIASys 当前任务工作层的两个核心读模型：

1. 运行态状态快照
2. 设置工作台聚合读模型

它回答的是：

- 前端任务页最少需要拿到哪些状态字段
- 设置工作台应该如何复用这些状态字段
- 哪些字段属于主线，哪些字段只属于兼容区

---

## 2. 核心原则

### 2.1 当前代码还没有统一成单一读模型

当前前端主线实际使用的是两组读链路：

1. 当前分支状态
   - 主要来自 `GET /api/sessions/status/{session_id}`
2. 工作区设置聚合
   - 前端在 `WorkspaceSettingsDialog` 里继续拉取工作区详情、资源挂载、资源验证和能力目录

因此文档必须先承认一个事实：

- 当前代码仍然是“分支状态主接口 + 前端聚合补充数据”
- 还没有一个已经落地的统一 `settings workbench` 后端读模型

### 2.2 任务工作层键当前仍使用 `session_id`

文档里统一用“任务工作层”表达，但当前代码实现层大多数接口仍使用 `session_id` 作为键。

### 2.3 compatibility 字段必须显式分区

当前仍存在但不再是主线的字段，例如：

- `sandbox_mode`
- `recovery_policy`
- `manual replay` 相关状态

都不应混进主线状态区。

---

## 3. 当前分支运行态状态快照

### 3.1 当前主入口

当前主入口仍然是：

- `GET /api/sessions/status/{session_id}`

这个接口当前已经返回的主线字段包括：

- `session_id`
- `title`
- `status`
- `message_count`
- `execution_record_count`
- `last_execution_status`
- `last_execution_record_id`
- `runtime_summary`
- `last_runtime_state`
- `can_edit_agent_config_now`
- `pending_agent_config_version`
- `applied_agent_config_version`
- `pending_capability_snapshot_version`
- `applied_capability_snapshot_version`
- `pending_memory_snapshot_version`
- `applied_memory_snapshot_version`
- `memory_effect`
- `workspace_capability_summary`
- `mode`
- `enabled_builtin_packs`
- `execution_policy`

```python
class SessionStatusInfo(TypedDict):
    session_id: str
    title: str | None
    status: str | None
    message_count: int | None
    execution_record_count: int | None
    last_execution_status: str | None
    last_execution_record_id: str | None
    runtime_summary: dict | None
    last_runtime_state: str | None
    can_edit_agent_config_now: bool | None
    pending_agent_config_version: str | None
    applied_agent_config_version: str | None
    pending_capability_snapshot_version: str | None
    applied_capability_snapshot_version: str | None
    pending_memory_snapshot_version: str | None
    applied_memory_snapshot_version: str | None
    memory_effect: str | None
    workspace_capability_summary: dict | None
    mode: str | None
    enabled_builtin_packs: list[str] | None
    execution_policy: dict | None
```

### 3.2 字段语义

#### Agent 配置状态

用于表达：

- 当前保存配置与已应用配置是否一致
- 当前是否允许编辑 Agent 配置

#### 运行态状态

用于表达：

- 当前 runtime 是否存在
- 是否需要刷新
- 为什么需要刷新

#### 执行证据摘要

用于表达：

- 有没有执行证据
- 最近一次执行情况如何

#### compatibility

当前实现里还没有单独的 `compat` 分区对象，兼容字段仍直接和主线字段一起返回。

因此这篇文档里如果还要继续谈 `compat`，必须把它明确标成“建议的后续收口方向”，不能写成已经落地。

---

## 4. 当前工作区设置聚合读模型

### 4.1 当前代码里的真实来源

当前 `WorkspaceSettingsDialog` 并不是调用一个统一的 `settings workbench` 接口，而是前端自己聚合这些来源：

- `workspaceSummary` 首帧种子
- `GET /api/workspaces/{workspace_id}`
- `GET /api/workspaces/{workspace_id}/resource-verification`
- `GET /api/workspaces/{workspace_id}/database-connectors`
- `GET /api/workspaces/{workspace_id}/knowledge-bases`
- `GET /api/workspaces/{workspace_id}/knowledge-graphs`
- capability registry 相关接口
- 当前分支的 `sessionStatus`

```python
class WorkspaceSettingsDialogReadModel(TypedDict):
    workspace_summary_seed: dict | None
    workspace_detail: dict | None
    session_status: dict | None
    resource_verification: dict | None
    database_mounts: dict | None
    knowledge_base_mounts: dict | None
    knowledge_graph_mounts: dict | None
    capability_registry: dict | None
```

### 4.2 关键约束

#### 1. 当前分支同步状态已经直接复用 `sessionStatus`

工作区设置和当前分支设置里凡是“待生效 / 已对齐 / 下次执行生效”的判断，当前都应尽量直接取自 `sessionStatus`，不要再发明第三套命名。

#### 2. 当前工作区资源上下文已经独立

数据库、知识库、知识图谱和资源验证当前已经单独拉取，说明这层语义在当前代码里就是独立聚合区，不属于单纯的通用设置继承层。

#### 3. 统一后端 workbench 仍是后续方向

如果后续要继续收口，可以把这套前端聚合下沉成后端统一 workbench 接口；但在当前阶段，这还不是代码真相。

---

## 5. compat 约束

### 5.1 可放入 compat 的字段

例如：

- `sandbox_mode`
- `recovery_policy`
- `rebuild_status`
- `last_replay_run_id`
- `last_replayed_sequences`

### 5.2 不可放入 compat 的字段

下面这些属于当前主线，不能被丢进 compat：

- `pending_agent_config_version`
- `applied_agent_config_version`
- `runtime_state`
- `runtime_refresh_required`
- `execution_record_count`

---

## 6. 前端消费要求

### 6.1 任务页

任务页优先消费：

- `TaskRuntimeStatusSnapshot`

用于展示：

- 当前任务状态
- 当前运行态状态
- 是否待下次执行生效

### 6.2 设置工作台

设置工作台消费：

- `SettingsWorkbenchResponse`

并直接复用其中的 `sync_state`。

### 6.3 任务配置弹窗

任务配置弹窗至少要能同时看到：

- 当前保存配置
- 当前主线同步状态
- 本轮实际执行快照摘要

---

## 7. 当前接口真相与后续方向

### 7.1 当前已经存在的主入口

- `GET /api/sessions/status/{session_id}`
- `GET /api/workspaces/{workspace_id}`
- `GET /api/workspaces/{workspace_id}/resource-verification`
- `GET /api/workspaces/{workspace_id}/database-connectors`
- `GET /api/workspaces/{workspace_id}/knowledge-bases`
- `GET /api/workspaces/{workspace_id}/knowledge-graphs`

### 7.2 当前还不存在的统一入口

下面这些仍然属于后续建议，不是现有代码真相：

- `GET /api/settings/workbench?session_id=...`
- 单独的统一 runtime lifecycle 读模型接口

---

## 8. 当前建议结论

当前主线应统一以下口径：

1. 当前分支状态主真相仍然是 `session status` 接口。
2. 工作区设置当前仍是前端聚合模型，不是统一后端 workbench。
3. 资源池摘要当前已经独立拉取，文档应按独立聚合区书写。
4. 如果后续要继续统一读模型，应在文档里明确标成“下一步收口”，不要把建议接口写成现有接口。

# 任务运行态状态与设置读模型契约

状态: 主线专题
更新时间: 2026-04-11
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

### 2.1 先统一读模型，再扩展写接口

只要运行态状态和设置读模型没有统一，前端就会继续自己拼字段，导致：

- “已保存待生效”判断不一致
- “需刷新运行态”提示不一致
- compatibility 字段到处泄漏

### 2.2 任务工作层键当前仍使用 `session_id`

文档里统一用“任务工作层”表达，但当前代码实现层大多数接口仍使用 `session_id` 作为键。

### 2.3 compatibility 字段必须显式分区

当前仍存在但不再是主线的字段，例如：

- `sandbox_mode`
- `recovery_policy`
- `manual replay` 相关状态

都不应混进主线状态区。

---

## 3. 任务运行态状态快照

### 3.1 最小字段集

```python
class TaskRuntimeStatusSnapshot(TypedDict):
    task_key: str                    # 当前实现先使用 session_id
    workspace_id: str | None
    scene: Literal["analysis", "research"]

    status: Literal["draft", "active", "completed"]
    message_count: int

    # Agent 配置状态
    agent_config_effect: Literal["next_run_only"]
    can_edit_agent_config_now: bool
    agent_config_lock_reason: str | None
    applied_agent_config_version: str | None
    pending_agent_config_version: str | None
    applied_agent_config_snapshot: dict | None
    pending_agent_config_snapshot: dict | None

    # 运行态状态
    runtime_state: str | None
    runtime_refresh_required: bool
    runtime_refresh_reasons: list[str]

    # 执行证据摘要
    has_execution_journal: bool
    execution_record_count: int
    last_execution_status: str | None
    last_execution_record_id: str | None

    # compatibility
    compat: dict[str, object]
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

用于表达仍需兼容但不再是主线的字段。

---

## 4. 设置工作台聚合读模型

### 4.1 最小结构

```python
class SettingsWorkbenchResponse(TypedDict):
    task_key: str | None
    workspace_id: str | None
    scene: str

    layers: dict
    resource_context: dict
    groups: list[dict]

    sync_state: SettingsSyncState
    compat: dict[str, object]

class SettingsSyncState(TypedDict):
    agent_config_effect: Literal["next_run_only"]
    applied_agent_config_version: str | None
    pending_agent_config_version: str | None
    runtime_state: str | None
    runtime_refresh_required: bool
    runtime_refresh_reasons: list[str]
```

### 4.2 关键约束

#### 1. `sync_state` 必须直接复用任务运行态状态快照

不要再让设置工作台自己发明另一套字段名。

#### 2. `layers` 只表达三层

- 系统目录层
- 用户默认层
- 任务工作层

#### 3. `resource_context` 单独表达 workspace 资源池

它不属于通用设置继承层。

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

## 7. 接口建议

### 7.1 当前主入口

在当前实现阶段，建议继续以：

- `GET /api/sessions/status/{session_id}`

作为任务运行态状态快照主入口。

### 7.2 设置工作台入口

建议新增：

- `GET /api/settings/workbench?session_id=...`

### 7.3 后续独立生命周期入口

如果后续需要把状态读模型进一步独立，可再新增：

- `GET /api/sessions/{user_id}/{session_id}/runtime-lifecycle`

但在当前阶段，不要为了“更优雅”先拆散已有 status 入口。

---

## 8. 当前建议结论

当前主线应统一以下口径：

1. 任务运行态状态快照和设置工作台聚合读模型必须共用同一套同步状态字段。
2. compatibility 字段必须显式分区。
3. `workspace` 资源池摘要单独放在 `resource_context`，不混进通用设置层。
4. 当前实现阶段先复用已有 `session status` 主入口，再逐步补 `settings/workbench`。

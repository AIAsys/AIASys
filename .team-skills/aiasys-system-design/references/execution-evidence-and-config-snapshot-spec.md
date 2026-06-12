# 执行证据与配置快照规范

状态: 主线专题
更新时间: 2026-04-04
适用版本: v0.3.9 当前主线

---

## 1. 文档目标

本文档用于收敛 AIASys 当前“执行证据层”的最小规范。

它回答的是：

- 一轮执行结束后，系统最少应记录哪些证据
- “当前保存配置”与“本轮实际执行配置”如何区分
- 配置快照应该包含哪些字段
- 前端任务配置与执行记录页应如何理解这些字段

---

## 2. 核心原则

### 2.1 执行证据回答的是“这一轮实际用了什么”

执行证据层只回答：

- 这一轮执行实际采用了什么 Agent 配置
- 这一轮执行实际加载了哪些 Skill / MCP / Tool
- 这一轮执行实际跑在哪个 runtime 上

### 2.2 当前保存配置与本轮执行快照必须分离

任务工作区当前保存的配置，可能已经被修改，但尚未应用到当前这一轮执行。

因此必须区分：

- `pending` 或当前保存配置
- `applied` 或本轮实际执行配置快照

### 2.3 证据要可追溯，不要求一开始就极度复杂

当前阶段优先先保证：

- 每轮执行都有最小证据
- 快照可被前端读取和对照
- 后续导出时能复原“当时怎么跑的”

---

## 3. 一轮执行最少应记录的证据

### 3.1 执行元信息

- `execution_id`
- `session_id`
- `workspace_id`
- `started_at`
- `ended_at`
- `status`

### 3.2 Agent 配置快照

- `agent_profile_id`
- `prompt_version`
- `prompt_override_hash`
- `enabled_tools`
- `subagent_policy`

### 3.3 能力配置快照

- `skill_packages`
- `mcp_servers`
- `capability_ids`

### 3.4 runtime 快照

- `runtime_kind`
- `env_id`
- `sandbox_mode`
- `runtime_instance_id`

### 3.5 输出与工具证据

- 执行 journal 引用
- 关键工具调用摘要
- 错误摘要
- 产物引用

---

## 4. 配置快照字段建议

### 4.1 Agent 快照

最少字段建议：

```text
agent_snapshot_id
agent_profile_id
prompt_version
prompt_override_hash
enabled_tools[]
subagent_enabled
subagent_strategy
```

### 4.2 能力快照

最少字段建议：

```text
capability_snapshot_id
skill_packages[]
mcp_servers[]
capability_ids[]
```

### 4.3 runtime 快照

最少字段建议：

```text
runtime_snapshot_id
runtime_kind
env_id
sandbox_mode
runtime_instance_id
```

---

## 5. 后端投影建议

当前后端对前端至少应投影以下字段：

- `applied_agent_config_version`
- `pending_agent_config_version`
- `applied_capability_snapshot_version`
- `pending_capability_snapshot_version`
- `last_execution_id`
- `last_runtime_state`

---

## 6. 前端展示要求

### 6.1 任务配置弹窗

任务配置弹窗中需要至少同时展示两层事实：

- 当前保存配置
- 本轮实际执行配置快照

### 6.2 执行记录面板

执行记录面板应能展示：

- 本轮运行环境
- 本轮 Agent 版本
- 本轮能力快照
- 关键工具调用

### 6.3 不要把目录层和证据层混在一起

以下对象不应直接拿来充当执行证据：

- Skill 市场条目
- MCP 市场条目
- 用户默认配置

---

## 7. 文件落点建议

当前建议把执行证据与快照引用收口到：

```text
.session/
├── config/
├── executions/
└── runtime/
```

---

## 8. 当前建议结论

当前主线应统一以下口径：

1. 执行证据层回答“这一轮实际用了什么”。
2. 当前保存配置与本轮实际执行配置必须分离。
3. Agent、能力、runtime 都应有最小快照字段。
4. 任务配置弹窗和执行记录面板都必须能看到快照差异。

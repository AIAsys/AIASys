# 运行态刷新与重建契约

状态: 主线专题
更新时间: 2026-04-04
适用版本: v0.3.9 当前主线

---

## 1. 文档目标

本文档用于明确 AIASys 当前任务工作区在配置变更后的运行态刷新与重建规则。

它回答的是：

- 哪些变更会要求 runtime 刷新
- 当前 turn 进行中时系统应如何处理
- 什么时候允许继续使用旧 runtime
- 什么时候必须重建 runtime
- 重建时哪些内容保留，哪些内容重置

---

## 2. 核心结论

### 2.1 配置可保存，不等于运行中热更新

当前主线统一口径：

- Agent 配置变更
- Skill 包变更
- MCP 配置变更
- 运行环境关键变更

都允许先保存到当前任务工作区。

但默认不承诺对当前正在执行的 turn 做热更新。

### 2.2 当前任务状态与 runtime 状态分层

任务工作区主状态和 runtime 状态必须分离。

因此：

- 当前任务可以仍是 `active`
- 同时 runtime 状态可以是 `refresh_required`

### 2.3 runtime 重建不等于新建任务

runtime 重建只替换当前任务背后的活跃执行实例。

它不应清空以下内容：

- 历史消息
- 工作区文件
- 附件
- Skill 目录包
- MCP yaml
- 执行证据历史

---

## 3. 哪些变更触发 `refresh_required`

以下变更默认会把当前任务标记为 `refresh_required`：

### 3.1 Agent 配置变更

例如：

- Agent profile 变更
- 提示词版本变更
- 提示词覆盖变更
- 工具启用列表变更
- 子 Agent 策略变更

### 3.2 Skill 包变更

例如：

- 导入新 Skill
- 删除 Skill
- 替换 Skill 包内容

### 3.3 MCP 配置变更

例如：

- `mcp.yaml` 内容变更
- 增删 MCP server
- 更新认证字段
- 调整启用状态

### 3.4 运行环境关键变更

例如：

- 本地执行配置切换
- 工作区 `uv` 环境锁文件、解释器版本或依赖集变更
- 会影响下一次执行重建的 runtime 配置变更

当前主线建议进一步明确：

- 工作区默认 Python 环境以 `uv` 物料为准
- `pyproject.toml`、`uv.lock`、`.python-version` 或 `.venv` 重建都会触发 `refresh_required`
- 运行中不承诺热更新已启动解释器的依赖图

---

## 4. 当前 turn 进行中的处理规则

### 4.1 不强制打断当前 turn

如果当前 turn 正在执行，用户修改了任务配置：

1. 先保存工作区配置
2. 把 runtime 状态标记为 `refresh_required`
3. 当前 turn 继续跑完
4. 前端明确提示“已保存，下次执行生效”

### 4.2 只有显式停止或灾难性错误才中断

以下情况可以提前中断当前 runtime：

- 用户手动停止
- runtime 本身崩溃
- 环境切换要求立即销毁旧实例且当前没有可继续执行价值

---

## 5. 下一次执行前的重建规则

当用户发起下一次执行，且任务 runtime 状态为 `refresh_required` 时，系统应执行：

1. 检查当前任务工作区配置是否可加载
2. 销毁旧 runtime 实例
3. 重新创建同一任务的 runtime
4. 从当前工作区读取最新配置与 `uv` 环境物料
5. 记录本轮执行实际采用的配置快照
6. 将 runtime 状态切回 `ready` 或 `busy`

如果重建失败：

- 保留任务工作区本体
- 保留配置文件和历史证据
- runtime 状态进入 `missing` 或错误态
- 前端展示明确失败原因

---

## 6. 保留与重置边界

### 6.1 重建后必须保留

- 任务工作区 ID
- 历史消息
- 工作区文件与附件
- Skill 目录包
- MCP 配置文件
- 执行记录历史
- 配置版本历史

### 6.2 重建后允许重置

- 活跃 runtime 进程
- 进程内内存态工具缓存
- 当前挂起的非持久运行时对象
- 上一实例的临时连接
- 旧 `.venv` 对应的解释器进程与内存态

---

## 7. 后端状态投影要求

后端至少应投影以下字段给前端：

- `runtime_state`
- `runtime_refresh_required`
- `can_edit_agent_config_now`
- `agent_config_effect`
- `applied_agent_config_version`
- `pending_agent_config_version`

如果后续扩展 Skill / MCP，也应增加同类字段，例如：

- `applied_capability_snapshot_version`
- `pending_capability_snapshot_version`

---

## 8. 前端提示要求

前端对用户只需要表达这些事实：

- 已保存，下次执行生效
- 当前运行中，稍后会刷新运行态
- 当前环境需要重建
- 重建失败，请检查配置

---

## 9. 当前建议结论

当前主线应统一采用“工作区可编辑，runtime 软重建”的模型：

1. 修改先保存到工作区。
2. 当前 turn 默认不热更新。
3. 系统把任务标记为 `refresh_required`。
4. 下一次执行前按工作区最新配置和 `uv` 环境物料重建 runtime。
5. 任务历史、工作区文件与执行证据全部保留。

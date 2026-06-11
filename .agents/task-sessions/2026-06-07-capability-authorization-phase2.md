# Task Session: 能力授权 Phase 2 — 配置化 + Agent 测试覆盖

Date: 2026-06-07
Parent: `.agents/task-sessions/2026-06-07-capability-authorization-modes.md`

## Goal

完成能力授权 Phase 2 的剩余工作：
1. 主会话创建不再硬编码 `yolo=True`，改为从配置层读取 `authorization_mode`
2. Agent 测试框架增加审批自动响应能力
3. 补充 Hardline BLOCK 测试 case（无需改模式即可验证）
4. 补充 SMART ASK / AUTO DENY 测试 case（需配置化完成后验证）

## Context

Phase 1 已完成：
- `CapabilityAuthorizationService` + 11 策略链已落地
- 77+ 单元测试通过
- 工具风险元数据、子 Agent 授权继承、Skill 安全元数据扩展已完成

Phase 1 遗留问题：
- `mixins/session.py:362` 仍硬编码 `yolo=True`，所有主会话实际运行在 FULL_AUTO
- SMART / MANUAL / AUTO 三种模式代码存在但用户无法实际使用
- Agent 测试框架未覆盖审批事件（`approval_required` / `capability_confirmation`）
- 没有集成测试验证 BLOCK / DENY / ASK 决策在实际 Agent 执行链路中的效果

## 设计约束

- 配置优先级：会话配置 > 当前工作区配置 > 全局工作区配置 > 系统默认（`smart`）
- `yolo` 作为兼容标记保留，但不再硬编码。新逻辑：`authorization_mode` 显式配置优先，`yolo=True` 仅作为旧数据兼容映射到 `full_auto`
- 不改动前端设置入口（Phase 2 范围外），测试通过 API 直接修改 session config 来切换模式
- 审批自动响应和 AskUser 自动响应保持独立（事件类型、API 路径、超时语义不同）

## 改动范围

### 后端

- `apps/backend/app/services/agent/mixins/session.py`
  - `RuntimeSessionCreateSpec` 构造时从配置层读取 `authorization_mode`
  - 移除硬编码 `yolo=True`

- `apps/backend/app/services/agent/runtime_backends/aiasys/session_stream.py`
  - 确认 `yolo` 兼容映射逻辑正确（已有，需验证）

### 测试框架

- `design-draft/agent-test-cases/run_case.py`
  - 新增审批事件检测：`approval_required`、`capability_confirmation`
  - 新增审批自动响应：调用 `POST /api/{user_id}/{session_id}/approvals/{tool_call_id}`
  - 新增 `get_pending_approvals()` 轮询辅助函数
  - 新增 `auto_resolve_approval_by_session()` 后台线程

### 测试 Case

- `cases/auth-001-block-hardline/` — FULL_AUTO 下 `rm -rf` 被 BLOCK
- `cases/auth-002-block-credential/` — FULL_AUTO 下 `curl $SECRET` 被 BLOCK
- `cases/auth-003-smart-ask-shell/` — SMART 下未知 Shell 触发 ASK，确认后执行
- `cases/auth-004-auto-deny/` — AUTO 下高风险操作被 DENY

## 验收标准

- [ ] 主会话 `authorization_mode` 可从 session config / workspace config 读取
- [ ] SMART 模式下未知 Shell 触发 `approval_required` 事件
- [ ] 测试框架自动响应审批后工具继续执行
- [ ] AUTO 模式下高风险工具直接返回 `is_error=True`，不触发审批事件
- [ ] Hardline 命令在 FULL_AUTO 下仍被 BLOCK
- [ ] 全量回归测试无 regression

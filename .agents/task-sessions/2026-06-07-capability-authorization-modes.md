# Task Session: capability authorization modes

Date: 2026-06-07

## Goal

评估 AIASys 是否需要统一授权模式，覆盖工具、Skill、MCP、运行环境和自动化能力，并明确默认档位、全自动边界和 AskUser 的职责。

## Context

用户指出授权不应该只看 Skill，工具也需要考虑。用户同时要求参考：

- Codex
- Copilot
- Kimi Code
- Hermes Agent
- Claude Code 泄露参考目录：`/home/ke/projects/easy-agents/参考资料/claude-code-系列/claude-leaked-files`

## Findings

- AIASys 当前 `AskUser` 可用，但运行时审批拦截仍是预留。
- AIASys 当前 `tool_search` 搜索后激活已有工具 schema，不等于安装或执行副作用。
- Skill 搜索和启用已经分离，`EnableSkill` 是持久化动作，应进入授权判断。
- Hermes 不是没有授权，它把 `clarify` 和危险命令 approval 分开，并保留 secret redaction。
- Claude Code 参考里每次工具调用都经过 `canUseTool` 和 `ToolPermissionContext`。
- Kimi Code 支持会话级批准和 YOLO/Auto。
- Codex 支持 approval policy 和 granular approval，其中包含 sandbox 与 skill 类别。

## Decision

- 授权对象统一定义为“能力调用”，包括工具、Skill、MCP、运行环境、AutoTask、子 Agent、全局写入和外部系统。
- 不依赖 Agent 主动调用 `AskUser` 作为唯一安全边界。
- `AskUser` 保留为 Agent 主动提问工具。
- 高风险能力确认由后端 `CapabilityAuthorizationService` 触发，前端可复用 AskUser 队列和组件，但事件类型要分离。
- 默认模式建议为 `smart`，不默认 `full_auto`。
- `full_auto` 只表示不弹交互确认，不关闭 denylist、secret protection、memory security scan、路径边界、外部系统边界和预算限制。

## Files

- Added: `design-draft/design/design-thinking/2026-06-07-能力授权模式可行性评估.md`
- Updated: `design-draft/design/design-thinking/38-六大框架审批模型对AIASys的启发与整合方案.md`
- Updated: `design-draft/design/design-thinking/48-AskUser用户确认机制跨框架对比与AIASys改进方案.md`

## Implementation (Phase 1) — Completed

### 新增文件

- `apps/backend/app/services/agent/capability_authorization.py`
  - `CapabilityAuthorizationService`：统一授权决策服务
  - `CapabilityAuthorizationRequest/Result`：请求/结果模型
  - `AuthorizationMode`：manual / smart / auto / full_auto
  - `AuthorizationDecision`：allow / ask / deny / block
  - `RiskLevel`：readonly / low / medium / high / critical
  - Shell 命令分类器（安全/破坏性/未知）
  - 按工具类型的专门决策：Shell、WriteFile、EnableSkill、MCP、EnvVar、AutoTask、RuntimeEnvironment、SubAgent

- `apps/backend/tests/test_capability_authorization.py`
  - 77 个单元测试，覆盖所有授权档位、风险等级、Shell 分类、工具场景

### 修改文件

- `apps/backend/app/core/agent_tool.py`
  - `AiasysTool` 新增 `risk_level`、`effect_scope`、`side_effect`、`dangerous` 类变量

- `apps/backend/app/services/agent/runtime_backends/base.py`
  - `RuntimeEventKind` 新增 `"capability_confirmation"`
  - `RuntimeSessionCreateSpec` 新增 `authorization_mode: str = "smart"`，保留 `yolo: bool = False` 兼容

- `apps/backend/app/services/agent/runtime_backends/aiasys/session_stream.py`
  - 工具执行循环接入 `CapabilityAuthorizationService.decide()`
  - 所有工具调用都经过授权判断
  - `allow` 直接执行，`ask` 发送 `approval_required` + `capability_confirmation` 事件，`deny/block` 返回错误
  - `yolo=True` 兼容映射到 `full_auto`

- 工具风险元数据（`risk_level` / `effect_scope` / `side_effect`）
  - `apps/backend/app/agents/tools/shell_tool.py` — Shell: high
  - `apps/backend/app/agents/tools/file_tools_read.py` — ReadFile: readonly
  - `apps/backend/app/agents/tools/file_tools_write.py` — WriteFile/StrReplaceFile: medium
  - `apps/backend/app/agents/tools/file_tools_create.py` — CreateFile: medium
  - `apps/backend/app/agents/tools/skill_tools.py` — ListSkills/LoadSkill/SearchStoreSkills: readonly; EnableSkill: high; DisableSkill: medium
  - `apps/backend/app/agents/tools/mcp_tools.py` — ListMCPServers/SearchMCPMarket: readonly; InstallMCPServer: high
  - `apps/backend/app/agents/tools/env_vars_tool.py` — ListEnvVars/GetEnvVar: readonly; SetEnvVar/DeleteEnvVar: high

### 验证结果

```bash
cd apps/backend && .venv/bin/python -m pytest tests/test_capability_authorization.py -v
# 77 passed

cd apps/backend && .venv/bin/python -m pytest tests/test_agent_config_service.py tests/test_expert_policy_routes.py tests/test_skill_tools.py -v
# 33 passed

cd apps/backend && .venv/bin/python -m pytest tests/test_aiasys_runtime_backend.py -v
# 20 passed
```

## Next Implementation Targets (Phase 2)

- 会话/工作区配置模型中持久化 `authorization_mode`
- 子 Agent 继承主控授权档位（当前子 Agent 创建时传 `yolo=True`，需改为继承）
- 前端确认事件 UI 接入 `capability_confirmation`
- 设置入口提供授权档位切换
- `remembered_grants` 记忆授权实现

## 子 Agent 授权继承（2026-06-07 追加）

方案 A（Kimi Code 式继承）：子 Agent `authorization_mode` 和 `yolo` 直接继承父会话。

### 参考项目结论

- **Kimi Code**：子 Agent 完全继承父权限模式（`child.permission.mode = parent.mode`）
- **Codex**：子 Agent 审批请求转发父会话，但 exec policy 不继承
- **Hermes**：子 Agent 默认 `auto-deny`，不是全自动
- **Claude/Copilot**：无独立子 Agent 权限层

**没有参考项目默认子 Agent 全自动**。行业共识是子 Agent 不应无条件比父宽松。

### 改动

- `app/services/agent/runtime_backends/aiasys/session_tools.py`
  - `_tool_context()` 新增 `"authorization_mode"` 和 `"yolo"` 字段

- `app/services/agent/runtime_backends/aiasys/tools/task_tool.py`
  - 子 Agent `RuntimeSessionCreateSpec` 不再硬编码 `yolo=True`
  - 改为从 `ctx` 读取父会话的 `authorization_mode` 和 `yolo` 并传入

- `apps/backend/tests/test_subagent_inheritance.py`
  - 新增 `TestSubagentAuthorizationInheritance` 类，覆盖：
    - 父 `smart + yolo=False` → 子 `smart + yolo=False`
    - 父 `smart + yolo=True` → 子 `smart + yolo=True`（向后兼容）
  - 新增 `_tool_context()` 包含 authorization_mode/yolo 的断言

### 注意

主会话创建（`session.py`）仍保留 `yolo=True`，这是独立决策。当前行为：
- 主 `yolo` → 子继承 `yolo` → 等价于 full_auto，和改之前一样
- 未来主改为 `smart` → 子自动 `smart`，安全边界不降级

### 验证

```bash
cd apps/backend && .venv/bin/python -m pytest tests/test_subagent_inheritance.py -v
# 27 passed

cd apps/backend && .venv/bin/python -m pytest tests/test_capability_authorization.py tests/test_subagent_inheritance.py tests/test_aiasys_runtime_backend.py tests/test_agent_config_service.py tests/test_expert_policy_routes.py tests/test_skill_tools.py -v
# 161 passed
```

## Skill 安全元数据扩展（2026-06-07 追加）

用户反馈：Skill 的风险不能只看来源（builtin vs external），要看它实际依赖什么工具。一个 "aiasys-xxx-skill" 如果带脚本、会调 Shell、会写文件，风险并不比外部 Skill 低。

### 改动

- `app/skills/models.py`
  - 新增 `SkillSecurityInfo` 模型：`source_trust`、`risk_level`、`has_scripts`、`requires_env`、`writes_workspace`、`writes_global`、`uses_shell`、`uses_network`、`installs_dependencies`、`adds_tools`
  - `SkillInfo` 新增 `security: SkillSecurityInfo` 字段

- `app/skills/skill_discovery.py`
  - `_parse_skill_info` 解析 SKILL.md frontmatter `[security]` 区块
  - 新增 `_infer_skill_security` 保守扫描：检查 scripts/ 目录、可执行文件后缀、依赖声明文件、SKILL.md 中高风险工具关键词
  - 来源为 builtin 时 `source_trust="builtin"`，否则 `"external"`
  - 有脚本/Shell/依赖时自动抬升为 `high`，有 env_fields 时 `medium`，其余 `low`

- `app/services/agent/capability_authorization.py`
  - `CapabilityAuthorizationRequest` 新增 `skill_security: dict[str, Any]`
  - `_decide_skill_activation` 不再按名字前缀判断，改为基于 `skill_security`：
    - `low` + 无脚本/Shell/依赖/global/网络/新增工具 → ALLOW
    - `medium` + 无 Shell/依赖/global/网络 → ALLOW
    - 有脚本、调用 Shell、安装依赖、写 global、使用网络、新增工具 → ASK（带具体原因）
    - 缺少安全元数据 → ASK（保守处理）

- `app/services/agent/runtime_backends/aiasys/session_stream.py`
  - 新增 `_get_skill_security` 方法，EnableSkill/DisableSkill 时查询 SkillManager 获取安全元数据
  - 将安全元数据传入 `CapabilityAuthorizationRequest`

- `tests/test_capability_authorization.py`
  - 新增 4 个 Skill 安全元数据相关测试用例，覆盖 low/medium/high/缺失场景
  - 总计 81 个测试全部通过

# Task Session: Agent 提示词 Skill 引用与专家角色边界修正

<!--
  说明: 这是 AI 任务执行的上下文持久化文件
  用途: 将 AI 的工作记忆从易失上下文转移到持久化文件系统
-->

---

## Metadata

| 字段 | 内容 |
|------|------|
| **任务类型** | bugfix |
| **关联版本** | v0.4.0 |
| **创建时间** | 2026-06-07 |
| **最后更新** | 2026-06-07 |
| **状态** | 已完成 |
| **执行者** | AI |

---

## 1. Goal

修正近期 Agent 提示词和系统 preset 调整后残留的运行时不一致问题，确保主控提示词里的 Skill 名称可加载，专家角色文案与工具权限一致。

成功标准：
- 主控提示词和系统 preset 中引用的内置 Skill 都能被 `SkillManager` 发现并通过 `LoadSkill` 读取
- `coder` 明确是主控授权范围内的可写实现者
- `researcher` / `reviewer` 的工具集与“默认只读”提示词一致，不再带环境写入、Skill 启停等状态修改工具
- 定向后端测试通过

---

## 2. Scope

计划修改：
- `apps/backend/app/agents/local_sandbox_agent_config/general_host_prompt.md`
- `apps/backend/app/services/agent/system_presets.py`
- `apps/backend/tests/test_skill_tools.py`
- `docs/guides/agent/expert-roles.md`
- `apps/backend/app/agents/scenes/analysis/scene.toml`
- `apps/backend/app/agents/local_sandbox_agent_config/subagent_data_analyst_prompt.md`
- `apps/backend/app/agents/tools/skill_tools.py`
- `apps/backend/tests/test_agent_config_service.py`
- `apps/backend/tests/test_expert_policy_routes.py`
- `docs/guides/capabilities/mcp-skill-market.md`

不处理：
- README 和图片素材调整
- 消息内容、图片持久化相关脏改动
- Memory 双注入问题

---

## 3. Findings

- `aiasys-markdown-output-guide` / `aiasys-hosting-guide` 是无效短名，实际内置目录名为 `aiasys-markdown-output-guide-skill` / `aiasys-hosting-guide-skill`。
- `coder` 的工具集包含 `WriteFile` / `StrReplaceFile` / `Shell`，但 preset 文案和权限标签仍写成只读。
- `researcher` / `reviewer` 提示词写“默认只读”，但工具集里仍包含环境注册、环境变量写入、Skill 启停等状态修改工具。

---

## 4. Plan

- [x] 修正主控 Skill 名称
- [x] 补充 Skill 引用回归测试
- [x] 校准 `coder` 角色文案与权限标签
- [x] 收窄 `researcher` / `reviewer` 工具集
- [x] 同步专家文档与场景描述
- [x] 运行定向测试

---

## 5. Validation

已执行：

```bash
cd apps/backend && .venv/bin/python -m pytest tests/test_skill_tools.py
cd apps/backend && .venv/bin/python -m pytest tests/test_expert_policy_routes.py -k 'preset_expert_catalog_exposes_notebook_read_only_tools or readonly_expert_catalog_roles_do_not_expose_mutation_tools'
cd apps/backend && .venv/bin/python -m pytest tests/test_agent_config_service.py -k 'system_preset_config_includes_skill_policy_and_names or system_prompt_matches_baseline'
cd apps/backend && .venv/bin/python -m pytest tests/test_expert_policy_routes.py
```

结果：
- `tests/test_skill_tools.py`：2 passed
- `tests/test_expert_policy_routes.py` 定向：2 passed, 11 deselected
- `tests/test_agent_config_service.py` 定向：2 passed, 16 deselected
- `tests/test_expert_policy_routes.py` 全文件：13 passed

残留扫描：

```bash
rg -n 'aiasys-markdown-output-guide([^[:alnum:]_-]|$)|aiasys-hosting-guide([^[:alnum:]_-]|$)|请立即调用 EnableSkill|立即调用 EnableSkill|必须调用 EnableSkill|只搜索不安装|代码分析、实现方案梳理|修改建议输出|当前不直接修改普通文件' apps/backend/app/agents apps/backend/app/services/agent docs/guides -g '!**/__pycache__/**'
```

结果：无匹配。

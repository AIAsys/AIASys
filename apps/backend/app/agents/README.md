# Agent 配置管理

本目录包含 AIASys 当前主线使用的 Agent prompt、工具和运行时适配。当前 `/analysis` 是通用任务工作区，不再按“数据分析模式 / 科研模式 / auto_research mode”区分主控。

## 当前结构

```text
app/agents/
├── local_sandbox_agent_config/
│   ├── general_host_prompt.md
│   ├── subagent_data_analyst_prompt.md
│   ├── subagent_coder_prompt.md
│   ├── subagent_researcher_prompt.md
│   └── subagent_reviewer_prompt.md
└── tools/
    ├── notebook_runtime_tool.py
    ├── ask_user/
    └── knowledge_tool.py
```

`general_host_prompt.md` 是通用主控提示词模板。`data_analysis` 这个 preset basename 只作为历史兼容配置 ID 保留，不代表当前有“数据分析模式”。

## Python 环境事实源

通用任务只按是否绑定 Python 环境表达运行能力：

- `runtime_binding.env_id = null`：当前任务不带 Python 环境。提示词不能声明本地 Python、预装依赖、notebook helper、Playwright 或 Chromium 已可用。
- `runtime_binding.env_id = "workspace-default"`：当前任务显式启用工作区 Python 环境。后端通过 `RuntimeEnvironmentService` 创建、登记和探测环境，再把真实状态写入 prompt。

Agent prompt 的运行环境段由 `app/services/agent/config.py` 根据当前 session、workspace runtime binding 和环境探测结果生成，不应在模板里静态写死 Python 版本或预装包。

## 添加或调整工具

默认工具、专家角色和 prompt 入口统一在 `app/services/agent/system_presets.py` 维护。新增工具时优先修改对应 baseline 的 `tools` / `allowed_tools`，不要恢复旧 checked-in YAML 作为事实源。

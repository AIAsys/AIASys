+++
name = "Extension Management"
description = "Agent 自主管理 AIASys 扩展（MCP、Expert、Skill）的完整指南。\n覆盖外部市场搜索、安装导入、工作区配置、启用工具管理和策略更新。\n当 Agent 需要为用户安装新能力、配置 MCP 工具或管理专家时使用。"
+++


# 扩展管理指南

本 Skill 让 Agent 通过后端 API 自主完成扩展的搜索、安装和配置，不需要用户手动操作前端。

**前置条件**

- 后端运行在 `http://localhost:13001`
- 本地认证模式（`LocalAuthProvider`）下，所有 API 调用**不需要 token**，直接 curl 即可
- 当前工作区 ID 通常从会话上下文中获取；若不确定，先用 `GET /api/workspaces` 列出

**扩展类型速览**

| 类型 | 定位 | 管理入口 |
|------|------|----------|
| MCP | 外部工具/服务集成（标准协议） | `/api/mcp/...` |
| Expert | 子 Agent / 协作专家 | `/api/workspaces/experts/...` |
| Skill | Agent 能力扩展（Markdown + 脚本） | `/api/skills/...` |

---

## 一、MCP 管理

MCP 采用"三层模型"：外部市场 -> 我的默认仓库（store）-> 工作区生效配置。

**优先使用 Agent 工具**：如果当前 Agent 拥有 `SearchMCPMarket` 和 `InstallMCPServer` 工具，优先使用它们完成搜索和安装，不要手动构造 curl 命令。这些工具自动处理工作区配置和工具启用，比直接调用 API 更可靠。

- `SearchMCPMarket(query="关键词", source_id="modelscope")`：搜索外部市场
- `InstallMCPServer(item_id="条目ID", source_id="modelscope")`：从外部市场导入到工作区

- 外部市场：可搜索的公开/账号同步 MCP 目录
- 我的默认仓库：用户导入后持久保存的 MCP Server 定义
- 工作区配置：从我的默认仓库复制到工作区，可单独覆盖启用状态和工具列表

### 1.1 搜索外部 MCP 市场

**列出市场源**

```bash
curl -s "http://localhost:13001/api/mcp/external-market/sources"
```

返回数组，每个元素含 `source_id`、`display_name`、`description`。用 `source_id` 进行后续搜索。

**搜索市场条目**

```bash
curl -s "http://localhost:13001/api/mcp/external-market/items?source_id=<source_id>&search=<关键词>&page_number=1&page_size=20"
```

关键返回字段：
- `items[].item_id`：条目唯一标识
- `items[].name` / `items[].description`：名称和描述
- `items[].type`：连接类型（`sse`、`streamable-http`、`stdio`）

**查看条目详情**

```bash
curl -s "http://localhost:13001/api/mcp/external-market/detail?source_id=<source_id>&item_id=<item_id>"
```

详情含 `env_fields`（需要配置的环境变量列表）、`readme_excerpt`（说明摘录）和完整的连接参数。

### 1.2 导入到我的默认仓库

确认要安装后，从外部市场导入到"我的默认"：

```bash
curl -s -X POST "http://localhost:13001/api/mcp/external-market/import" \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "<source_id>",
    "item_id": "<item_id>",
    "enabled": true,
    "env_overrides": {
      "API_KEY": "your-key-here"
    }
  }'
```

- `enabled`：导入后是否立即生效（默认 true）
- `env_overrides`：补充环境变量；若详情里 `env_fields` 标了 `required`，这里必须提供

成功返回 `imported_names`（导入的 server 名称列表）和 `message`。

### 1.3 管理我的默认仓库

**列出仓库中的 MCP Server**

```bash
curl -s "http://localhost:13001/api/mcp/store"
```

返回字段：
- `servers[].name`：唯一名称（标识符）
- `servers[].display_name`：展示名称
- `servers[].type`：连接类型
- `servers[].url` / `servers[].command` / `servers[].args`：连接参数
- `servers[].env_fields`：待填环境变量描述
- `servers[].enabled_tools`：当前全局层启用的工具（空表示全部）

**手动添加 Server（适用于非市场来源）**

```bash
curl -s -X POST "http://localhost:13001/api/mcp/store" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-server",
    "type": "sse",
    "url": "http://example.com/sse",
    "description": "自定义 MCP Server",
    "timeout_ms": 30000
  }'
```

`type` 可选 `sse`、`streamable-http`、`stdio`。`stdio` 类型需提供 `command` 和 `args`。

**更新环境变量**

```bash
curl -s -X PUT "http://localhost:13001/api/mcp/store/<server_name>/env" \
  -H "Content-Type: application/json" \
  -d '{"env": {"API_KEY": "new-value"}}'
```

**测试连接**

```bash
curl -s -X POST "http://localhost:13001/api/mcp/store/<server_name>/test"
```

返回 `status`（`connected` 或 `error`）、`tools_count`、`tools[]`（可用工具列表）。连接失败时 `error_message` 会给出友好提示。

**删除仓库中的 Server**

```bash
curl -s -X DELETE "http://localhost:13001/api/mcp/store/<server_name>"
```

### 1.4 工作区 MCP 配置

**查看工作区生效配置**

```bash
curl -s "http://localhost:13001/api/mcp/workspaces/<workspace_id>?scope=effective"
```

`scope=effective` 返回三层合并后的最终生效配置；`scope=workspace` 只返回工作区显式覆盖的 server。

**将仓库 Server 复制到工作区**

```bash
curl -s -X POST "http://localhost:13001/api/mcp/workspaces/<workspace_id>/servers/<server_name>"
```

**从工作区移除**

```bash
curl -s -X DELETE "http://localhost:13001/api/mcp/workspaces/<workspace_id>/servers/<server_name>"
```

注意：这只会移除工作区层的覆盖，不会删除仓库中的原始定义。

**查看 Server 的工具列表**

```bash
curl -s "http://localhost:13001/api/mcp/workspaces/<workspace_id>/servers/<server_name>/tools"
```

返回 `tools[]`（所有可用工具）和 `enabled_tools[]`（当前启用的子集）。

**配置启用的工具（白名单）**

```bash
curl -s -X PUT "http://localhost:13001/api/mcp/workspaces/<workspace_id>/servers/<server_name>/tools" \
  -H "Content-Type: application/json" \
  -d '{"enabled_tools": ["tool_a", "tool_b"]}'
```

传空数组 `[]` 表示禁用该 Server 的所有工具。

**测试工作区连接并缓存工具**

```bash
curl -s -X POST "http://localhost:13001/api/mcp/workspaces/<workspace_id>/servers/<server_name>/test"
```

成功后会自动把工具列表缓存到工作区，供前端和 Agent 使用。

---

## 二、专家（Expert）管理

Expert 是协作子 Agent。系统内置一批专家，用户可以安装到全局或特定工作区，也可以创建自定义专家。

### 2.1 查看可安装的专家

**全局专家目录**

```bash
curl -s "http://localhost:13001/api/workspaces/experts/global"
```

返回 `roles[]`，每个角色含：
- `role_id`：唯一标识（也是安装时用的 `name`）
- `name` / `description`：展示名称和说明
- `host_selectable`：是否允许用户手动启用
- `source`：来源（`builtin`、`system`、`custom`）

**工作区专家目录**

```bash
curl -s "http://localhost:13001/api/workspaces/<workspace_id>/experts"
```

### 2.2 安装系统内置专家

**安装到全局**

```bash
curl -s -X POST "http://localhost:13001/api/workspaces/experts/global/<role_id>/enable" \
  -H "Content-Type: application/json" \
  -d '{"role_id": "<role_id>"}'
```

**安装到工作区**

```bash
curl -s -X POST "http://localhost:13001/api/workspaces/<workspace_id>/experts/<role_id>/enable" \
  -H "Content-Type: application/json" \
  -d '{"role_id": "<role_id>"}'
```

成功返回专家的完整详情（含 `system_prompt`、`model`、`tools`）。

### 2.3 管理专家启用策略

**查看全局策略**

```bash
curl -s "http://localhost:13001/api/workspaces/experts/global/policy"
```

返回 `enabled_role_ids[]`（当前启用的角色列表）、`available_roles[]`（所有可选角色）和 `collaboration_policy`（协作运行默认值）。

**更新全局策略**

```bash
curl -s -X PUT "http://localhost:13001/api/workspaces/experts/global/policy" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled_role_ids": ["coder", "researcher"],
    "role_tool_ids": {
      "coder": ["shell", "write_file"]
    },
    "collaboration_policy": {
      "mode": "parallel",
      "max_parallel": 3
    }
  }'
```

- `enabled_role_ids`：明确启用的角色 ID 列表；传 `null` 表示继承系统默认
- `role_tool_ids`：为特定角色限制可用工具子集；`null` 表示该角色可用全部工具

**查看工作区策略**

```bash
curl -s "http://localhost:13001/api/workspaces/<workspace_id>/experts/policy"
```

**更新工作区策略**

```bash
curl -s -X PUT "http://localhost:13001/api/workspaces/<workspace_id>/experts/policy" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled_role_ids": ["coder"],
    "role_tool_ids": {},
    "collaboration_policy": null
  }'
```

### 2.4 专家可见性策略

**更新全局专家可见性**

```bash
curl -s -X PUT "http://localhost:13001/api/workspaces/experts/global/<role_id>/visibility" \
  -H "Content-Type: application/json" \
  -d '{
    "catalog_visible": true,
    "host_selectable": true,
    "default_enabled": false
  }'
```

- `catalog_visible`：是否在前端目录中展示
- `host_selectable`：是否允许用户选择启用
- `default_enabled`：新工作区是否默认启用

**更新工作区专家可见性**

```bash
curl -s -X PUT "http://localhost:13001/api/workspaces/<workspace_id>/experts/<role_id>/visibility" \
  -H "Content-Type: application/json" \
  -d '{
    "catalog_visible": true,
    "host_selectable": true,
    "default_enabled": false
  }'
```

---

## 三、Skill 管理

Skill 是 Agent 的能力扩展。与 MCP 不同，Skill 以 Markdown + 可选脚本形式存在，由 Agent 主动读取后执行。

Skill 同样采用"外部市场 -> 仓库 -> 工作区"的分层模型。

### 3.1 搜索外部 Skill 市场

**列出市场源**

```bash
curl -s "http://localhost:13001/api/skills/external-market/sources"
```

**搜索市场条目**

```bash
curl -s "http://localhost:13001/api/skills/external-market/items?source_id=<source_id>&search=<关键词>&sort_by=recommended&page_number=1&page_size=24"
```

可选参数：`category`（分类筛选）、`sort_by`（`recommended`、`name`、`updated`）。

返回 `items[]`，含 `item_id`、`name`、`description`、`version`、`author` 等。

**查看条目详情**

```bash
curl -s "http://localhost:13001/api/skills/external-market/detail?source_id=<source_id>&item_id=<item_id>"
```

### 3.2 安装外部 Skill 到工作区

从市场直接安装到指定工作区（不需要先导入仓库）：

```bash
curl -s -X POST "http://localhost:13001/api/skills/external-market/workspaces/<workspace_id>/install" \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "<source_id>",
    "item_id": "<item_id>",
    "force": false
  }'
```

- `force`：若工作区已存在同名 Skill，是否覆盖（默认 false）
- 成功返回 `skill_name`（安装后的 Skill 名称）和 `message`

### 3.3 查看 Skill 仓库

```bash
curl -s "http://localhost:13001/api/skills/store"
```

返回 `skills[]`，每个 Skill 含：
- `name` / `display_name` / `description`
- `source`：来源标识
- `versions[]`：可用版本列表
- `globally_enabled`：是否已在全局工作区启用

### 3.4 管理全局 Skill

**列出全局已启用 Skill**

```bash
curl -s "http://localhost:13001/api/skills/global"
```

**启用 Skill 到全局**

```bash
curl -s -X POST "http://localhost:13001/api/skills/global/enable" \
  -H "Content-Type: application/json" \
  -d '{
    "skill_name": "<skill_name>",
    "version": null,
    "force": false
  }'
```

- `version`：指定版本号，默认使用当前最新版本
- `force`：覆盖已启用的同名 Skill

**从全局禁用**

```bash
curl -s -X POST "http://localhost:13001/api/skills/global/disable" \
  -H "Content-Type: application/json" \
  -d '{"skill_name": "<skill_name>"}'
```

### 3.5 管理工作区 Skill

**列出工作区已启用 Skill**

```bash
curl -s "http://localhost:13001/api/skills/workspaces/<workspace_id>"
```

返回 `skills[]`，额外含 `hash_status`（`match`/`mismatch`/`unknown`，与仓库版本对比）和 `version`。

**启用 Skill 到工作区**

```bash
curl -s -X POST "http://localhost:13001/api/skills/workspaces/<workspace_id>/enable" \
  -H "Content-Type: application/json" \
  -d '{
    "skill_name": "<skill_name>",
    "version": null,
    "force": false
  }'
```

这会从 Skill 仓库复制到工作区 `.aiasys/skills/` 目录。

**从工作区禁用**

```bash
curl -s -X POST "http://localhost:13001/api/skills/workspaces/<workspace_id>/disable" \
  -H "Content-Type: application/json" \
  -d '{"skill_name": "<skill_name>"}'
```

**更新工作区 Skill（从仓库重新复制）**

```bash
curl -s -X POST "http://localhost:13001/api/skills/workspaces/<workspace_id>/update" \
  -H "Content-Type: application/json" \
  -d '{"skill_name": "<skill_name>"}'
```

当仓库里的 Skill 升级后，用此接口同步到工作区。

**读取工作区 Skill 内容**

```bash
curl -s "http://localhost:13001/api/skills/workspaces/<workspace_id>/<skill_name>/entry"
```

返回 `content`（SKILL.md 完整文本）和 `env_fields`（环境变量配置项）。

**删除工作区中的 Skill**

```bash
curl -s -X DELETE "http://localhost:13001/api/skills/workspaces/<workspace_id>/<skill_name>"
```

---

## 四、通用操作模式

### 4.1 安装前确认流程

无论安装 MCP、Expert 还是 Skill，建议遵循以下顺序：

1. **搜索**：用 `.../sources` 获取市场源，再用 `.../items?search=` 查找候选
2. **确认**：用 `.../detail` 查看详情，确认功能、依赖、环境变量要求
3. **安装**：调用对应 install/import/enable 接口
4. **验证**：安装后调用 list/get/test 确认状态正确

### 4.2 使用 Python requests 替代 curl

如果 Agent 更习惯用 `RunCode` 执行 Python：

```python
import requests, json

BASE = "http://localhost:13001"

# 示例：搜索 MCP 市场
r = requests.get(f"{BASE}/api/mcp/external-market/sources")
print(r.json())

# 示例：安装外部 Skill
payload = {"source_id": "github", "item_id": "arxiv-search", "force": False}
r = requests.post(
    f"{BASE}/api/skills/external-market/workspaces/my_ws/install",
    json=payload,
)
print(r.json())
```

本地模式不需要设置任何 `Authorization` 头。

### 4.3 获取当前工作区 ID

如果不确定当前工作区 ID：

```bash
curl -s "http://localhost:13001/api/workspaces"
```

返回 `workspaces[].workspace_id` 和 `workspaces[].title`，从中选择对应项。

### 4.4 错误处理速查

| HTTP 状态 | 常见原因 |
|-----------|----------|
| 400 | 参数错误、名称格式无效、已存在 |
| 404 | 资源不存在（server/role/skill/workspace 未找到） |
| 403 | 系统预设角色不允许修改 |
| 500 | 服务端内部错误，检查后端日志 |

请求失败时，响应体通常包含 `detail` 字段，里面有可读的错误说明。

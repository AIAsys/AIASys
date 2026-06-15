+++
name = "AIASys Connector Installer"
description = "指导 Agent 在 AIASys 系统内搜索、选择并安装连接器（MCP Server）。当用户需要联网搜索、OCR、外部 API 等能力但当前工作区尚未安装对应连接器时触发。"
+++


# AIASys Connector Installer

本 Skill 让 Agent 能够自主发现 AIASys 内置的连接器（MCP Server）并将其安装到当前工作区。

## 何时使用

- 用户说"我要联网搜索""安装搜索连接器""帮我装一个 OCR"等
- Agent 判断当前任务需要某个 MCP 能力，但工作区尚未安装
- 用户询问有哪些可用连接器

## 核心概念

**连接器 = MCP Server**

AIASys 中的"连接器"就是 MCP Server。系统预装了一些内置连接器（AIASys 精选），但不会默认安装到每个工作区。需要时由 Agent 或用户手动安装。

**安装后生效**

连接器安装到当前工作区后，其暴露的工具（如 `web_search`、`web_fetch`）会在会话中可用。通常需要安装后的下一轮对话或新会话才会加载。

## 工作流

### 1. 搜索可用连接器

如果你知道连接器名称或功能，先用 `SearchAvailableConnectors` 搜索系统内置源仓库：

```json
{
  "query": "search"
}
```

返回结果示例：

```json
{
  "items": [
    {
      "capability_id": "stepfun-search",
      "display_name": "StepFun Search",
      "publisher": "StepFun",
      "description": "阶跃星辰官方搜索 MCP 服务，提供 web_search 全网搜索与 web_fetch 网页内容获取。",
      "tools": ["web_search", "web_fetch"]
    }
  ]
}
```

如果内置源仓库找不到，再用 `SearchMCPMarket` 搜索外部市场：

```json
{
  "query": "weather",
  "source_id": "modelscope"
}
```

### 2. 安装连接器

拿到 `capability_id` 后，调用 `InstallConnector`：

```json
{
  "capability_id": "stepfun-search"
}
```

对于需要 API Key 的连接器，安装后需要用户补充 key。你有两种方式帮用户配置：

**方式 A：引导用户设置环境变量**

告诉用户：

```bash
export STEPFUN_API_KEY=your-step-plan-key
```

然后重启后端或新会话生效。

**方式 B：调用 SetEnvVar 写入工作区环境变量**

```json
{
  "name": "STEPFUN_API_KEY",
  "value": "your-step-plan-key"
}
```

注意：SetEnvVar 会写入工作区配置，适合长期使用；但向 Agent 暴露真实 key 时需谨慎，建议让用户自行在 UI 中配置。

### 3. 验证安装

安装后可以用 `ListMCPServers` 查看当前工作区已安装的 MCP Server：

```json
{
  "scope": "workspace"
}
```

## 与已有工具的关系

| 工具 | 用途 | 使用场景 |
|------|------|---------|
| `SearchAvailableConnectors` | 搜索系统内置连接器 | 优先使用，匹配 AIASys 精选 |
| `SearchMCPMarket` | 搜索外部 MCP 市场 | 内置仓库找不到时使用 |
| `InstallConnector` | 安装内置连接器到工作区 | 拿到 capability_id 后使用 |
| `InstallMCPServer` | 导入外部市场条目到系统仓库 | 外部市场条目，需配合配置使用 |
| `ListMCPServers` | 列出已安装/仓库中的 Server | 验证安装结果 |

## 约束

1. **优先内置仓库**：找连接器时先用 `SearchAvailableConnectors`，没有再用 `SearchMCPMarket`
2. **不要重复安装**：安装前先用 `ListMCPServers(scope="workspace")` 确认是否已安装
3. **安装需要用户授权**：`InstallConnector` 是高风险工具，smart 模式下会询问用户，不要在未经授权时反复调用
4. **API Key 处理**：不要在对话中回显用户提供的 key；安装后提醒用户如何配置 key
5. **安装后不一定立即生效**：告诉用户可能需要新建会话或等待下一轮工具加载

## 示例对话

用户：帮我装一个能联网搜索的连接器。

Agent：
1. `SearchAvailableConnectors(query="search")` → 找到 stepfun-search
2. `InstallConnector(capability_id="stepfun-search")` → 安装成功
3. 告诉用户：已安装 StepFun Search，请配置 STEPFUN_API_KEY 后新建会话使用。

# MCP 与 Skill 市场

> 当前版本: v0.3.9

本文档说明 MCP（Model Context Protocol）和 Skill 的概念、管理和使用方式。

## MCP 概念

MCP 是 Model Context Protocol 的缩写，用于扩展系统的能力边界。通过接入 MCP Server，Agent 可以获得与外部系统交互的能力，如操作 Office 文档、发送 IM 消息、控制浏览器等。

MCP Server 是独立运行的服务进程，Agent 通过标准协议与它们通信。一个 MCP Server 可以提供多个工具，Agent 按需调用。

## MCP 管理

MCP Server 按来源分为三类：

### 系统 MCP

系统内置的 MCP Server，随 AIASys 一起部署，不可删除。系统 MCP 提供基础的平台能力。

#### StepFun Search（联网搜索）

AIASys 内置了阶跃星辰的 [StepSearch MCP Server](https://platform.stepfun.com/docs/zh/step-plan/integrations/search-mcp) 作为可安装连接器，需要用户手动安装到工作区后才启用：

- **工具**：`web_search`（全网搜索）、`web_fetch`（网页内容获取）
- **传输类型**：streamable-http
- **服务端点**：`https://api.stepfun.com/step_plan/v1/mcp/web_search/mcp`
- **计费**：`web_search` 每次调用约 0.04 元，与 Step Plan 套餐其他用量叠加；`web_fetch` 不单独计费

**安装与配置方式**：

1. 在"能力管理 → 连接器"（或"能力管理 → 全部/可安装"）中找到 **StepFun Search**，点击"安装"到当前工作区
2. 从 [阶跃星辰开放平台](https://platform.stepfun.com) 获取 Step Plan 套餐的 API Key（注意与普通按量计费 API Key 可能不同）
3. 任选一种方式填入：
   - **环境变量**：启动后端前设置 `export STEPFUN_API_KEY=your-step-plan-key`，安装后的配置中的 `Authorization: Bearer ${STEPFUN_API_KEY}` 会自动解析
   - **工作区配置**：安装后在"能力管理 → MCP 管理"中找到 `stepfun-search`，编辑 Headers，填入 `Authorization: Bearer your-step-plan-key`

安装前不会自动加载，未配置 API Key 时 MCP Server 会连接失败，不影响其他功能。

### Agent 自动安装连接器

系统内置 Skill `aiasys-connector-installer-skill` 可让 Agent 自主发现并安装连接器：

- `SearchAvailableConnectors`：搜索 AIASys 内置源仓库中的可用连接器
- `InstallConnector`：将指定连接器安装到当前工作区

启用该 Skill 后，Agent 可以响应"帮我装一个能联网搜索的连接器"这类指令，自动搜索并安装 StepFun Search 等内置连接器。

注意：`InstallConnector` 属于高风险工具，smart 授权模式下会询问用户确认。

### 自定义 MCP

用户自行添加的 MCP Server。支持两种传输方式：

- **STDIO**：通过标准输入输出与本地进程通信。配置时指定启动命令和参数
- **HTTP**：通过 HTTP 请求与远程服务通信。配置时指定 URL 和认证头

### 外部市场

从外部 MCP 市场导入的 Server 配置。导入后作为自定义 MCP 管理，可以修改配置参数。

## MCP 配置

添加自定义 MCP Server 的步骤：

1. 点击左侧 Activity Bar 的"能力管理"图标
2. 在面板中选择"MCP 管理"分类
3. 点击"添加 Server"
4. 填写配置：

   - **名称**：Server 的标识名称，工作区内唯一
   - **传输方式**：选择 STDIO 或 HTTP
   - **STDIO 配置**：填写启动命令和参数
   - **HTTP 配置**：填写请求 URL 和认证头

5. 点击"测试连接"验证配置是否正确
6. 连接成功后点击"保存"

## MCP 验证

添加 MCP Server 时，系统会对 STDIO 配置进行安全校验，防止命令注入攻击：

- 禁止在命令参数中使用管道符、重定向符
- 禁止使用命令替换语法（反引号、`$()`）
- 禁止使用环境变量展开

如果配置未通过安全校验，系统会拒绝保存并提示具体的违规项。

## 会话级 MCP

每个会话可以独立配置 MCP Server 的启用状态。在会话设置中，可以为当前会话选择性地启用或禁用某些 MCP Server。

会话级配置优先级高于工作区配置。如果某个 Server 在工作区中启用但在会话中禁用，当前会话的 Agent 不会调用该 Server 的工具。

## Skill 概念

Skill 是特定领域的 SOP（标准操作流程）和脚本包。每个 Skill 封装了一套完成特定任务的方法、提示词和工具组合。

Skill 按需安装，不占用上下文。只有被激活时，Skill 的提示词和工具才会注入 Agent 的上下文中。未安装的 Skill 对 Agent 完全不可见。

## Skill 市场

Skill 市场是浏览、搜索、安装和卸载 Skill 的入口。

### 浏览与搜索

在"能力管理"面板中选择"Skill 市场"分类，可以看到所有可用的 Skill。每个 Skill 卡片显示：

- 名称和简要描述
- 标签（系统内置 / 外部市场）
- 当前状态（未安装 / 已安装）

支持按名称和标签搜索过滤。

### 安装

点击 Skill 卡片上的"安装"按钮。安装过程是将 Skill 从源仓库复制到当前工作区的 `.aiasys/skills/` 目录。安装后生成 `.aiasys-skill-meta.json` 元数据文件，记录来源和版本指纹。

### 卸载

点击已安装 Skill 卡片上的"卸载"按钮。卸载只删除工作区中的 Skill 副本，源仓库中的 Skill 不受影响。卸载后可随时重新安装。

### Skill 架构

Skill 采用全局源仓库 + 工作区副本的两层架构：

| 层级 | 路径 | 作用 |
|------|------|------|
| 内置源 | `apps/backend/skills/builtin/` | 系统预装，不可删除 |
| 用户源 | `apps/backend/skills/store/` | 外部市场导入，可从全局仓库删除 |
| 工作区副本 | `{ws}/.aiasys/skills/` | 安装后实际运行的位置 |
| 全局副本 | `global_workspace/.aiasys/skills/` | 全局启用后跨工作区共享 |

## 内置 Skill 清单

| Skill | 说明 |
|-------|------|
| aiasys-platform-skill | 平台操作与运行环境管理 |
| aiasys-tool-usage-skill | Agent 工具选择与使用指南 |
| aiasys-markdown-output-guide-skill | 前端特殊 Markdown 输出规范 |
| aiasys-hosting-guide-skill | 托管控制与托管用户指令规范 |
| aiasys-notebook-first-skill | Notebook-first 数据分析工作流 |
| aiasys-data-viz-guide-skill | ECharts、CSV 和图片展示规范 |
| aiasys-data-tools-guide-skill | 数据库、知识库、知识图谱、多维表和 Canvas 工具指南 |
| competition-research-skill | 竞赛场景完整工作流（文献检索、论文摄入、实验循环） |
| competition-parallel-research-skill | 竞赛并行研究执行 |
| competition-runtime-prep-skill | 竞赛运行环境准备 |
| skill-creator-skill | Skill 开发工作台（结构、测试、打包、部署） |
| extension-management-skill | MCP、Skill 和协作专家扩展管理 |
| arxiv-search-skill | arXiv 论文搜索与下载 |
| pdf-translate-skill | PDF 保版式翻译 |
| pymupdf4llm-pdf-to-markdown-skill | PDF 转 Markdown 供 Agent 阅读 |
| paddleocr-skill | PaddleOCR 文档提取 |
| aiasys-canvas-skill | AIASys Canvas 对象编辑 |
| aiasys-memory-organizer-skill | Memory 整理与 consolidation |
| tabular-data-preview-skill | Excel、CSV 等表格文件结构化预览 |
| uv-runtime-skill | 当前工作区 UV/Python 运行环境管理 |

## 访问入口

点击左侧 Activity Bar 的"能力管理"图标，面板中分为两个主分类：

- **MCP 管理**：查看、添加、编辑、测试 MCP Server
- **Skill 市场**：浏览、搜索、安装、卸载 Skill

## Agent 自主管理

Agent 具备自主管理 MCP 和 Skill 的能力。Agent 可以：

- 搜索市场中的 Skill，根据任务需要推荐安装
- 按当前授权模式安装和配置 Skill：manual 模式需逐条确认；smart 模式下内置低风险 Skill 可自动放行，外部来源或含脚本 Skill 仍需确认；auto/full_auto 模式在硬安全边界内自动执行
- 添加和测试 MCP Server 连接
- 在会话中启用或禁用 MCP Server

搜索结果只是候选，不会自动变成安装动作。审查、咨询、评估和复盘类请求中，Agent 只会列出候选和推荐理由，不会因为搜到了 Skill 就直接安装。

Agent 的所有管理操作都会记录在执行流中，用户可以随时查看和撤销。

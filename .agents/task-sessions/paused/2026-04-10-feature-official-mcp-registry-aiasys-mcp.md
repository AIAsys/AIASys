# Task Session: 集成 Official MCP Registry 到 AIASys MCP 发现与管理面板

<!-- 
  说明: 这是 AI 任务执行的上下文持久化文件
  用途: 将 AI 的"工作记忆"从易失的上下文窗口转移到持久化的文件系统
-->

---

## Metadata

| 字段 | 内容 |
|------|------|
| **任务类型** | feature (功能开发) |
| **关联版本** | v0.3.2 |
| **关联任务** | 集成 Official MCP Registry 到 AIASys MCP 发现与管理面板 |
| **创建时间** | 2026-04-10 02:08 |
| **最后更新** | 2026-04-12 |
| **预计耗时** | 6-8h |
| **实际耗时** | _h |
| **状态** | ⏸️ paused |
| **执行者** | AI |

---

> 暂缓说明（2026-04-12）
> 本会话目前只完成了立项说明、范围和实现计划，还没有进入真实代码实现。
> 由于当前主线已经收口到 notebook/workbench 设计与实现，本项暂时移出 `active/`，
> 待用户明确要正式开做 Official MCP Registry 后再恢复。

---

## 1. Goal（目标）

**一句话目标**: 在 AIASys 中构建一个基于 Official MCP Registry 的 MCP Server 发现与管理面板，支持定时同步元数据、本地搜索筛选、以及连接配置管理。

**成功标准**:
- [ ] 后端能定时从 `registry.modelcontextprotocol.io` 拉取 MCP Server 元数据并持久化到本地数据库
- [ ] 前端提供 MCP 发现页面：支持关键词搜索、按 runtime 分类（node/python/docker）、结果列表展示
- [ ] 用户可将某个 MCP Server "添加到工作区"，生成并保存本地配置（命令/SSE URL/环境变量）
- [ ] 与现有 `aiasys-resource-verification` 体系对接：对新增配置执行"验活"检查
- [ ] 所有验收项通过测试验证，代码已提交

---

## 2. Scope（范围）

### 2.1 In Scope（包含）
- 后端新增 `MCPDiscoveryService`：封装 Official Registry API 调用、数据清洗、增量同步
- 数据库新增 `mcp_registry_server` 表：存储官方 registry 的元数据（名称、描述、仓库地址、安装包信息、远程端点、版本等）
- 数据库新增 `workspace_mcp_config` 表：存储用户/工作区级别的 MCP 配置实例
- 后端新增 API 路由：
  - `GET /api/mcp/registry/servers` — 搜索/列表本地缓存的 MCP Server
  - `POST /api/mcp/registry/sync` — 手动触发同步（管理员/系统用）
  - `POST /api/workspaces/{id}/mcp-configs` — 将某个 MCP Server 添加为工作区配置
  - `GET /api/workspaces/{id}/mcp-configs` — 获取工作区已配置的 MCP 列表
- 前端新增 "MCP 广场" 页面：搜索框、分类筛选、结果卡片、详情弹窗（含安装方式/环境变量说明）、"添加"按钮
- 后端定时任务（APScheduler / Celery beat / 或简单后台线程）：每小时自动执行一次同步

### 2.2 Out of Scope（不包含）
- 不接入 Smithery、腾讯云 MCP 广场等第三方平台（后续可扩展）
- 不提供 MCP Server 的云托管执行能力（只保存配置，不替用户运行 Server）
- 不实现 MCP 协议本身的 Client/Server 通信层（配置生成后，由用户本地或外部系统消费）
- 不处理付费/订阅相关的 MCP Server 商业逻辑

---

## 3. Context（上下文）

### 3.1 问题背景
AIASys 作为 AI 辅助开发系统，需要让用户方便地发现和配置 MCP Server。Official MCP Registry（`registry.modelcontextprotocol.io`）是由 Anthropic + GitHub + Microsoft 等维护的权威元数据 registry，提供**免费、无认证、只读的 REST API**，是合法且稳定的数据源。

### 3.2 Official Registry API 关键信息

**Base URL**: `https://registry.modelcontextprotocol.io`

**核心端点**:
```bash
# 1. 列出所有服务器（支持 cursor 分页）
GET /v0.1/servers?limit=100
Response: {
  "servers": [...],
  "metadata": { "count": 100, "nextCursor": "..." }
}

# 2. 按关键词搜索
GET /v0.1/servers?search=filesystem&limit=20

# 3. 按更新时间过滤（增量同步用）
GET /v0.1/servers?updated_since=2025-10-23T00:00:00.000Z

# 4. 获取某个 Server 的详情（版本列表）
GET /v0.1/servers/{serverName}/versions

# 5. 获取特定版本详情（可用 `latest`）
GET /v0.1/servers/{serverName}/versions/{version}
```

**重要约束**:
- 官方明确说明：**"Aggregators are expected to scrape data on a regular but infrequent basis (for example, once per hour) and persist the data in their own data store."**
- 因此**必须本地缓存**，不能直接在前端每次请求都透传调用官方 API。

**Server 对象示例**:
```json
{
  "server": {
    "$schema": "https://static.modelcontextprotocol.io/schemas/2025-09-29/server.schema.json",
    "name": "io.github.gongrzhe/redis-mcp-server",
    "description": "A Redis MCP server...",
    "repository": {
      "url": "https://github.com/GongRzhe/REDIS-MCP-Server",
      "source": "github"
    },
    "version": "1.0.0"
  },
  "packages": [
    {
      "registry_name": "docker",
      "name": "@gongrzhe/server-redis-mcp",
      "version": "1.0.0",
      "package_arguments": [...]
    }
  ],
  "remotes": [
    {
      "type": "streamable-http",
      "url": "https://yourdomain.com/yourserver"
    }
  ]
}
```

### 3.3 相关入口
| 入口 | 说明 | 路径 |
|------|------|------|
| 后端主线 | FastAPI 项目结构 | `apps/backend/app/` |
| 前端主线 | React 19 + Tailwind 4 | `apps/web/src/` |
| 系统设计 | AIASys 专属约束 | `.agents/skills/aiasys-system-design/SKILL.md` |
| 前端开发规范 | React 19 模式 | `.agents/skills/frontend-pattern/SKILL.md` |
| 后端开发规范 | API 开发模式 | `.agents/skills/api-dev/SKILL.md` |
| 资源验活 | 已有 skill，评估如何复用 | `.agents/skills/aiasys-resource-verification/SKILL.md` |
| SOP 流程 | 实施五步法 | `.agents/skills/sop-workflow/SKILL.md` |

### 3.4 约束条件
- 所有 Python 命令使用项目已有的 `.venv` 环境
- 后端必须使用 `APIRouter`，禁止直接用 `app`
- 响应模型必须显式定义 Pydantic model
- 数据库操作必须异步（SQLAlchemy async）
- 前端必须使用 Tailwind CSS 4，`cn()` 工具合并类名
- 新增 hook/定时任务需考虑 fail-open 原则
- 不引入重量级依赖（如 Celery）除非已有基础设施

---

## 4. Plan（执行计划）

### Phase 1: 需求理解与架构设计
**状态**: pending | **预计**: 1h

- [ ] 阅读 `api-dev`、`frontend-pattern`、`aiasys-system-design` 三个 skill
- [ ] 检查现有数据库模型（`apps/backend/app/models/`）和路由结构
- [ ] 确认项目中使用的定时任务方案（APScheduler / Celery / 无）
- [ ] 确认 `aiasys-resource-verification` 的接口，规划如何对 MCP 配置做验活
- [ ] 设计数据库模型（`MCPRegistryServer`、`WorkspaceMCPConfig`）
- [ ] 设计 API 契约（Request/Response Pydantic models）
- [ ] **检查点**: 产出 `architecture.md` 或在本文件的 4.2 决策记录中补齐

### Phase 2: 后端实现
**状态**: pending | **预计**: 2.5h

- [ ] **数据库模型**: 在 `apps/backend/app/models/` 下新增 `mcp_registry.py`
  - `MCPRegistryServer`: 对应官方 registry 的元数据
  - `WorkspaceMCPConfig`: 用户在工作区中保存的 MCP 配置实例
- [ ] **数据同步服务**: 新增 `apps/backend/app/services/mcp_discovery.py`
  - 封装 HTTP client 调用 Official Registry API
  - 支持分页拉取、增量同步（`updated_since`）
  - 将结果清洗后写入数据库（upsert 逻辑）
- [ ] **API 路由**: 新增 `apps/backend/app/api/routes/mcp_registry.py`
  - `GET /api/mcp/registry/servers` — 本地搜索（query + runtime filter + pagination）
  - `POST /api/mcp/registry/sync` — 手动触发同步
  - `POST /api/workspaces/{id}/mcp-configs` — 添加工作区 MCP 配置
  - `GET /api/workspaces/{id}/mcp-configs` — 获取工作区 MCP 配置列表
- [ ] **定时任务**: 在 `apps/backend/app/main.py` 或独立模块中注册 hourly sync job
- [ ] **检查点**: 后端接口通过 curl / pytest 自测通过

### Phase 3: 前端实现
**状态**: pending | **预计**: 2.5h

- [ ] 新增页面路由和组件目录（参考现有页面结构）
  - 建议路径: `apps/web/src/pages/Settings/MCPDiscovery/` 或独立 `apps/web/src/pages/MCP/`（视现有路由设计而定）
- [ ] 实现 `MCPDiscoveryPage`:
  - 顶部搜索栏 + runtime 筛选标签（All / Node / Python / Docker / Remote）
  - 结果列表：卡片展示（名称、描述、仓库链接、安装方式标签）
  - 点击卡片弹出详情 `Dialog`：展示完整 metadata、packages/remotes、环境变量说明
  - "添加到工作区" 按钮：调用 `POST /api/workspaces/{id}/mcp-configs`
- [ ] 实现 `WorkspaceMCPConfigList`:
  - 展示当前工作区已添加的 MCP 配置
  - 每个配置显示"验活状态"（如果有接入 resource-verification）
- [ ] **检查点**: 前端页面可正常渲染、搜索、添加配置

### Phase 4: 测试与验证
**状态**: pending | **预计**: 1.5h

- [ ] 手动测试 Official Registry API 同步（验证数据完整性）
- [ ] 手动测试前端搜索、筛选、详情弹窗、添加配置全流程
- [ ] 运行后端 pytest（如有）/ lint / type-check
- [ ] 运行前端 `npm run lint` / `npm run type-check`
- [ ] **检查点**: 所有 AC 满足

### Phase 5: 交付与同步
**状态**: pending | **预计**: 0.5h

- [ ] 整理变更，按规范提交 commit（中英文双语 message）
- [ ] 更新本 task session 中的进度、决策、风险、验证证据
- [ ] 关闭 task session（移动到 `completed/`）

---

## 4. Findings（发现）

### 4.1 技术发现
| 发现 | 来源 | 影响 | 记录时间 |
|------|------|------|----------|
| Official Registry 提供无认证只读 REST API | 官方文档 | 可直接集成，无需 OAuth 或 API Key | 2026-04-10 |
| 官方要求聚合器定期抓取并本地持久化 | 官方文档 | 必须设计本地缓存表和定时同步机制 | 2026-04-10 |
| Registry 目前处于 preview，API 可能有 breaking changes | 第三方评测 | 封装层要做好版本兼容和异常处理 | 2026-04-10 |

### 4.2 决策记录
| 决策 | 可选方案 | 选择理由 | 决策时间 |
|------|----------|----------|----------|
| 使用 Official Registry 而非 Smithery | Smithery / 腾讯云 MCP 广场 | 官方 API 免费开放、无认证、无商业风险、数据结构规范 | 2026-04-10 |
| 本地缓存 + 定时同步 | 每次请求透传官方 API | 符合官方设计意图、降低请求延迟、避免 rate limit | 2026-04-10 |

### 4.3 关联规范
| 规范文件 | 适用场景 | 关键要点 |
|----------|----------|----------|
| `api-dev` | 后端路由/模型/服务 | APIRouter、Pydantic、async DB |
| `frontend-pattern` | 前端页面 | React 19、Tailwind 4、`cn()` |
| `aiasys-system-design` | 信息架构 | 工作区是一等对象 |
| `aiasys-resource-verification` | 验活 | 统一验证资源可用性 |

---

## 5. Issues & Risks（问题与风险）

### 5.1 已解决问题
| 问题 | 严重程度 | 解决方案 | 解决时间 |
|------|----------|----------|----------|
| 无 | - | - | - |

### 5.2 待解决问题
| 问题 | 严重程度 | 计划解决 | 阻塞状态 |
|------|----------|----------|----------|
| 项目中是否已有 APScheduler / Celery 等定时任务基础设施 | 中 | Phase 1 调查 | 否 |
| `workspace_mcp_config` 与工作区现有权限模型如何对接 | 中 | Phase 1 设计 | 否 |

### 5.3 潜在风险
| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| Official Registry API 返回 schema 变化导致解析失败 | 中 | 同步中断 | 封装层做异常捕获和日志记录，避免同步任务崩溃 |
| Registry 收录量较小（~500），用户可能觉得不够用 | 高 | 体验落差 | 后续可扩展 npm/PyPI 搜索作为补充数据源 |
| 某些 MCP Server 需要本地文件访问，无法直接远程配置 | 中 | 配置后仍无法使用 | 前端在展示时标注 "Local Only" 或 "Hosted Available" |

---

## 6. Progress Log（进度日志）

### Session 2026-04-10

**开始时间**: 02:08  
**结束时间**: _  
**持续时间**: _h _m

**本次目标**: 完成 Task Session 初始化与任务文档撰写，交由下一个 AI 执行。

**完成工作**:
- [x] 创建 Task Session
- [x] 补齐 Goal / Scope / Context / Plan / Risks

**遇到的问题**:
- 无

**下一步计划**:
- 待用户明确恢复优先级后，从 Phase 1 开始：阅读相关 skill 和现有代码，确认架构方案

**文件变更**:
| 文件 | 操作 | 说明 |
|------|------|------|
| `.agents/task-sessions/active/2026-04-10-feature-official-mcp-registry-aiasys-mcp.md` | 创建 | 任务主文档 |

---

## 7. Summary（总结）

当前仅完成任务定义与实施计划，尚未进入实现阶段，因此本轮不以 completed 关闭，而是转为 `paused`，避免继续占用 `active` 名额。

*任务会话模板 v1.0.0 | 创建于 2026-04-10 02:08*

# CLAUDE.md

> CLAUDE CLI 入口

---

## AI 协作入口

**所有开发任务从此开始：**

### [→ AGENTS.md](AGENTS.md)

---

## 项目概览

**AIASys** — 以任务工作区为核心的 AI 工作平台。

### 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12+, FastAPI, Pydantic v2, 自研 Agent Runtime, FastMCP |
| 前端 | React 19, TypeScript, Vite, Tailwind CSS 4, shadcn/ui, Pixi.js + d3-force |
| 基础设施 | Docker, Nginx |
| 设计 | Markdown 设计文档 |

### 关键目录

```
AIASys/
├── apps/backend/          # Python 后端（FastAPI + Agent Runtime）
│   ├── app/               # 主应用代码
│   ├── tests/             # 后端测试
│   └── pyproject.toml     # Python 依赖
├── apps/web/              # React 前端
│   ├── src/               # 前端源码
│   └── package.json       # Node 依赖
├── apps/desktop/          # Electron 桌面壳
├── design-draft/          # 设计产物与归档
│   └── design/            # 正式设计文档
├── docs/                  # 对外文档
├── infra/                 # 基础设施配置
├── scripts/               # 项目级工具脚本
└── .agents/               # AI 协作配置
    ├── skills/            # 协作 Skill
    └── task-sessions/     # 复杂任务会话记录
```

### 常用命令

```bash
# 后端（注意：不带 --reload，避免多 agent 并行时热重启相互干扰）
cd apps/backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 13001

# 前端（HMR 已在 vite.config.ts 中禁用）
cd apps/web && npm run dev -- --host 0.0.0.0 --port 13000

# 测试
cd apps/backend && uv run pytest
cd apps/web && npm run test:e2e:lifecycle
```

> **重要**：开发服务器**禁止使用热刷新/热重载**。因为多个终端 agent 可能同时在干活，一个 agent 保存文件触发重启可能导致其他 agent 调试中的服务崩溃。完成任务后手动重启服务器让用户测试验收。

### 协作规则摘要

- **安全优先（P0）**：禁止硬编码密钥、禁止 force push、保护 .env
- **先对齐再执行（P1）**：明确目标/范围/验收标准后再动手
- **SOP 五步法（P2）**：需求 → 设计 → 编码 → 验证 → 交付
- **代码洁癖（P3）**：发现遗留代码随手清理，不堆积技术债
- **详见 [AGENTS.md](AGENTS.md)**
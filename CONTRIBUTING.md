# AIASys 贡献指南

> 欢迎加入 AIASys。本指南只讲当前仓库的真实协作方式，不再保留已经偏离实现的旧流程。

## 1. 协作原则

- **代码优先**：文档和规则必须跟随已验证的实现，而不是反过来替代码做假设。
- **验证后回写**：先完成实现与验证，再同步更新 `docs/`、`.agents/skills/.ai-rules/`、需求台账和 changelog。
- **入口收口**：本地开发优先使用根目录统一入口 `./dev.sh`，不要默认各自进入前后端目录手工拼命令。

## 2. 快速上手

### 2.1 环境准备

- 克隆项目后先看 [docs/guides/QUICKSTART.md](docs/guides/QUICKSTART.md)
- 推荐顺序：

```bash
./dev.sh setup-hooks
./dev.sh

# 如需强制本地沙盒模式
./dev.sh start-local
```

- AI 协作与执行规则入口： [.agents/skills/.ai-rules/README.md](.agents/skills/.ai-rules/README.md)

### 2.2 日常开发流程

1. 创建分支：`git checkout -b feature/your-feature-name`
2. 实现改动：优先遵循仓库现有结构，不额外引入平行方案或重复入口。
3. 自检验证：
   - 后端：在 `apps/backend/` 至少运行 `make test`
   - 后端静态检查：如有必要再运行 `make lint`
   - 前端：在 `apps/web/` 至少运行 `npm run build`
   - 前端补充检查：按需要运行 `npm run lint`、`npm run test:e2e:lifecycle`
4. 回写文档：验证通过后，再更新相关 `docs/`、`.ai-rules`、`todo-lists`、`changelog`
5. 提交代码：先执行一次 `./dev.sh setup-hooks`，之后直接使用 `git commit`

## 3. 提交规范

当前仓库以 **Conventional Commits 风格** 为主，允许可选 scope：

- `feat:`
- `fix:`
- `docs:`
- `refactor:`
- `perf:`
- `test:`
- `chore:`

推荐格式：

```text
type(scope): 简短说明
```

示例：

- `feat(runtime-env): add local sandbox mode selection`
- `fix(ui): move attachment menu inside container`
- `docs: refresh contributing and startup docs`

## 4. PR / 推送前检查

- 说明清楚：
  - 改了什么
  - 为什么改
  - 如何验证
- 影响主链路或完成口径的改动，必须同步更新：
  - `.agents/skills/.ai-rules/`
  - `docs/changelog/`

## 5. 项目结构

```text
AIASys/
├── apps/
│   ├── backend/          # Python 后端（FastAPI + Agent Runtime）
│   │   ├── app/          # 主应用代码
│   │   ├── skills/       # 系统内置 skill
│   │   ├── templates/    # 工作区模板
│   │   └── tests/        # 后端测试
│   ├── web/              # React 19 + Vite 前端
│   │   ├── src/          # 前端源码
│   │   └── e2e/          # Playwright E2E 测试
│   └── desktop/          # Electron 桌面壳
├── design-draft/         # 设计产物与归档（gitignore）
├── docs/                 # 对外文档（快速启动、changelog）
├── images/               # README / docs 配图
├── infra/                # Docker / 部署配置
├── scripts/              # 项目级工具脚本
│   ├── dev/              # dev.sh、生命周期测试
│   ├── design/           # 设计基线校验
│   └── security/         # 安全扫描
├── .agents/              # AI 协作配置
│   ├── skills/           # 协作 skill（含 .ai-rules）
│   └── task-sessions/    # 复杂任务会话记录
└── DESIGN.md             # 视觉设计基线
```

**AI 协作规则主文档**：[AGENTS.md](AGENTS.md) — 包含完整的协作规则、项目语义、Memory 设计边界、LLM 编码最佳实践等，开发前必读。

## 6. 获取帮助

如果你在开发中遇到任何困惑，欢迎：
- 在 [Issues](https://github.com/AIAsys/AIASys/issues) 中提问。
- 查阅 [docs/guides/](docs/guides/) 目录下的详细指南。
- 阅读 [AGENTS.md](AGENTS.md) 了解协作规则和项目语义约束。

---

*感谢你的贡献！让我们一起打造最智能的 AI Agent 工作平台。*

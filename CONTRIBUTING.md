# AIASys 贡献指南

> 欢迎加入 AIASys。本指南只讲当前仓库的真实协作方式，不再保留已经偏离实现的旧流程。

## 1. 协作原则

- **代码优先**：文档和规则必须跟随已验证的实现，而不是反过来替代码做假设。
- **验证后回写**：先完成实现与验证，再同步更新 `docs/`、需求台账和 changelog。
- **入口收口**：本地开发优先使用根目录统一入口 `./dev.sh`，不要默认各自进入前后端目录手工拼命令。

## 2. 快速上手

### 2.1 环境准备

- 克隆项目后先看 [docs/guides/getting-started/QUICKSTART.md](docs/guides/getting-started/QUICKSTART.md)
- 推荐顺序：

```bash
./dev.sh setup-hooks
./dev.sh

# 如需强制本地沙盒模式
./dev.sh start-local
```

### 2.2 日常开发流程

1. 创建分支：`git checkout -b feature/your-feature-name`
2. 实现改动：优先遵循仓库现有结构，不额外引入平行方案或重复入口。
3. 自检验证：
   - 后端：在 `apps/backend/` 至少运行 `make test`
   - 后端静态检查：如有必要再运行 `make lint`
   - 前端：在 `apps/web/` 至少运行 `npm run build`
   - 前端补充检查：按需要运行 `npm run lint`、`npm run test:e2e:lifecycle`
4. 回写文档：验证通过后，再更新相关 `docs/`、`todo-lists`、`changelog`
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

### 4.1 分支保护规则

仓库采用三支分层策略，push 权限有严格限制：

| 分支 | 角色 | 直接 push | PR 要求 |
|------|------|-----------|---------|
| `main` | 发布分支 | 禁止 | 必须从 `dev` 合并，需 review |
| `dev` | 开发分支 | 禁止 | 必须从个人分支合并，需 review |
| `li-xiu-qi` 等个人分支 | 日常开发 | 允许（force push 允许） | 合并到 `dev` 时提 PR |

- 任何改动都不要直接 push 到 `main` 或 `dev`，走 PR 流程。
- 个人分支的 force push 只用于 amend 修补自己的提交，不用于覆盖他人代码。
- CODEOWNERS（`.github/CODEOWNERS`）定义了各路径的默认审查人，PR 会自动请求对应 Owner 审查。

### 4.2 Pre-commit Hooks

项目使用 [Lefthook](https://github.com/evilmartians/lefthook) 管理 pre-commit 检查，配置文件在仓库根目录 `lefthook.yml`：

```bash
# 首次使用需安装 hooks（在项目根目录执行）
cd apps/web && npx lefthook install
```

pre-commit 阶段会自动运行：

- **前端**：ESLint 检查 + TypeScript 类型检查
- **后端**：Ruff lint & format 检查 + Pylint 检查
- **通用**：EditorConfig 合规检查

### 4.3 PR 描述要求

- 说明清楚：
  - 改了什么
  - 为什么改
  - 如何验证
- 影响主链路或完成口径的改动，必须同步更新：
  - `docs/changelog/`

### 4.4 编辑器配置

仓库根目录有 `.editorconfig`，大多数编辑器安装对应插件后会自动读取。它统一了缩进风格（Python 4 空格，前端 2 空格）、换行符（LF）、文件编码（UTF-8）等基础格式规则，避免因编辑器差异产生不必要的 diff。

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
├── docs/                 # 对外文档（快速启动、changelog）
├── images/               # README / docs 配图
├── infra/                # Docker / 部署配置
├── scripts/              # 项目级工具脚本
│   ├── dev/              # dev.sh、生命周期测试
│   ├── design/           # 设计基线校验
│   └── security/         # 安全扫描
└── DESIGN.md             # 视觉设计基线
```

## 6. 获取帮助

如果你在开发中遇到任何困惑，欢迎：
- 在 [Issues](https://github.com/AIAsys/AIASys/issues) 中提问。
- 查阅 [docs/guides/](docs/guides/) 目录下的详细指南，入口见 [docs/guides/README.md](docs/guides/README.md)。
- 了解哪些 AI Agent 配置应该/不应该提交：见 [docs/guides/contributing/ai-agent-config-guidelines.md](docs/guides/contributing/ai-agent-config-guidelines.md)。

---

*感谢你的贡献！让我们一起打造最智能的 AI Agent 工作平台。*


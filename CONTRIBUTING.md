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

1. Fork 项目到你自己的 GitHub 账户
2. Clone 你的 fork：`git clone https://github.com/YOUR_USERNAME/AIASys.git`
3. 添加上游仓库：`git remote add upstream https://github.com/AIAsys/AIASys.git`
4. 创建分支：`git checkout -b feature/your-feature-name`
5. 实现改动：优先遵循仓库现有结构，不额外引入平行方案或重复入口。
6. 自检验证：
  - 后端：在 `apps/backend/` 至少运行 `make test`
  - 后端静态检查：如有必要再运行 `make lint`
  - 前端：在 `apps/web/` 至少运行 `npm run build`
  - 前端补充检查：按需要运行 `npm run lint`、`npm run test:e2e:lifecycle`
7. 推送到你的 fork：`git push origin feature/your-feature-name`
8. 从你的 fork 向 `AIAsys/AIASys` 的 `dev` 分支提交 PR

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

### 3.2 Commit 拆分原则

**每个 commit 只做一个逻辑单元。** 不要把前端 UI、后端 API、bugfix、文档、截图混在一个 commit 里。

**不好的示例（不要这样做）：**

```text
feat: @ 文件引用功能 + Windows Shell/桌面打包修复
```

这个 commit 同时包含：
- 前端文件引用 UI
- 后端 Shell 执行逻辑
- 桌面打包脚本

review 和回滚都很困难。

**好的示例（拆分后）：**

```text
feat(web): 添加 @ 文件选择器与引用标签
feat(web): 消息气泡中美化显示 @/workspace/ 文件引用
fix(backend): Windows 下 uv/fnm 路径与 .exe 后缀匹配
fix(backend): 彻底移除 cmd.exe 支持
chore(desktop): 优化 prepare-runtime 打包前清理逻辑
```

拆分原则：
- 前端组件改动一个 commit
- 后端 API/服务改动一个 commit
- bug 修复一个 commit
- 文档/截图一个 commit
- 版本号/changelog 一个 commit
- 纯格式化（`style:`）单独一个 commit，不与其他改动混合

## 4. PR / 推送前检查

### 4.1 分支策略

项目采用 Fork + PR 工作流：

| 分支 | 角色 | 直接 push | PR 要求 |
|------|------|-----------|---------|
| `main` | 稳定发布分支 | 禁止 | 必须从 `dev` 合并，需 review |
| `dev` | 开发分支 | 禁止 | 必须从 fork 的分支合并，需 review |

流程：
- **外部贡献者**：Fork → 创建分支 → 提交 PR 到 `AIASys/AIASys` 的 `dev`
- **维护者**：审查并合并 PR 到 `dev`，定期从 `dev` 合并到 `main` 发版

保持 fork 同步：
```bash
git fetch upstream
git checkout dev
git merge upstream/dev
git push origin dev
```

- **任何改动都不要直接 push 到 `main` 或 `dev`，必须走 PR 流程**。维护者/管理员自己的改动也不例外，至少在 GitHub 上留下 PR 记录和 review 痕迹。
- CODEOWNERS（`.github/CODEOWNERS`）定义了各路径的默认审查人，PR 会自动请求对应 Owner 审查。
- 若只有一位维护者，可启用 self-review，但仍需通过 PR 合并，不能直接 push。

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
- **Changelog 强制规则**：任何用户可感知的功能新增、bug 修复、性能优化、接口不兼容修改，必须随 PR 同步更新 `docs/changelog/`。详见 `docs/changelog/README.md`。
- **版本号同步规则**：如果是 release PR，必须确认三端版本号一致：
  - `apps/web/package.json`
  - `apps/desktop/package.json`
  - `apps/backend/pyproject.toml`

### 4.4 编辑器配置

仓库根目录有 `.editorconfig`，大多数编辑器安装对应插件后会自动读取。它统一了缩进风格（Python 4 空格，前端 2 空格）、换行符（LF）、文件编码（UTF-8）等基础格式规则，避免因编辑器差异产生不必要的 diff。

## 5. 发布流程（维护者专用）

### 5.1 分支流程

发布必须严格遵循 `dev` → `main` 的合并路径：

1. 所有功能/修复先合并到 `dev`
2. 准备发版时，从 `dev` 向 `main` 创建 PR
3. PR 通过 CI 和 review 后合并到 `main`
4. 在 `main` 上执行发布脚本

禁止直接在 `main` 上开发并打 tag。

### 5.2 发布脚本

使用项目提供的发布辅助脚本：

```bash
./scripts/dev/release.sh 0.4.17
```

脚本会：
- 检查当前分支为 `main` 且工作区干净
- 检查 `docs/changelog/v0.4.17_YYYY-MM-DD.md` 已存在
- 同步三端版本号
- 提交版本号变更
- 打 tag `v0.4.17`

演练模式（不实际提交/tag）：

```bash
./scripts/dev/release.sh --dry-run 0.4.17
```

### 5.3 发版检查清单

- [ ] `dev` 已合并到 `main`
- [ ] `docs/changelog/vX.Y.Z_YYYY-MM-DD.md` 已按规范编写
- [ ] 三端版本号已同步
- [ ] CI 在 `main` 上通过
- [ ] 已打 tag `vX.Y.Z` 并推送到 `upstream`
- [ ] Desktop Build & Pre-release CI 成功完成
- [ ] Release 产物（AppImage / exe / dmg / zip）已上传

### 5.4 版本号规则

- 采用语义化版本（SemVer）：`MAJOR.MINOR.PATCH`
- 预发布版本：`X.Y.Z-beta.N`（如 `0.4.17-beta.1`）
- 当前阶段以 beta 预发布为主，release 标记 `prerelease=true`

## 6. 项目结构

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


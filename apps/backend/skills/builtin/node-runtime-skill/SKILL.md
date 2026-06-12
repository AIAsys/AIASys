+++
name = "Node 运行环境"
description = "管理当前 AIASys 工作区的 Node.js/fnm 运行环境。适用于用户询问怎么使用 Node.js、\n怎么安装 npm 依赖、怎么检查 workspace-default 环境、为什么工作区有 .env 目录、\n或需要把脚本、应用、CLI 工具绑定到工作区 Node 环境时使用。"
+++


# Node 运行环境 Skill

这个 skill 只负责当前工作区的 Node.js/fnm 运行环境。平台总览、Docker 沙盒、环境变量和数据表仍由 `aiasys-platform-skill` 说明。

## 先分清三件事

| 名称 | 作用 | 位置或入口 |
|------|------|------------|
| Node 环境物料 | Node.js 版本声明、依赖声明和锁文件 | 工作区 `.env/` |
| 工作区环境变量 | API key、token、服务地址等运行时变量 | `.workspace/workspace.json` 的 `runtime_binding.env_vars` |
| 一次性工具 | 临时运行重依赖 CLI，不污染工作区默认环境 | `npx` |

`.env/` 是 AIASys 管理的工作区 Node 物料目录，不是传统 dotenv 文件。不要把 API key 写进 `.env/package.json` 或 `.env/package-lock.json`。

## 默认目录

AIASys 管理的默认 Node 环境会落在当前工作区根目录：

```text
.env/
├── environments.json
├── package.json
├── package-lock.json
├── .node-version
└── .node_modules/
```

默认环境 ID 是 `workspace-default`。fnm 管理的 Node 版本缓存在 `~/.fnm/node-versions/` 下。

不要直接编辑 `.env/environments.json`。创建、绑定、安装和检查都通过 `RuntimeEnvironment` 工具完成。

## 什么时候用

- 用户要运行 Node.js 脚本、前端应用或自动化工具。
- 缺少 npm 包，需要安装到当前工作区。
- 要确认当前会话是否绑定了 Node 环境。
- 要切换或检查 `workspace-default`。
- 要解释工作区里的 `.env/`、`.node-version`、`package.json` 或 `package-lock.json`。
- 要使用 `npx` 运行一次性 CLI 工具。

## 什么时候不用

- 只需要设置 API key、token 或服务地址时，用 `SetEnvVar`，不要改 `.env/`。
- 需要系统库、GPU、浏览器或固定 Linux 镜像时，用 Docker 沙盒资源。
- 只跑一次重依赖命令时，优先用 `npx`，不要污染 `workspace-default`。
- 不要修改 `apps/backend/node_modules`。那是 AIASys 后端自身运行环境。

## 常用操作

查看当前工作区环境：

```json
{
  "action": "list",
  "inspect": true
}
```

创建或刷新默认 Node 环境：

```json
{
  "action": "ensure_node",
  "env_id": "workspace-default",
  "display_name": "Workspace Node",
  "node_version": "20.x",
  "packages": ["typescript", "eslint"],
  "sync": true,
  "activate": true
}
```

安装依赖：

```json
{
  "action": "install_packages",
  "env_id": "workspace-default",
  "packages": ["next", "react"],
  "sync": true
}
```

绑定环境为工作区默认：

```json
{
  "action": "bind",
  "env_id": "workspace-default"
}
```

检查单个环境：

```json
{
  "action": "inspect",
  "env_id": "workspace-default"
}
```

取消登记：

```json
{
  "action": "unregister",
  "env_id": "workspace-default"
}
```

`unregister` 只取消登记和默认绑定，不保证删除所有 `.env/` 物料。清理大体积目录前，先确认没有运行中的会话还在使用这个环境。

## 依赖管理规则

- 常用工具和框架写进 `workspace-default`，例如 `express`、`next`、`typescript`。
- 项目复现需要固定版本时，在安装包名里写版本约束，例如 `react@18.2.0`。
- 执行一次性 CLI 工具时优先使用 `npx <package>` 或 `npx --package <package> <command>`，不要全局安装。
- 安装失败时先检查包名、Node 版本、网络和平台支持，再考虑 Docker。
- 修改环境后，当前正在执行的轮次不承诺热更新。下一次执行或重建运行态后再稳定使用新环境。

## 和环境变量配合

Node.js 包和 API key 分开管理。

需要 `OPENAI_API_KEY`、`GITHUB_TOKEN`、代理地址或数据库连接串时，用环境变量工具：

```json
{
  "name": "OPENAI_API_KEY",
  "value": "sk-..."
}
```

工作区变量写入 `.workspace/workspace.json` 的 `runtime_binding.env_vars`。全局变量和工作区变量会在执行时合并，工作区同名变量优先。

## 故障处理

| 现象 | 处理 |
|------|------|
| `fnm CLI 不可用` | 当前机器缺少 fnm，先向用户说明运行环境缺口。桌面或服务器部署需要补 fnm。 |
| `npm install` 失败 | 检查 Node 版本、包版本、网络和平台支持。 |
| `npx` 不可用 | 确保 Node.js 和 npm 已正确安装，`npx` 通常随 npm 一起提供。 |
| 全局包冲突 | 项目级依赖优先用 `npm install` 安装到本地 `.node_modules/`，不要用 `npm install -g` 污染全局。 |
| Docker 中找不到 `.env/.node_modules` | Docker 不复用宿主机 Node 环境，容器内依赖要由镜像或容器内命令提供。 |

## 相关 Skill

| Skill | 用途 |
|-------|------|
| `aiasys-platform-skill` | 平台总览、环境变量、Docker 沙盒、数据表、知识资源 |
| `competition-research-skill` | 竞赛项目和自动实验工作流 |
| `pdf-translate-skill` | 示例：用 `npx` 隔离运行一次性工具 |

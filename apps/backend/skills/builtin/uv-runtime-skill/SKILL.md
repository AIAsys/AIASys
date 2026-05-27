+++
name = "UV 运行环境"
description = "管理当前 AIASys 工作区的 Python/UV 运行环境。适用于用户询问怎么使用 uv、\n怎么安装 Python 依赖、怎么检查 workspace-default 环境、为什么工作区有 .env 目录、\n或需要把 Notebook、IPython、普通 Python 脚本绑定到工作区环境时使用。"
+++


# UV 运行环境 Skill

这个 skill 只负责当前工作区的 Python/UV 运行环境。平台总览、Docker 沙盒、环境变量和数据表仍由 `aiasys-platform-skill` 说明。

## 先分清三件事

| 名称 | 作用 | 位置或入口 |
|------|------|------------|
| UV 环境物料 | Python 版本、依赖声明、锁文件和虚拟环境 | 工作区 `.env/` |
| 工作区环境变量 | API key、token、服务地址等运行时变量 | `.workspace/workspace.json` 的 `runtime_binding.env_vars` |
| 一次性工具 | 临时运行重依赖 CLI，不污染工作区默认环境 | `uvx` 或 `uv tool run` |

`.env/` 是 AIASys 管理的工作区 UV 物料目录，不是传统 dotenv 文件。不要把 API key 写进 `.env/pyproject.toml` 或 `.env/uv.lock`。

## 默认目录

AIASys 管理的默认 UV 环境会落在当前工作区根目录：

```text
.env/
├── environments.json
├── pyproject.toml
├── uv.lock
├── .python-version
└── .venv/
```

默认环境 ID 是 `workspace-default`。系统会把真实解释器记录为 `.env/.venv/bin/python`，Windows 下是 `.env/.venv/Scripts/python.exe`。

不要直接编辑 `.env/environments.json`。创建、绑定、安装和检查都通过 `RuntimeEnvironment` 工具完成。

## 什么时候用

- 用户要运行 Python、Notebook、IPython 或数据分析脚本。
- 缺少 Python 包，需要安装到当前工作区。
- 要确认当前会话是否绑定了 Python 环境。
- 要切换或检查 `workspace-default`。
- 要解释工作区里的 `.env/`、`.venv/`、`pyproject.toml` 或 `uv.lock`。

## 什么时候不用

- 只需要设置 API key、token 或服务地址时，用 `SetEnvVar`，不要改 `.env/`。
- 需要系统库、GPU、浏览器或固定 Linux 镜像时，用 Docker 沙盒资源。
- 只跑一次重依赖命令时，优先用 `uvx` 或 `uv tool run`，不要污染 `workspace-default`。
- 不要修改 `apps/backend/.venv`。那是 AIASys 后端自身运行环境。

## 常用操作

查看当前工作区环境：

```json
{
  "action": "list",
  "inspect": true
}
```

创建或刷新默认 UV 环境：

```json
{
  "action": "ensure_uv",
  "env_id": "workspace-default",
  "display_name": "Workspace UV",
  "python_version": "3.11",
  "packages": ["pandas", "numpy"],
  "create_venv": true,
  "sync": true,
  "activate": true
}
```

安装依赖：

```json
{
  "action": "install_packages",
  "env_id": "workspace-default",
  "packages": ["scikit-learn", "xgboost"],
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

- 常用分析依赖写进 `workspace-default`，例如 `pandas`、`numpy`、`scikit-learn`。
- 项目复现需要固定版本时，在安装包名里写版本约束，例如 `xgboost==2.1.4`。
- 执行一次性 CLI 工具时优先使用 `uvx --from <package> <command>` 或 `uv tool run --from <package> <command>`。
- 安装失败时先检查包名、Python 版本、网络和平台支持，再考虑 Docker。
- 修改环境后，当前正在执行的轮次不承诺热更新。下一次执行或重建运行态后再稳定使用新环境。

## 和环境变量配合

Python 包和 API key 分开管理。

需要 `OPENAI_API_KEY`、`PADDLEOCR_TOKEN`、代理地址或数据库连接串时，用环境变量工具：

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
| `uv CLI 不可用` | 当前机器缺少 uv，先向用户说明运行环境缺口。桌面或服务器部署需要补 uv。 |
| `uv sync` 失败 | 检查 Python 版本、包版本、网络和平台 wheel。 |
| `python` 可用但 `pip` 不可用 | 不要直接用 `pip`，改用 `RuntimeEnvironment install_packages` 或 `uv pip`。 |
| Notebook 没读到新依赖 | 重建或重新绑定运行态后再执行。 |
| Docker 中找不到 `.env/.venv` | Docker 不复用宿主机 UV 环境，容器内依赖要由镜像或容器内命令提供。 |

## 相关 Skill

| Skill | 用途 |
|-------|------|
| `aiasys-platform-skill` | 平台总览、环境变量、Docker 沙盒、数据表、知识资源 |
| `competition-research-skill` | 竞赛项目和自动实验工作流 |
| `pdf-translate-skill` | 示例：用 `uvx` 隔离运行 pdf2zh |

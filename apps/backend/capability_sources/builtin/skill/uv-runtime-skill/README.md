# UV 运行环境

管理当前 AIASys 工作区的 Python/UV 运行环境。包括依赖安装、环境绑定、版本锁定和导入验证。

## 适用场景

- 安装 Python 依赖包
- 检查和管理 `workspace-default` 环境
- 理解工作区 `.env/` 目录的用途
- 把 Notebook、IPython、Python 脚本绑定到工作区环境

## 核心概念

| 名称 | 作用 | 位置 |
|------|------|------|
| UV 环境物料 | Python 版本、依赖声明、锁文件和虚拟环境 | 工作区 `.env/` |
| 工作区环境变量 | API key、token 等运行时变量 | `.workspace/workspace.json` |
| 一次性工具 | 临时运行重依赖 CLI，不污染默认环境 | `uvx` 或 `uv tool run` |

## 注意事项

- `.env/` 是 AIASys 管理的 UV 物料目录，不是传统 dotenv 文件
- 不要把 API key 写进 `.env/pyproject.toml` 或 `.env/uv.lock`

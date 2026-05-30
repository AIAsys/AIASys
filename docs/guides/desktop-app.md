# 桌面应用

AIASys 桌面版基于 Electron，提供原生窗口、系统托盘和自动端口管理。日常使用优先推荐桌面版，Web 版适合临时访问和远程场景。

> **前置要求**：Python 3.12+、Node.js 22+、npm。详见 [快速启动指南](QUICKSTART.md)。

## 启动

```bash
cd apps/desktop
npm install
npm run dev
```

桌面版自动管理前后端服务的启动和端口。如果后端（13001）或前端（13000）已在运行，桌面版会复用现有服务，不会重复启动。

## 自动服务管理

桌面版启动时会检查后端和前端是否已在运行：

- 已运行：直接连接现有服务
- 未运行：自动启动后端和前端，退出时自动关闭

用户不需要手动管理 `uvicorn` 和 `npm run dev` 进程，桌面版统一处理。

## 默认端口

| 服务 | 端口 |
|------|------|
| 前端 | 13000 |
| 后端 | 13001 |

## 端口冲突处理

如果默认端口被占用，桌面版自动查找下一个可用端口。前端和后端的端口冲突独立处理，互不影响。

## 平台支持

桌面版支持 Windows、macOS、Linux 三端。

Python 路径自动检测：

- **Windows**：查找 `Scripts/python.exe`
- **macOS / Linux**：查找 `bin/python`

不需要手动配置 Python 路径。

## 打包模式

打包后的桌面版（`npm run build` 产物）将后端运行时外置到用户目录，不在安装包内写运行时数据。升级桌面版不会覆盖用户的后端配置和运行时文件。

各平台运行时目录：

- Linux：`~/.config/aiasys-desktop/backend-runtime/`
- macOS：`~/Library/Application Support/aiasys-desktop/backend-runtime/`
- Windows：`%APPDATA%/aiasys-desktop/backend-runtime/`

（Electron 通过 `app.getPath("userData")` 自动获取，各平台映射到正确路径。）

## 远程调试

设置环境变量 `AIASYS_DESKTOP_REMOTE_DEBUGGING_PORT` 开启 Electron 远程调试：

```bash
# Linux/macOS
export AIASYS_DESKTOP_REMOTE_DEBUGGING_PORT=9222
npm run dev

# Windows CMD
set AIASYS_DESKTOP_REMOTE_DEBUGGING_PORT=9222
npm run dev
```

## 无头环境

Linux 环境下如果没有可用的显示服务器（`DISPLAY` 环境变量不存在），桌面版自动禁用 GPU 加速，以无头模式运行。

## 启动路径

桌面版默认打开 `/workspace` 页面。如需覆盖，设置环境变量：

```bash
# Linux/macOS
export AIASYS_DESKTOP_START_PATH=/some-other-path

# Windows CMD
set AIASYS_DESKTOP_START_PATH=/some-other-path
```

## 与 Web 版的区别

| 特性 | 桌面版 | Web 版 |
|------|--------|--------|
| 原生窗口 | 有 | 无（浏览器标签页） |
| 系统托盘 | 有 | 无 |
| 自动端口管理 | 有 | 无（需手动启动前后端） |
| 适用场景 | 日常使用 | 临时访问、远程使用 |
| 前端代码 | 与 Web 版共用 | 与桌面版共用 |

两个版本共享同一套前端代码（`apps/web/src/`），桌面版通过 Electron 加载前端页面，功能和交互完全一致。
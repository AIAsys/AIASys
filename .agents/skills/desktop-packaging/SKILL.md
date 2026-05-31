---
name: desktop-packaging
description: |
  AIASys Desktop 打包规范与操作指南。覆盖 Electron + Python backend 的三端（Linux/macOS/Windows）
  打包流程、已知坑、构建脚本和验证清单。用于新增打包功能、排查打包问题、或添加新平台支持时。
---

# AIASys Desktop 打包规范

## 架构概述

AIASys Desktop 是 Electron 薄壳，复用 `apps/web` 作为 renderer，Python FastAPI 作为 backend。

```
Electron Main Process
  ├── service-manager.cjs  (启动/管理 backend + frontend 服务)
  ├── main.cjs             (窗口管理 + 系统托盘)
  ├── preload.cjs          (renderer 安全暴露)
  └── resources/
      ├── web/             (web dist + local_preview_server.py)
      └── backend/         (Python venv + 源码 + templates + skills)
```

## 核心约束

### 数据隔离（代码只读，数据可写）

所有可变数据（数据库、日志、上传文件、会话历史）必须写入用户目录。代码目录（`resources/app`、`resources/backend`）在生产环境中视为只读。

运行时数据目录：
- Linux: `~/.config/aiasys-desktop/backend-runtime/`
- Windows: `%APPDATA%/AIASys Desktop/backend-runtime/`
- macOS: `~/Library/Application Support/aiasys-desktop/backend-runtime/`

启动时自动创建所需的运行时目录结构（`data/`、`logs/`、`workspaces/`）。

## 三端打包策略

| 平台 | 目标格式 | 构建命令 | 状态 |
|------|----------|----------|------|
| Linux | `dir` (目录版) | `npm run dist:linux:dir` | 已验证 |
| Linux | `AppImage` | `npm run dist:ci:linux` | 配置完成，待验证 |
| Windows | `nsis` (安装包) | `npm run dist:win` | 配置完成，待 Windows 环境验证 |
| Windows | `zip` (便携版) | `npm run dist:win` | 配置完成 |
| macOS | `dmg` | `npm run dist:mac` | 配置完成，待验证 |
| macOS | `zip` | `npm run dist:mac` | 配置完成 |

## 构建流程

```bash
cd apps/desktop

# 1. 构建 web dist
npm run build:web

# 2. 准备运行时（staging 到 .dist/）
npm run prepare:runtime

# 3. 打包（以 Windows NSIS 为例）
npm run dist:win
```

`prepare-runtime.cjs` 的职责：
1. 清理 `__pycache__` 和 `.pyc` 文件
2. 复制 `apps/web/dist` 到 `.dist/web/`
3. 复制 backend 必需文件到 `.dist/backend/`（.venv、app、vendor、skills 等）
4. 创建空的数据/日志/工作区目录

## 关键配置

### package.json (electron-builder)

- `appId`: `com.aiasys.desktop`
- `productName`: `AIASys Desktop`
- `extraResources`: 从 `.dist/web` 和 `.dist/backend` 复制到 `resources/`
- `files`: 只包含 `src/`、`build/`、`package.json`（主进程代码和图标）

### NSIS (Windows)

- `oneClick: false` — 允许用户选择安装目录
- `allowToChangeInstallationDirectory: true`
- `requestedExecutionLevel: "asInvoker"` — 不请求管理员权限（避免拖放文件失效）
- `license`: `build/license.txt` — GBK 编码的中文许可协议
- `include`: `build/installer.nsh` — 自定义脚本

### installer.nsh 功能

- 安装前检测并终止正在运行的 `AIASys Desktop.exe`
- 卸载前终止运行中的进程
- 卸载时询问是否删除用户数据（`%APPDATA%/AIASys Desktop`）

## 已知坑与解决方案

### 1. 跨平台 .venv 问题

**问题**: 在 Linux 上构建 Windows 安装包时，`.venv` 包含的是 Linux 平台的 Python 解释器（`bin/python`），Windows 上无法运行。

**解决**: 每个平台必须在对应平台上构建，或在 CI 中使用对应平台的 runner。`service-manager.cjs` 会检测平台不匹配并抛出明确错误。

### 2. Windows 控制台黑窗

**问题**: `spawn` 默认在 Windows 会弹出 cmd 窗口。

**解决**: `spawn` 参数必须包含 `windowsHide: true` + `stdio: "pipe"`。

### 3. Windows 端口占用检测

**问题**: Linux 用 `lsof`，Windows 没有该命令。

**解决**: Windows 用 `netstat -ano` 获取 PID，再用 `tasklist` 获取进程名。`service-manager.cjs` 的 `readListeningProcessWindows()` 已实现。

### 4. 子进程崩溃干等

**问题**: `waitForUrl` 轮询期间子进程崩溃，会等到 90 秒超时。

**解决**: `waitForUrl` 每次轮询检查 `child.exitCode !== null`，崩溃时立即抛出。

### 5. 日志持久化

**问题**: `stdio: "inherit"` 时输出只到控制台，无持久日志。

**解决**: `stdio: "pipe"` + 手动 pipe 到日志文件（`{logsDir}/{name}-spawn.log`）。同时保留控制台输出。

### 6. 系统托盘

**问题**: 关闭窗口即退出应用，用户期望最小化到托盘。

**解决**: `main.cjs` 中 `close` 事件拦截（`!isQuitting` 时 `event.preventDefault() + win.hide()`），托盘右键菜单提供"显示窗口/打开日志目录/打开数据目录/退出"。

## 验证清单

构建完成后必须检查：

- [ ] 安装包/目录产物存在
- [ ] 安装后/解压后 `resources/backend/.venv/.../python` 可执行
- [ ] 首次启动不报错
- [ ] backend 运行态写入用户目录，不写回安装目录
- [ ] 关闭窗口后托盘图标存在
- [ ] 托盘右键"退出"能彻底结束所有子进程
- [ ] 卸载后无残留进程
- [ ] （Windows）安装时可选目录
- [ ] （Windows）卸载时询问是否删数据

## 相关文件

| 文件 | 作用 |
|------|------|
| `apps/desktop/src/main.cjs` | 主进程、窗口、托盘 |
| `apps/desktop/src/service-manager.cjs` | 服务生命周期、端口管理、进程检测 |
| `apps/desktop/src/preload.cjs` | renderer 安全暴露 |
| `apps/desktop/scripts/prepare-runtime.cjs` | 构建前 staging |
| `apps/desktop/scripts/launch.cjs` | dev/preview 启动器 |
| `apps/desktop/package.json` | electron-builder 配置 |
| `apps/desktop/build/installer.nsh` | NSIS 自定义脚本 |
| `apps/desktop/build/license.txt` | 安装许可（GBK 编码）|
| `apps/desktop/build/icon.*` | 应用图标 |

## 扩展指南

### 添加新平台支持

1. 在 `package.json` 的 `build` 下添加目标平台配置
2. 在 `scripts` 中添加对应的 `dist:*` 命令
3. 在 `service-manager.cjs` 中验证平台特定逻辑（进程检测、路径分隔符等）
4. 更新本 skill 的三端策略表格

### 修改打包行为

1. 修改 `prepare-runtime.cjs` 调整 staging 内容
2. 修改 `package.json` 的 `extraResources` 或 `files` 调整打包包含项
3. 修改 `service-manager.cjs` 调整运行时行为
4. 同步更新本 skill 的"已知坑"章节

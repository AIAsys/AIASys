# 桌面应用

AIASys 桌面版基于 Electron，提供原生窗口、系统托盘和自动端口管理。日常使用优先推荐桌面版，Web 版适合临时访问和远程场景。

> **前置要求**：Python 3.12+、Node.js 22+、npm。详见 [快速启动指南](QUICKSTART.md)。

## 启动

```bash
cd apps/desktop
npm install
npm run dev
```

桌面版自动管理前后端服务的启动和端口。如果后端（13011）或前端（13010）已在运行，桌面版会复用现有服务，不会重复启动。

## 自动服务管理

桌面版启动时会检查后端和前端是否已在运行：

- 已运行：直接连接现有服务
- 未运行：自动启动后端和前端，退出时自动关闭

用户不需要手动管理 `uvicorn` 和 `npm run dev` 进程，桌面版统一处理。

## 默认端口

桌面版使用独立的端口范围，与 Web 版（`dev.sh`）互不冲突：

| 服务 | 桌面版 | Web 版（dev.sh） |
|------|--------|-------------------|
| 前端 | 13010 | 13000 |
| 后端 | 13011 | 13001 |

桌面版启动时会占用这两个端口。如果端口已被占用（包括被其他桌面版实例占用），自动查找下一个可用端口。

## 端口冲突处理

如果默认端口被占用，桌面版自动查找下一个可用端口。前端和后端的端口冲突独立处理，互不影响。

## 平台支持

桌面版支持 Windows、macOS、Linux 三端。

Python 路径自动检测：

- **Windows**：查找 `Scripts/python.exe`
- **macOS / Linux**：查找 `bin/python`

不需要手动配置 Python 路径。

### Windows 编码兼容性

Windows 系统默认使用 cp936（GBK）编码，与 Linux/macOS 的 UTF-8 不同。桌面版在 Windows 上做了以下适配：

- 子进程输出使用智能解码：尝试 UTF-8 → locale 编码（cp936）→ GBK → UTF-8 replace
- 构造 Windows 命令行时避免使用 `shlex.quote`（单引号会损坏 cmd.exe），改用双引号或 `subprocess.list2cmdline`
- 日志文件统一使用 UTF-8 编码，确保跨平台一致性

后端开发者在编写涉及 subprocess 的工具时，需要遵循相同的编码处理策略。

## 打包与安装

### 构建命令

```bash
cd apps/desktop

# Linux 目录版
npm run dist:linux:dir

# Windows NSIS 安装包 + 便携版 zip
npm run dist:win

# macOS dmg + zip
npm run dist:mac
```

构建流程：`build:web`（构建前端）→ `prepare:runtime`（staging 后端运行时）→ `electron-builder`（打包）。

### 打包特性

- 后端运行时外置到用户目录，不在安装包内写运行时数据
- `prepare-runtime.cjs` 自动清理 `__pycache__` 和 `.pyc` 文件
- 升级桌面版不会覆盖用户的后端配置和运行时文件

### 各平台产物

| 平台 | 产物 | 说明 |
|------|------|------|
| Linux | `dist/linux-unpacked/aiasys-desktop` | 目录版，直接运行 |
| Linux | `dist/AIASys-x.x.x-linux.zip` | 绿色版 zip（推荐 AI/自动化安装） |
| Linux | `dist/AIASys-x.x.x.AppImage` | 单文件可执行（CI 构建） |
| Windows | `dist/AIASys Setup x.x.x.exe` | NSIS 安装程序，可选安装目录（推荐 AI/自动化安装） |
| Windows | `dist/AIASys-x.x.x-win.zip` | 绿色版 zip（fallback） |
| macOS | `dist/AIASys-x.x.x-mac.zip` | 绿色版 zip（推荐 AI/自动化安装） |
| macOS | `dist/AIASys-x.x.x.dmg` | 磁盘映像安装包 |

### 使用安装脚本（推荐）

三端统一使用 `apps/desktop/scripts/install.cjs` 安装：

```bash
# Windows（优先 .exe NSIS 安装包）
node apps/desktop/scripts/install.cjs "dist/AIASys Setup 0.4.34.exe"

# Windows（fallback: 绿色版 zip）
node apps/desktop/scripts/install.cjs dist/AIASys-0.4.34-win.zip

# macOS
node apps/desktop/scripts/install.cjs dist/AIASys-0.4.34-mac.zip

# Linux
node apps/desktop/scripts/install.cjs dist/AIASys-0.4.34-linux.zip
```

脚本会自动完成：终止运行中的 AIASys、备份旧版本、解压、创建快捷方式 / `.desktop` 入口、验证关键文件。

默认安装路径：

| 平台 | 默认路径 |
|------|---------|
| Windows | `%LOCALAPPDATA%\Programs\AIASys` |
| macOS | `/Applications/AIASys.app` |
| Linux | `~/.local/share/AIASys` |

指定自定义路径：

```bash
node apps/desktop/scripts/install.cjs "dist/AIASys Setup 0.4.34.exe" "C:\tools\AIASys"
```

### Windows 安装包特性

- 允许用户选择安装目录（非一键安装）
- 不需要管理员权限（避免拖放文件到应用失效）
- 安装前自动检测并关闭运行中的 AIASys
- 卸载时询问是否删除用户数据（`%APPDATA%/aiasys-desktop`）

### 各平台运行时目录

- Linux：`~/.config/aiasys-desktop/backend-runtime/`
- macOS：`~/Library/Application Support/aiasys-desktop/backend-runtime/`
- Windows：`%APPDATA%/aiasys-desktop/backend-runtime/`

（Electron 通过 `app.getPath("userData")` 自动获取，各平台映射到正确路径。）

### 跨平台构建限制

Windows 安装包必须在 Windows 环境（或 Windows CI runner）上构建。在 Linux/macOS 上交叉构建会产生含 Linux venv 的无效产物，Windows 上无法运行。Linux 和 macOS 同理。

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

## 系统托盘

关闭窗口时，应用会隐藏到系统托盘而不是退出。

托盘右键菜单：
- **显示窗口**：恢复主窗口
- **打开日志目录**：打开 backend 运行日志文件夹
- **打开数据目录**：打开用户数据根目录
- **退出**：彻底结束所有子进程并退出应用

## 日志

子进程（backend、frontend）的 stdout/stderr 同时输出到控制台和持久化日志文件：

```
{userData}/backend-runtime/logs/backend-spawn.log
{userData}/backend-runtime/logs/frontend-spawn.log
```

启动失败时，错误对话框会显示日志目录路径，并自动打开该目录。

## 与 Web 版的区别

| 特性 | 桌面版 | Web 版 |
|------|--------|--------|
| 原生窗口 | 有 | 无（浏览器标签页） |
| 系统托盘 | 有 | 无 |
| 自动端口管理 | 有 | 无（需手动启动前后端） |
| 离线运行 | 有（安装后无需网络） | 需网络（若部署在远程） |
| 适用场景 | 日常使用 | 临时访问、远程使用 |
| 前端代码 | 与 Web 版共用 | 与桌面版共用 |

两个版本共享同一套前端代码（`apps/web/src/`），桌面版通过 Electron 加载前端页面，功能和交互完全一致。
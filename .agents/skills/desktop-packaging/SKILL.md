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

## Windows 打包工作流

Windows 安装包必须在 Windows 侧构建。根据代码存放位置不同，有两种工作模式。

---

### 模式 A：代码在 WSL，Windows 侧编译（推荐）

AIASys 日常开发在 WSL，代码放在 WSL 文件系统里。Windows 通过 `\\wsl$\` 访问同一份代码，两边实时同步。

**环境分工**

| 环境 | 职责 | 为什么 |
|------|------|--------|
| WSL | 代码编辑、前后端服务调试、git 操作 | 开发主阵地 |
| Windows | Electron 主进程调试、安装包构建 | 必须验证真实的 Windows 行为 |

**前置条件（Windows 侧）**

- Node.js >= 20
- Python 3.11+（用于创建 Windows 版 .venv）
- Git（可选）

**完整构建步骤**

```powershell
# 1. 进入项目路径（通过 \\wsl$\ 访问 WSL 文件）
cd "\\wsl$\Ubuntu\home\ke\projects\AIASys\apps\desktop"

# 2. 安装 desktop 的 node_modules（Windows 侧独立安装，不和 WSL 共享）
npm install

# 3. 准备后端 .venv（必须在 Windows 上创建，不能复用 WSL 的）
cd "..\backend"
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
python -m venv .venv
.venv\Scripts\activate
uv pip install -e .
# 或: pip install -e .

# 4. 构建前端（WSL 里做也行，Windows 做也行）
cd "..\web"
npm install
npm run build

# 5. 准备运行时
cd "..\desktop"
npm run prepare:runtime
# 预期输出：
# [aiasys-desktop] 嵌入完整 Python 运行时: ... -> ...\.dist\backend\.venv\python

# 6. 验证嵌入 Python
ls .dist\backend\.venv\python\python.exe

# 7. 打包
npm run dist:win
# 产物：dist\AIASys Desktop Setup 0.4.0.exe
```

**关键注意**

- .venv 必须在 Windows 上重建（WSL 的是 Linux 版）
- node_modules 不跨环境共享（WSL 和 Windows 各自独立安装）
- prepare-runtime 必须在 Windows 上执行（才会嵌入 Windows 版 Python）
- WSL 修改的代码 Windows 实时可见，修改后重启 Electron 即可

---

### 模式 B：代码在 Windows 本地，直接编译

代码直接 clone 到 Windows 本地目录（如 `C:\Users\ke\projects\AIASys`），不涉及 WSL。

**适用场景**

- 团队成员只在 Windows 上工作
- CI/CD 在 Windows runner 上执行
- 不需要 WSL 开发环境

**前置条件**

- Node.js >= 20
- Python 3.11+
- Git

**完整构建步骤**

```powershell
# 1. 克隆代码（或进入已有目录）
cd "C:\Users\ke\projects"
git clone https://github.com/AIAsys/AIASys.git
cd AIASys\apps\desktop

# 2. 安装 desktop 依赖
npm install

# 3. 准备后端 .venv
cd "..\backend"
python -m venv .venv
.venv\Scripts\activate
uv pip install -e .
# 或: pip install -e .

# 4. 构建前端
cd "..\web"
npm install
npm run build

# 5. 准备运行时并打包
cd "..\desktop"
npm run prepare:runtime
npm run dist:win
```

**两种模式对比**

| 项 | 模式 A（WSL 代码） | 模式 B（Windows 本地） |
|----|-------------------|----------------------|
| 代码位置 | WSL 文件系统 | Windows 本地磁盘 |
| 进入路径 | `\\wsl$\Ubuntu\...` | `C:\Users\ke\...` |
| 代码编辑 | WSL 侧（vim/vscode） | Windows 侧（任意编辑器） |
| git 操作 | WSL 侧 | Windows 侧 |
| 前后端调试 | WSL 侧 `npm run dev` | Windows 侧 `npm run dev` |
| 打包 | Windows 侧 `npm run dist:win` | Windows 侧 `npm run dist:win` |

两种模式的打包命令和验证流程完全一致，唯一区别是代码存放位置和日常开发环境。

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

**WSL + Windows 双环境开发时的具体做法**：
- WSL 负责代码编辑和前后端服务调试
- Windows 负责 `python -m venv .venv`、`.venv\Scripts\activate`、`npm run dist:win`
- 详见上文"模式 A：代码在 WSL，Windows 侧编译"

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

### Windows 安装包专项验证

在无 Python 环境的 Windows 机器（或虚拟机）上测试：

1. **安装前确认目标机器没有 Python**
   ```powershell
   python --version
   # 应该报错"python 不是内部或外部命令"
   ```

2. **安装并启动**
   - 双击 `.exe` 安装包，确认能选择安装目录
   - 从开始菜单启动，等待 10~30 秒，确认主界面正常显示

3. **嵌入 Python 验证**
   - 检查安装目录 `resources/backend/.venv/python/python.exe` 存在
   - 检查 `%APPDATA%\AIASys Desktop\backend-runtime\logs\backend-spawn.log` 无 Python 路径错误

4. **功能验证**
   - 关闭窗口 → 托盘图标仍在
   - 托盘右键菜单含：显示窗口 / 打开日志目录 / 打开用户配置 / 打开工作区目录 / 退出
   - 托盘 → 退出 → 任务管理器无残留进程
   - 卸载 → 弹窗询问是否删除用户数据 → 选"是" → `%APPDATA%\AIASys Desktop` 被删除

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

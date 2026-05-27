# AIASys Desktop

第一阶段 Electron desktop 薄壳。

## 目标

- 复用现有 `apps/web` 作为唯一 renderer
- 开发态复用 Vite dev server
- 预览态复用 `apps/web/dist` + 本地代理
- 不在本阶段引入第二套桌面前端

## 命令

先安装 desktop 依赖：

```bash
cd apps/desktop
npm install
```

开发态：

```bash
cd apps/desktop
npm run dev
```

这个命令会：

- 优先复用已运行的 `127.0.0.1:13001` backend 和 `127.0.0.1:13000` frontend
- 如未运行，则自动拉起 backend 和 `apps/web` 的 Vite dev server
- 默认端口若被其他 checkout 占用，会自动回退到新的空闲端口
- 然后打开 Electron 窗口

常用调试环境变量：

```bash
AIASYS_DESKTOP_OPEN_DEVTOOLS=0
AIASYS_DESKTOP_REMOTE_DEBUGGING_PORT=9224
AIASYS_DESKTOP_DISABLE_GPU=1
AIASYS_DESKTOP_ELECTRON_ARGS="--disable-gpu --remote-debugging-port=9224"
```

预览态：

```bash
cd apps/desktop
npm run build:web
npm run start
```

这个命令会：

- 优先复用已运行的 backend / frontend
- 若未运行，则自动拉起 backend
- 默认端口若被其他 checkout 占用，会自动回退到新的空闲端口
- 启动 `apps/web/scripts/local_preview_server.py` 承接 `apps/web/dist`
- 通过本地代理把 `/api` 和 `/health` 转发到 backend

如果你显式设置了 `AIASYS_DESKTOP_FRONTEND_PORT` / `AIASYS_DESKTOP_BACKEND_PORT`，
desktop 会把它们视为锁定端口；这时若端口被其他进程占用，会直接报错而不是自动换端口。

## 当前范围

- 已覆盖 desktop 骨架、开发态和预览态入口
- 已覆盖 Linux `dir` 目录版打包，可产出 `dist/linux-unpacked/`
- 当前 Linux 目录版会把 `apps/web/dist` 与 backend runtime 一起打进 `resources/web` / `resources/backend`
- backend runtime 当前复用打包时的 `.venv` 与源码树，体积较大，但已能在 WSL 中完成真实启动验证
- packaged 模式会把 backend 运行态目录外置到用户目录，而不是写回 `resources/backend`
- 尚未覆盖 AppImage / deb、代码签名、自动更新、正式发行

## Linux 目录版

打包命令：

```bash
cd apps/desktop
npm run dist:linux:dir
```

当前产物：

```bash
apps/desktop/dist/linux-unpacked/aiasys-desktop
```

当前实现说明：

- 先构建 `apps/web/dist`
- 再把 `web dist + local_preview_server.py` 复制到 `apps/desktop/.dist/web`
- 把 backend 源码、`vendor`、`config.json` 和 `.venv` 复制到 `apps/desktop/.dist/backend`
- packaged 模式下从 `process.resourcesPath/web` 与 `process.resourcesPath/backend` 启动，不再依赖仓库根路径
- backend 的 `data / workspaces / logs` 会外置到 `~/.config/aiasys-desktop/backend-runtime/`
- 首次启动时由 packaged backend 自己在外置目录生成 `app.db`、`llm_config.json` 等运行态文件

当前已验证：

- `linux-unpacked` binary 可在 WSL + `xvfb-run` 下启动
- packaged backend 会从 `resources/backend/.venv/bin/python` 拉起
- packaged preview frontend 会从 `resources/web/dist` 提供 `/analysis`
- packaged backend 运行态会写入 `~/.config/aiasys-desktop/backend-runtime/`，不会继续写回包内 `resources/backend/data`
- 页面可真实渲染，并可进行基础输入交互
- `resources/web/scripts/local_preview_server.py` 现在会对 `/api/agent/execute/stream` 做逐块 flush，packaged preview 模式下 SSE 不会再卡在代理层
- packaged backend 在“没有显式默认模型、只有默认 provider”时，会优先选择默认 provider 下的第一个启用模型；当前已验证会自动选到 `kimi-kimi-for-coding`
- 通过 Electron renderer 进入工作区后，已可真实发送消息并在页面中看到返回内容，不再长期停留在“正在执行任务”

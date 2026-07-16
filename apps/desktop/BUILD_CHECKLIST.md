# AIASys Windows 离线安装包构建检测清单

> 本文档汇总 Windows 桌面端打包的关键要求与自检项，确保每次自动化构建都能复现、产物可运行。  
> 版本：v0.4.13  
> 适用平台：Windows 10/11 x64

---

## 一、历史问题与当前状态

| # | 历史 BUG | 当前状态 | 说明 |
|---|---|---|---|
| 1 | NSIS `MessageBox` 未转义双引号导致构建失败 | ✅ 已修复 | `installer.nsh` 中字符串已无内部双引号 |
| 2 | NSIS 安装包体积异常（仅 KB 级空壳） | ✅ 已修复 | 构建前清理 `.dist`/`dist`，完整链路构建 |
| 3 | License 中文乱码 | ✅ **本次修复** | `license.txt` 已添加 UTF-8 BOM；`prepare-runtime.cjs` 自动确保编码正确 |
| 4 | 前端 Preview 服务 ROOT 路径错误 | ✅ 已修复 | `local_preview_server.py` 使用 `parent.parent.parent / "dist"` |
| 5 | Shell/Monitor POSIX 命令在 Windows 上执行失败 | ✅ 已修复 | `ShellExecutor` 排除 WSL bash，优先 Git Bash；运行时自动处理 UV+WSL 回退 |
| 6 | 后端启动超时（WMI 卡死） | ✅ 已修复 | `app/main.py` 顶部 monkey-patch `platform._wmi_query` |
| 7 | 构建时文件被锁定 | ⚠️ 需每次清理 | 构建脚本自动/手动杀残留进程、清理 `.dist`/`dist` |
| 8 | winCodeSign 下载超时 | ✅ 已修复 | 必须设置 `ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/` |
| 9 | 子进程输出编码乱码 | ✅ 已修复 | `encoding_utils.py` 的 `smart_decode()` 多级 fallback |
| 10 | `fcntl` 在 Windows 缺失 | ✅ 已修复 | 使用 `filelock` 替代 |
| 11 | Electron 主进程缺少 `fs` 导入 | ✅ 已修复 | `main.cjs` 顶部已导入 `fs` |
| 12 | EXE 无自定义图标 / 图标不一致 | ✅ **本次修复** | `package.json` 移除 `signAndEditExecutable: false`，Windows 使用 `build/icon.ico` |

---

## 二、构建前环境要求

### 必备软件
- Node.js ≥ 18（推荐 v24.x）
- npm ≥ 10
- Python 3.12（开发/构建机使用）
- Git for Windows（提供 Git Bash）
- uv（Python 包管理器）

### 必备环境变量
```powershell
$env:ELECTRON_BUILDER_BINARIES_MIRROR = "https://npmmirror.com/mirrors/electron-builder-binaries/"
```

### 图标统一要求
`package.json` 中 `icon: "build/icon"`，electron-builder 会自动识别：
- Windows: `build/icon.ico`（多尺寸，建议 256×256）
- macOS: `build/icon.icns`
- Linux: `build/icon.png`

> 若更新品牌图标，必须同时更新三个文件。

---

## 三、构建流程（已封装）

```bash
cd apps/desktop
$env:ELECTRON_BUILDER_BINARIES_MIRROR="https://npmmirror.com/mirrors/electron-builder-binaries/"
npm run dist:win
```

等价于：
```bash
npm run build:web      # 构建前端 dist
npm run prepare:runtime # 准备 .dist/backend + .dist/web
npx electron-builder --win nsis --publish=never
```

### prepare-runtime 会自动完成
- 清理 `__pycache__` / `.pyc`
- 确保 `build/license.txt` 带 UTF-8 BOM
- 复制嵌入 Python 运行时
- 修正 `.venv/pyvenv.cfg` 的 `home` 路径
- 清理开发依赖包与无用目录
- 构建前自检（图标、license、NSIS 脚本存在且编码正确）

---

## 四、关键产物验证

构建完成后，必须确认：

| # | 验证项 | 合格标准 |
|---|---|---|
| 1 | NSIS 安装包体积 | `dist/AIASys Setup X.X.X.exe` ≥ 200 MB |
| 2 | ZIP 便携包体积（CI 产物） | `dist/AIASys-X.X.X-win.zip` ≥ 300 MB；本地构建可不产出 |
| 3 | 安装程序可执行 | 双击 `.exe` 正常弹出安装向导 |
| 4 | License 中文正常 | 安装向导许可协议页面显示正常中文 |
| 5 | 安装路径可配置 | 安装向导出现目录选择步骤 |
| 6 | 安装后启动 | 安装完成双击桌面快捷方式，10 秒内进入主界面 |
| 7 | 后端健康检查 | `curl http://127.0.0.1:13011/health` 返回 `{"status":"ok"}` |
| 8 | 卸载数据保留选项 | 卸载时弹出对话框，可选择保留/删除用户数据 |
| 9 | 托盘设置入口 | 右键托盘图标 →「设置」子菜单可打开对应设置面板 |
| 10 | 图标一致性 | 安装图标、桌面快捷方式、任务栏、托盘图标均正确 |

---

## 五、手动排查速查

| 现象 | 诊断 | 解决 |
|---|---|---|
| 构建报错 `EBUSY` / 文件锁定 | 残留 `7za.exe` / `makensis.exe` | 杀进程 → 等待 10s → `rm -rf .dist dist` → 重试 |
| NSIS 报错 `unterminated string` | `installer.nsh` 含未转义 `"` | 确保 `MessageBox` 字符串无内部双引号 |
| 后端启动超时 90s | WMI 服务卡死或僵尸进程 | 确认 `app/main.py` 有 WMI 补丁；清理僵尸进程 |
| License 乱码 | `license.txt` 无 BOM | `prepare-runtime` 会自动处理；手动可用 Python 加 BOM |
| 图标显示默认 Electron 图标 | `signAndEditExecutable: false` | 已在 `package.json` 中移除该字段 |

---

## 六、禁止事项

- ❌ 不要将用户数据写入安装目录（`Program Files` 普通用户不可写）
- ❌ 不要假设目标系统已安装 Python/UV/Node.js
- ❌ 不要在构建时遗漏 `__pycache__` 清理
- ❌ 不要将 `requestedExecutionLevel` 设为 `requireAdministrator`（会破坏拖放兼容性）
- ❌ 不要将无 BOM 的 `license.txt` 直接打包

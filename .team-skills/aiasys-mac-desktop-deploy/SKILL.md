---
name: aiasys-mac-desktop-deploy
description: |
  AIASys Mac 桌面端远程部署与验证。通过 SSH 连接 Mac 设备，
  完成代码同步、依赖安装、Electron 二进制处理、后端 venv 搭建、
  前端构建、桌面应用启动，以及工作区创建验证。
  适用于需要在 Mac 上编译和测试 AIASys 桌面版的场景。
---

# AIASys Mac 桌面端部署

## 前置条件

| 条件 | 说明 |
|------|------|
| Mac SSH 可达 | 已知 Mac 的 IP 地址和 SSH 账号密码 |
| Xcode CLT | Mac 上已安装 Xcode Command Line Tools（`xcode-select -p` 验证） |
| nvm | Mac 上有 nvm（Node 版本管理） |
| WSL 工具 | WSL 上有 `sshpass` 和 `scp` |
| LLM 配置 | `apps/backend/config.json` 已存在且 key 有效，详见 [aiasys-llm-config](../aiasys-llm-config/SKILL.md) |

## 快速开始

以下命令中的 `<IP>`、`<用户>`、`<密码>` 请替换为实际值。

### 1. SSH 连通性检查

```bash
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "echo connected && hostname"
```

### 2. 代码同步（git bundle）

```bash
git bundle create /tmp/AIASys-bundle.bundle dev
scp /tmp/AIASys-bundle.bundle <用户>@<IP>:/tmp/
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  cd ~/projects && rm -rf AIASys && mkdir AIASys && cd AIASys &&
  git init && git fetch /tmp/AIASys-bundle.bundle dev &&
  git checkout -b dev FETCH_HEAD
"
```

### 3. 安装系统依赖

#### Python 3.12

如果 Mac 系统 Python 版本低于 3.12，需要安装：

```bash
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  cd /tmp && curl -L -o python312.pkg 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-macos11.pkg' &&
  sudo installer -pkg python312.pkg -target /
"
```

验证：
```bash
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "/usr/local/bin/python3.12 --version"
```

#### uv（Python 包管理器）

uv 在首次 `pip install` 时会自动安装到 `~/.local/bin/uv`。如果不存在，可从 WSL 复制 vendored 二进制：

```bash
# 查看本地 vendored uv（仅 darwin-arm64 和 darwin-x64）
ls apps/backend/vendor/uv/

# 传输到 Mac
scp apps/backend/vendor/uv/darwin-arm64/uv <用户>@<IP>:~/.local/bin/uv
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "chmod +x ~/.local/bin/uv && ~/.local/bin/uv --version"
```

### 4. 安装 Node 依赖

```bash
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  export NVM_DIR=\$HOME/.nvm && source \$NVM_DIR/nvm.sh &&
  cd ~/projects/AIASys &&
  npm install --prefix apps/web &&
  npm install --prefix apps/desktop &&
  npm approve-scripts electron &&
  npm approve-scripts electron-winstaller
"
```

### 5. Electron 二进制处理

Mac 上 npm 下载 Electron 经常因网络问题失败，需要手动从镜像下载：

```bash
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  cd ~/projects/AIASys/apps/desktop &&
  rm -rf node_modules/electron/dist &&
  export NVM_DIR=\$HOME/.nvm && source \$NVM_DIR/nvm.sh &&
  node -e \"
    const https = require('https');
    const fs = require('fs');
    const url = 'https://npmmirror.com/mirrors/electron/41.2.0/electron-v41.2.0-darwin-arm64.zip';
    const f = fs.createWriteStream('/tmp/electron.zip');
    https.get(url, {headers: {'User-Agent': 'electron-builder'}}, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400) {
        https.get(res.headers.location, {headers: {'User-Agent': 'electron-builder'}}, (r) => r.pipe(f));
      } else { res.pipe(f); }
    }).on('error', e => console.error(e));
    f.on('finish', () => { f.close(); console.log('Downloaded:', fs.statSync('/tmp/electron.zip').size); });
  \"
"
```

解压并写入 path.txt：

```bash
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  cd ~/projects/AIASys/apps/desktop &&
  mkdir -p node_modules/electron/dist &&
  unzip -q /tmp/electron.zip -d node_modules/electron/dist &&
  printf 'Electron.app/Contents/MacOS/Electron' > node_modules/electron/path.txt
"
```

> **注意**：`path.txt` 必须用 `printf` 写入（`echo` 会带 `\n` 换行导致 spawn 路径错误）。

### 6. 后端环境搭建

```bash
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  cd ~/projects/AIASys/apps/backend &&
  ~/.local/bin/uv --version &&
  ~/.local/bin/uv venv .venv --python 3.12 &&
  ~/.local/bin/uv pip install -r pyproject.toml --python .venv/bin/python3
"
```

### 7. 配置与目录准备

```bash
# 同步配置文件（config.json 不在仓库中，需单独传输）
scp apps/backend/config.json <用户>@<IP>:~/projects/AIASys/apps/backend/config.json

# 创建必要目录
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  cd ~/projects/AIASys/apps/backend &&
  mkdir -p data workspaces logs
"
```

### 8. 启动应用

```bash
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  cd ~/projects/AIASys &&
  export NVM_DIR=\$HOME/.nvm && source \$NVM_DIR/nvm.sh &&
  cd apps/desktop &&
  nohup npm run dev > /tmp/aiasys-desktop.log 2>&1 &
  echo 'PID:' \$!
"
```

等待启动（约 15 秒）：

```bash
sleep 12
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "cat /tmp/aiasys-desktop.log | tail -20"
```

期望看到：
- `Uvicorn running on http://127.0.0.1:13011`
- `VITE v7.1.11 ready`
- `[aiasys-desktop] bootstrap complete`

### 9. 创建工作区验证

```bash
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  curl -s -X POST http://127.0.0.1:13011/api/workspaces \
    -H 'Content-Type: application/json' \
    -d '{
      \"title\": \"测试工作区\",
      \"workspace_kind\": \"task\",
      \"template_id\": \"data-analysis\",
      \"runtime_binding\": {\"env_id\": \"workspace-default\", \"sandbox_mode\": \"local\"},
      \"initial_conversation_title\": \"开始分析\"
    }' | python3 -m json.tool
"
```

验证 Python 环境是否就绪：
```bash
# 替换 <workspace_id> 为上一步返回的 ID
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  curl -s 'http://127.0.0.1:13011/api/workspaces/<workspace_id>/runtime-environments' |
  python3 -c \"import json,sys; d=json.load(sys.stdin); e=d['envs'][0]; print('status:', e['status'], '| packages:', e['package_count'], '| error:', e.get('last_error'))\"
"
```

期望输出：`status: ready | packages: 157 | error: None`

## 端口说明

| 服务 | 端口 | 说明 |
|------|------|------|
| 后端 (Uvicorn) | 13011 | FastAPI 后端 |
| 前端 (Vite) | 13010 | 开发服务器 |
| 前端访问 | `http://<IP>:13010` | 如需从 WSL 访问前端 |

## 故障排查

| 症状 | 原因 | 解决 |
|------|------|------|
| `Electron failed to install correctly` | electron dist 未下载或损坏 | 删除 dist 目录后重新执行步骤 5 |
| `spawn ENOENT` 且 path 带 `\n` | path.txt 用 echo 写入 | 用 `printf` 重写 path.txt |
| `uv: No such file or directory` | uv 不在后端 PATH 中 | 安装 uv 到 `~/.local/bin/` |
| `config.json 不存在` | 未同步配置文件 | 执行步骤 7 |
| 后端启动慢或卡住 | venv 未创建 | 执行步骤 6 |
| 前端构建报 TypeScript 错误 | `tsc -b` 严格检查 | dev 模式下不影响启动，可忽略或修复 TS |
| 后端报 "LLM 动态配置为空" | `config.json` 未同步或 key 无效 | 见 [aiasys-llm-config](../aiasys-llm-config/SKILL.md) 排查 |
| API 返回 401 "Incorrect API key" | key 过期或被撤销 | 更新 `config.json` 中的 api_key 后重启后端 |

## 清理

停止 Mac 上的所有相关进程：

```bash
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  pkill -9 -f electron &&
  pkill -9 -f launch.cjs &&
  pkill -9 -f 'npm run dev' &&
  pkill -9 -f uvicorn
"
```

## 相关文件

| 文件 | 说明 |
|------|------|
| `apps/desktop/scripts/launch.cjs` | 桌面启动脚本，设置 `ELECTRON_OVERRIDE_DIST_PATH` 绕过 path.txt 换行符问题 |
| `apps/backend/app/services/runtime_environment.py` | UV 环境服务，已修复桌面模式下 PATH 截断问题 |
| `skills/_global/mac-desktop-deploy/SKILL.md` | 个人版（含具体 IP/密码等个人信息） |
| `aiasys-llm-config` | LLM 配置管理：key 位置、同步流程、故障排查 |

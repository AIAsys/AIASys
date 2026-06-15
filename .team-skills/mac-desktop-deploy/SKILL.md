---
name: mac-desktop-deploy
description: |
  AIASys Mac 桌面端部署与验证。通过 SSH 连接 Mac 设备，
  完成代码同步、依赖安装、Electron 二进制处理、后端 venv 搭建、
  前端构建、桌面应用启动，以及工作区创建验证。
  适用于需要远程编译和测试 Mac 桌面版的场景。
---

# Mac 桌面端部署

## 前提条件

- Mac 设备 IP 和 SSH 账号密码已知
- Mac 上有 Xcode Command Line Tools（`xcode-select -p` 验证）
- Mac 上有 nvm（Node 版本管理）
- 开发机上有 `sshpass` 和 `scp`（用于向 Mac 传输文件）

## 部署流程

### 1. SSH 连通性检查

```bash
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "echo connected && hostname"
```

如果提示 `sudo: a terminal is required`，后续安装 Python 时需要交互式 sudo。

### 2. 代码同步

用 git bundle 打包（排除 node_modules）：

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

```bash
# Python 3.12（如果 Mac 只有 3.9）
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  cd /tmp && curl -L -o python312.pkg 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-macos11.pkg' &&
  sudo installer -pkg python312.pkg -target /
"
# 验证
/usr/local/bin/python3.12 --version
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

Mac 上 npm 下载 Electron 经常失败，需要手动从镜像下载：

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

解压并修复 path.txt 换行符问题：

```bash
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  cd ~/projects/AIASys/apps/desktop &&
  mkdir -p node_modules/electron/dist &&
  unzip -q /tmp/electron.zip -d node_modules/electron/dist &&
  printf 'Electron.app/Contents/MacOS/Electron' > node_modules/electron/path.txt
"
```

> **注意**：`path.txt` 不能用 `echo` 写入（会带 `\n` 换行），必须用 `printf`。

### 6. 后端环境搭建

```bash
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  cd ~/projects/AIASys/apps/backend &&
  ~/.local/bin/uv --version &&
  ~/.local/bin/uv venv .venv --python 3.12 &&
  ~/.local/bin/uv pip install -r pyproject.toml --python .venv/bin/python3
"
```

如果 `~/.local/bin/uv` 不存在，从 vendored 路径复制：
```bash
# 先从开发机传输 vendored uv
scp apps/backend/vendor/uv/darwin-arm64/uv <用户>@<IP>:~/.local/bin/uv
```

### 7. 配置与目录准备

```bash
scp apps/backend/config.toml <用户>@<IP>:~/projects/AIASys/apps/backend/config.toml
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
      \"template_id\": \"data-analysis\",
      \"runtime_binding\": {\"env_id\": \"workspace-default\", \"sandbox_mode\": \"local\"}
    }' | python3 -m json.tool
"
```

验证 Python 环境：
```bash
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  curl -s http://127.0.0.1:13011/api/workspaces/<workspace_id>/runtime-environments |
  python3 -c \"import json,sys; d=json.load(sys.stdin); e=d['envs'][0]; print('status:', e['status'], 'packages:', e['package_count'])\"
"
```

## 故障排查

| 症状 | 原因 | 解决 |
|------|------|------|
| `Electron failed to install correctly` | electron dist 未下载 | 执行步骤 5 手动下载 |
| `spawn ENOENT` + path 带 `\n` | path.txt 用 echo 写入 | 用 `printf` 重写 path.txt |
| `uv: No such file or directory` | uv 不在后端 PATH 中 | 复制 vendored uv 到 `~/.local/bin/` |
| `config.toml 不存在` / `配置文件不存在` | 未同步配置文件 | 执行步骤 7 |
| 后端启动慢 / 卡住 | venv 未创建 | 执行步骤 6 |

## 清理

```bash
# 停止 Mac 上的所有相关进程
sshpass -p '<密码>' ssh -o StrictHostKeyChecking=no <用户>@<IP> "
  pkill -9 -f electron && pkill -9 -f launch.cjs && pkill -9 -f npm && pkill -9 -f uvicorn
"
```

## 参数速查

| 参数 | 默认值 | 说明 |
|------|--------|------|
| Mac SSH 用户 | `ml` | |
| Mac SSH 密码 | — | 不硬编码在 skill 中 |
| Mac IP | `172.16.105.139` | 按实际环境填写 |
| Python 版本 | 3.12 | 后端要求 >= 3.12 |
| Electron 版本 | 41.2.0 | 与 package.json 保持一致 |
| 后端端口 | 13011 | |
| 前端端口 | 13010 | |
| uv 镜像 | npmmirror | 国内加速 |

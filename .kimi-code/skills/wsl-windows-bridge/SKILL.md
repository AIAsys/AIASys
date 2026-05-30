---
name: wsl-windows-bridge
description: |
  WSL 与 Windows 双环境互相操作的桥接方法论。
  当 Agent 需要在 WSL 中操作 Windows 文件（或反之）、跨环境修改配置、同步文件、
  路径转换、命令行工具选择时触发。
  覆盖 WSL→Windows 路径映射（/mnt/c/ → C:\）、Windows→WSL 路径映射（\\wsl$\）、
  Shell 工具选择策略、常见跨环境错误与规避方法。
---

# WSL ↔ Windows 桥接操作 Skill

**定位**: Agent 在 WSL 和 Windows 双环境下互相操作时的正确方法论
**适用范围**: 所有涉及跨 WSL/Windows 边界的文件读写、命令执行、配置修改场景

---

## 核心原则

> **Agent 永远运行在 WSL 侧**。所有操作通过 WSL 的 Shell 工具发出，但可以通过路径映射访问 Windows 侧的文件。

```
Agent (WSL) ──Shell──> Linux 命令 ──/mnt/c/...──> Windows 文件
Agent (WSL) ──Shell──> Linux 命令 ──本地路径────> WSL 文件
```

**没有"从 Windows 侧操作"的路径**。Agent 无法直接执行 PowerShell 或 CMD 命令（除非通过 `cmd.exe /c` 或 `powershell.exe -Command` 在 WSL 中调用）。

---

## 路径映射速查表

| 场景 | WSL 路径 | Windows 路径 |
|------|----------|-------------|
| Windows 用户目录 | `/mnt/c/Users/ke/` | `C:\Users\ke\` |
| Windows 项目目录 | `/mnt/c/Users/ke/Documents/projects/...` | `C:\Users\ke\Documents\projects\...` |
| Windows kimi 配置 | `/mnt/c/Users/ke/.kimi/config.toml` | `C:\Users\ke\.kimi\config.toml` |
| WSL 用户目录 | `/home/ke/` | `\\wsl.localhost\Ubuntu\home\ke\` |
| WSL kimi 配置 | `/home/ke/.kimi/config.toml` | ❌ 无直接 Windows 路径（需通过 `\\wsl$`） |

### 路径转换工具

```bash
# WSL → Windows 路径
wslpath -w "/mnt/c/Users/ke/.kimi/config.toml"   # → C:\Users\ke\.kimi\config.toml

# Windows → WSL 路径
wslpath -u "C:\\Users\\ke\\.kimi\\config.toml"    # → /mnt/c/Users/ke/.kimi/config.toml
```

---

## 操作策略：读 vs 写

### 读取 Windows 文件（安全，随意）

直接用 `/mnt/c/...` 路径读取：

```bash
cat /mnt/c/Users/ke/.kimi/config.toml
# 或用 ReadFile 工具: /mnt/c/Users/ke/.kimi/config.toml
```

### 写入 Windows 文件（需谨慎）

同样可以直接写，但注意：

```bash
# ✅ 正确：WriteFile / StrReplaceFile 直接操作 /mnt/c/... 路径
# ✅ 正确：Shell 中用重定向
echo "content" > /mnt/c/Users/ke/some-file.txt
```

**重要**：`/mnt/c/` 下的文件写入是直接操作 Windows 文件系统，不需要额外权限。前提是文件/目录已存在且有写权限。

### 在 Windows 上执行命令

Agent 无法直接开 PowerShell，但可以通过 WSL 调用：

```bash
# ✅ 执行简单 Windows 命令
/mnt/c/Windows/System32/cmd.exe /c "dir C:\Users\ke"
/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -Command "Get-Process"

# ⚠️ 限制：无法执行需要 Windows GUI 或交互式输入的命令
# ⚠️ 限制：Windows 命令中的路径必须用 Windows 格式（C:\...），不能用 /mnt/c/...
```

---

## 常见错误与规避

### 错误 1：路径格式混淆

```
❌ 错误：在 WSL Shell 中使用 Windows 路径格式
   cat "C:\Users\ke\.kimi\config.toml"      # 找不到文件

❌ 错误：在 cmd.exe /c 中使用 WSL 路径
   cmd.exe /c "dir /mnt/c/Users/ke"          # Windows 不认 /mnt/c/

✅ 正确：WSL 命令用 /mnt/c/，Windows 命令用 C:\
```

### 错误 2：`find` 命令在 `/mnt/c/` 下极慢

```
❌ 错误：
   find /mnt/c/Users/ke -name "config.toml" -path "*kimi*" 2>/dev/null
   # 遍历整个 Windows 用户目录，可能超时

✅ 正确：限制搜索深度
   find /mnt/c/Users/ke -maxdepth 4 -name "config.toml" -path "*kimi*" 2>/dev/null
   # 或用 Glob 工具指定更精确的路径
```

### 错误 3：跨环境修改配置后忘记两边同步

```
❌ 错误：只改了 WSL 的 ~/.kimi/config.toml，Windows 端没改
❌ 错误：只改了 Windows 的 C:\Users\ke\.kimi\config.toml，WSL 端没改

✅ 正确：确认用户说的是"两边都改"，则两个文件都要更新
✅ 正确：操作前先确认当前会话运行在哪一侧，优先改当前侧，再同步对侧
```

### 错误 4：以为 Agent 可以直接运行 PowerShell

```
❌ 错误：
   Shell: "Get-ChildItem C:\Users\ke\.kimi\"     # bash 不认这个命令

✅ 正确：
   Shell: "powershell.exe -Command 'Get-ChildItem C:\Users\ke\.kimi\'"
   # 或直接用 WSL 方式读取
   Shell: "ls /mnt/c/Users/ke/.kimi/"
```

### 错误 5：写入不存在的 Windows 目录

```
❌ 错误：
   WriteFile: /mnt/c/Users/ke/new-dir/new-file.txt
   # 如果 new-dir 不存在会失败

✅ 正确：先确保目录存在
   mkdir -p /mnt/c/Users/ke/new-dir
   WriteFile: /mnt/c/Users/ke/new-dir/new-file.txt
```

---

## 跨环境配置同步策略

许多工具（kimi-cli、claude-code、codex）在 WSL 和 Windows 端各自维护独立的配置文件：

| 工具 | WSL 配置路径 | Windows 配置路径 |
|------|-------------|-----------------|
| Kimi CLI | `~/.kimi/config.toml` | `C:\Users\ke\.kimi\config.toml` |
| Claude Code | `~/.claude/settings.json` | `C:\Users\ke\.claude\settings.json` |
| Codex CLI | `~/.codex/config.toml` | `C:\Users\ke\.codex\config.toml` |

### 同步原则

1. **用户说"两边都改"** → 两个文件都要更新
2. **用户说"改配置"未指定** → 优先改 WSL 侧（Agent 运行环境），然后主动确认是否同步 Windows 侧
3. **用户说"Windows 那边"** → 只改 `/mnt/c/Users/ke/...` 路径
4. **用户说"WSL 这边"** → 只改 `~/.kimi/...` 或 `/home/ke/...`

### 典型工作流

```
用户: "帮我把 kimi 的 max_ralph_iterations 改成 -1，两边都要"

Agent 操作:
1. StrReplaceFile ~/.kimi/config.toml          # WSL 侧
2. StrReplaceFile /mnt/c/Users/ke/.kimi/config.toml  # Windows 侧
3. 提醒用户：新会话才生效
```

---

## 性能注意事项

| 操作 | 性能 | 建议 |
|------|------|------|
| 读取 `/mnt/c/` 下单个文件 | 快 | 直接用 |
| 写入 `/mnt/c/` 下单个文件 | 快 | 直接用 |
| `find` 遍历 `/mnt/c/` 深层目录 | 慢，可能超时 | 限制 `-maxdepth`，或用精确路径 |
| `grep` 搜索 `/mnt/c/` 下大范围 | 慢 | 缩小搜索范围 |
| 在 `/mnt/c/` 下编译/构建 | 极慢 | 不要这样做，把文件拷到 WSL 本地再操作 |

---

## 关联 Skill

- **ai-model-configs**：管理多平台 AI 工具配置，包含 WSL/Windows 双环境配置文件路径
- **plink-ssh**：Windows 侧远程操作 Linux 服务器
- **pkm-env-manager**：PKM 环境管理，涉及跨环境路径

---

## 交付检查

- [ ] 确认操作目标是 WSL 侧还是 Windows 侧（或两者）
- [ ] 路径格式与操作环境匹配（WSL→`/mnt/c/`，Windows→`C:\`）
- [ ] 跨环境搜索时限制深度和范围
- [ ] 两边配置同步时两个文件都已更新
- [ ] 提醒用户配置变更需要新会话才能生效（如适用）
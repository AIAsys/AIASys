---
name: aiasys-cross-platform
description: |
  AIASys 项目跨平台兼容性规范（团队版）。当涉及路径处理、文件 IO、进程管理、
  编码转换、Shell 命令执行、依赖选型时触发。覆盖三端（Windows、macOS、Linux）
  差异陷阱、常见错误模式、正确做法和项目内已有的跨平台基础设施。
  触发于：新增文件 IO 操作、使用 subprocess、引入新依赖、处理路径字符串、
  遇到平台相关 bug、或需要判断某个 API 是否跨平台安全时。
---

# AIASys 跨平台兼容性规范

## 定位

AIASys 三端支持（Windows、macOS、Linux），本 Skill 记录项目内已验证的跨平台陷阱和正确做法。

**核心原则**：优先用跨平台纯 Python/纯 JS 库，代码层消灭平台分支。平台差异推到构建/打包阶段，不推到运行时代码。

---

## 1. 依赖选型红线

### 已知陷阱清单

| 依赖 | 风险 | 替代方案 |
|------|------|----------|
| `fcntl` | Unix-only，Windows 直接 `ModuleNotFoundError` | `filelock`（最轻量）或 `portalocker` |
| `uvloop` | 不支持 Windows | 标准库 `asyncio`，Windows 上自动用默认事件循环 |
| `select.poll` | Unix-only，Windows 上没有 | `selectors.DefaultSelector()` 或 `asyncio` 高层 API |
| `os.fork` | Unix-only | `multiprocessing.Process` 或 `subprocess` |
| `aiohttp[speedups]` | `aiodns` → `pycares` 在 Windows 上编译痛苦 | `httpx`（纯 Python，无加速依赖也够） |
| `msvcrt` | Windows-only，反向的移植问题 | 用跨平台库替代，不要反向写兼容层 |
| `shlex.quote` | 在 Windows 上行为不对 | `subprocess.list2cmdline` 或手动双引号转义 |

### 引入新依赖前检查

1. 是否有纯 Python/纯 JS 替代？
2. 是否三端编译/运行无问题？
3. 带 C 扩展的库（`numpy`、`cryptography`、`psutil`）用 `uv` 的多平台锁定能力处理，不手写双依赖文件

---

## 2. 路径处理

### 正确做法

```python
# ✅ 使用 pathlib + as_system_path
from pathlib import Path
from app.utils.path_utils import as_system_path

file_path = Path(workspace_dir) / "subdir" / "file.txt"
with open(as_system_path(file_path), "r") as f:
    content = f.read()
```

### 错误做法

```python
# ❌ 硬编码路径分隔符
path = workspace_dir + "/" + subdir + "/" + filename

# ❌ 直接使用 Path 做文件 IO（Windows 长路径 > 240 字符会失败）
file_path.unlink()
shutil.rmtree(file_path)

# ✅ 正确：使用 as_system_path
Path(as_system_path(file_path)).unlink()
shutil.rmtree(as_system_path(file_path))
```

### 长路径处理

`app/utils/path_utils.py` 提供 `as_system_path()`，在 Windows 上对超过 240 字符的绝对路径自动添加 `\\?\` 前缀。

**所有涉及用户工作区路径的文件 IO 必须走 `as_system_path()`**：

- `open()`、`Path.read_text()`、`Path.write_text()`、`Path.mkdir()`、`Path.unlink()`
- `shutil.copy()`、`shutil.move()`、`shutil.rmtree()`、`shutil.copytree()`、`shutil.copy2()`
- `os.remove()`、`os.makedirs()`、`os.rename()`

---

## 3. 编码处理

### 正确做法

```python
# ✅ 使用 smart_decode（UTF-8 → UTF-16LE BOM → locale → GBK 降级链）
from app.core.encoding_utils import smart_decode

result = subprocess.run(cmd, capture_output=True)
output = smart_decode(result.stdout)
```

### 错误做法

```python
# ❌ 硬编码 UTF-8（Windows 上可能产生 GBK 解码错误）
output = result.stdout.decode("utf-8")

# ❌ 硬编码 GBK（Linux/macOS 上不是 GBK）
output = result.stdout.decode("gbk")
```

### 适用范围

**所有 subprocess 输出解码必须走 `smart_decode()`**。文件内容解码也建议使用 `smart_decode()`。

`smart_decode()` 降级链：UTF-8 → UTF-16LE BOM → locale encoding → GBK → `errors="replace"` 兜底。

---

## 4. 进程管理

### 进程终止

```python
# ✅ 跨平台判断
import os
import signal
import subprocess

if os.name == "nt":
    # Windows：无进程组语义，用 taskkill
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)])
else:
    # POSIX：用进程组终止
    os.killpg(os.getpgid(pid), signal.SIGTERM)
```

| 操作 | POSIX | Windows |
|------|-------|---------|
| 进程组终止 | `os.killpg(os.getpgid(pid), signal.SIGTERM)` | `taskkill /T /F /PID <pid>` |
| 创建进程组 | `os.setpgrp()` / `start_new_session=True` | 无原生支持，用 `taskkill /T` 杀树 |
| 子进程创建 | `os.fork()` | `subprocess.Popen` |

### 已实现的跨平台组件

- `PTYManager`：`apps/backend/app/services/terminal/pty_manager.py` — POSIX 用 openpty+fork，Windows 用 pywinpty
- `ShellExecutor`：`apps/backend/app/services/shell_executor.py` — 双路径 `_kill_posix_process_tree` / `_kill_windows_process_tree`
- ACP Client：cancel/close 用 taskkill（Windows）

---

## 5. Shell 命令执行

### 跨平台 Shell 引用

```python
# ✅ 在 runtime_execution.py 中的实现
def _shell_quote(arg: str) -> str:
    if os.name == "nt":
        return f"'{arg}'"          # Windows: PowerShell 单引号
    else:
        import shlex
        return shlex.quote(arg)    # POSIX: shlex.quote
```

### Shell 选择

| 平台 | 默认 Shell | 备选 |
|------|-----------|------|
| Windows | PowerShell | Git Bash、WSL、busybox |
| macOS | zsh | bash |
| Linux | bash | sh |

**Windows 上已禁用 `cmd.exe`**，即使显式指定 `interpreter=cmd`，ShellExecutor 也自动降级到 PowerShell。

---

## 6. 常见错误模式

### 模式 1：裸 `Path` 做文件 IO

```python
# ❌
file_path = Path(workspace) / "file.txt"
file_path.unlink()               # Windows 长路径可能失败
shutil.rmtree(file_path)         # 同上

# ✅
file_path = Path(workspace) / "file.txt"
Path(as_system_path(file_path)).unlink()
shutil.rmtree(as_system_path(file_path))
```

### 模式 2：硬编码 UTF-8 解码

```python
# ❌
text = stdout.decode("utf-8")

# ✅
from app.core.encoding_utils import smart_decode
text = smart_decode(stdout)
```

### 模式 3：`os.path.join` 混用分隔符

```python
# ❌
path = os.path.join("dir", "subdir", "file.txt")  # 返回字符串，不是 Path

# ✅
path = Path("dir") / "subdir" / "file.txt"
```

### 模式 4：`shlex.quote` 在 Windows 上

```python
# ❌ 在 Windows 路径上使用
import shlex
cmd = f"cd {shlex.quote(windows_path)} && ..."  # Windows 行为不对

# ✅ 仅用于 POSIX/WSL/Docker 路径
# Windows 路径用双引号或 subprocess.list2cmdline
```

### 模式 5：`os.name` 分支漏了 macOS

```python
# ❌
if os.name == "nt":
    ...
else:
    ...  # 假设是 Linux，但 macOS 也走这里

# ✅ 用 sys.platform 或显式处理三端
import sys
if sys.platform == "win32":
    ...
elif sys.platform == "darwin":
    ...
else:
    ...
```

---

## 7. 项目内已接入 `as_system_path` 的模块

以下模块已正确接入，新增类似操作时参考：

- `file_history.py` — 文件版本管理全部 IO
- `memory/store.py`、`memory/resolver.py` — Memory 子系统
- `diff_service.py` — 差异对比
- `file_tools.py`、`file_tools_read.py`、`file_tools_write.py` — Agent 文件工具
- `workspaces_resources_files.py` — 工作区文件 API
- `sqlite_vec.py` — 数据库连接
- `session_execution_journal.py` — 执行日志
- `subagent_storage.py` — 子 Agent 存储
- `files_core.py` — 文件核心端点
- `sessions_branches.py` — 会话分支

---

## 8. 快速检查清单

新增或修改文件 IO 代码时，确认：

- [ ] 所有 `Path` 文件 IO 操作（`mkdir`、`unlink`、`write_text`、`read_text`）走 `as_system_path()`
- [ ] 所有 `shutil` 操作（`copy`、`move`、`rmtree`、`copytree`、`copy2`）走 `as_system_path()`
- [ ] 所有 `subprocess` 输出解码走 `smart_decode()`
- [ ] 文件内容解码用 `smart_decode()` 而非硬编码 `decode("utf-8")`
- [ ] 路径拼接使用 `pathlib.Path`，而非字符串拼接
- [ ] 无 `os.fork()` 裸调用（跨平台用 `subprocess`）
- [ ] 无 `shlex.quote` 用于 Windows 路径
- [ ] 新依赖已在三端检查过可用性
- [ ] 无 `os.name == "nt"` 分支覆盖不全（需同时考虑 macOS）

---

## 9. 相关文件

| 文件 | 说明 |
|------|------|
| `app/utils/path_utils.py` | `as_system_path()` 实现 |
| `app/core/encoding_utils.py` | `smart_decode()` 实现 |
| `app/services/terminal/pty_manager.py` | 跨平台 PTY 管理 |
| `app/services/shell_executor.py` | 跨平台 Shell 执行 |
| `AGENTS.md` | 跨平台依赖选择、桌面打包约束 |
| `design-draft/design/design-thinking/windows-cross-platform-shell-strategy.md` | Windows Shell 策略设计 |

---

*跨平台兼容性是 AIASys 三端支持的基础，代码层消灭平台分支，差异推到构建/打包阶段。*
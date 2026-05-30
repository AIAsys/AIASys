---
name: vendor-sync
description: Manage external vendor dependencies (kimi-cli and kimi-agent-sdk) synchronization. Use when checking versions, updating vendor libraries, or syncing upstream changes. This skill covers version checking, upstream syncing, and proper commit procedures for vendor updates.
---

# Vendor 依赖库同步

管理 AIASys 项目的外部依赖库（kimi-cli 和 kimi-agent-sdk）的版本检查和同步更新。

---

## 管理的依赖库

| 库名 | 本地路径 | 上游仓库 | 当前版本 |
|------|----------|----------|----------|
| kimi-cli | `apps/backend/vendor/kimi-cli` | https://github.com/MoonshotAI/kimi-cli | 1.30.0 |
| kimi-agent-sdk | `apps/backend/vendor/kimi-agent-sdk` | https://github.com/MoonshotAI/kimi-agent-sdk | 0.0.5 |

---

## 核心原则

1. **独立检查**：分别检查每个依赖库的上游更新
2. **完整同步**：确保从上游获取完整的最新代码
3. **版本验证**：同步后验证版本号是否正确
4. **及时提交**：vendor 更新应当单独提交，保持历史清晰

---

## 同步流程

### 1. 检查 kimi-cli 更新

```bash
cd apps/backend/vendor/kimi-cli

# 查看当前版本
git log --oneline -3

# 获取上游最新信息
git fetch upstream

# 查看待更新内容
git log --oneline HEAD..upstream/main

# 合并更新
git merge upstream/main --no-edit
```

### 2. 检查 kimi-agent-sdk 更新

```bash
# 克隆上游最新代码到临时目录
cd /tmp
rm -rf kimi-agent-sdk-check
git clone https://github.com/MoonshotAI/kimi-agent-sdk.git kimi-agent-sdk-check

# 查看最新提交时间
cd kimi-agent-sdk-check
git log -1 --format="%ci %s"

# 查看最新版本
cat python/pyproject.toml | grep "^version"

# 对比本地版本
cat /home/ke/projects/AIASys/apps/backend/vendor/kimi-agent-sdk/pyproject.toml | grep "^version"
```

### 3. 同步 kimi-agent-sdk

```bash
# 备份当前目录（可选）
cd /home/ke/projects/AIASys/apps/backend/vendor/kimi-agent-sdk

# 清空当前内容
rm -rf *

# 复制最新代码（从临时目录）
cp -r /tmp/kimi-agent-sdk-check/python/* .

# 验证版本
cat pyproject.toml | grep "^version"

# 清理临时目录
rm -rf /tmp/kimi-agent-sdk-check
```

---

## 版本检查清单

### kimi-cli 版本检查

- [ ] 进入 `apps/backend/vendor/kimi-cli` 目录
- [ ] 确认有 upstream remote 指向 `https://github.com/MoonshotAI/kimi-cli.git`
- [ ] 执行 `git fetch upstream` 获取最新信息
- [ ] 执行 `git log HEAD..upstream/main` 查看待更新提交
- [ ] 确认是否需要更新

### kimi-agent-sdk 版本检查

- [ ] 查看本地版本：`cat pyproject.toml | grep version`
- [ ] 克隆上游仓库到临时目录
- [ ] 查看上游最新提交时间：`git log -1 --format="%ci"`
- [ ] 查看上游版本：`cat python/pyproject.toml | grep version`
- [ ] 对比版本差异

---

## 提交规范

Vendor 更新应使用单独的提交，提交信息格式：

```
chore(vendor): 同步 <库名> 到 <版本>

- 从上游 <仓库地址> 同步最新代码
- 更新版本: <旧版本> -> <新版本>
- 主要变更:
  - <变更1>
  - <变更2>
```

**示例：**

```bash
git add apps/backend/vendor/kimi-cli
git commit -m "chore(vendor): 同步 kimi-cli 到 1.30.0

- 从上游 MoonshotAI/kimi-cli 同步最新代码
- 更新版本: 1.28.0 -> 1.30.0
- 主要变更:
  - feat: 添加 SetTodoList 状态持久化
  - feat: ReadFile 工具支持 totalLines 和 tail 模式
  - fix: 修复 Rich markdown 样式泄漏问题"
```

---

## 快速命令参考

### 一键检查所有依赖

```bash
echo "=== kimi-cli ==="
cd apps/backend/vendor/kimi-cli && git fetch upstream 2>/dev/null && git log --oneline HEAD..upstream/main | head -5

echo "=== kimi-agent-sdk ==="
cd /tmp && rm -rf sdk-check && git clone --depth 1 https://github.com/MoonshotAI/kimi-agent-sdk.git sdk-check 2>/dev/null && cat sdk-check/python/pyproject.toml | grep version && rm -rf sdk-check
```

### 查看最新提交时间

```bash
# kimi-cli
cd apps/backend/vendor/kimi-cli && git log -1 --format="%ci" upstream/main

# kimi-agent-sdk
cd /tmp && git clone --depth 1 https://github.com/MoonshotAI/kimi-agent-sdk.git sdk-time 2>/dev/null && cd sdk-time && git log -1 --format="%ci" && cd .. && rm -rf sdk-time
```

---

## 注意事项

1. **kimi-cli 是独立 git 仓库**：可以直接使用 git merge 同步
2. **kimi-agent-sdk 是子目录拷贝**：需要从上游 python/ 目录复制内容
3. **版本号位置**：
   - kimi-cli: `pyproject.toml` 中的 `version`
   - kimi-agent-sdk: `pyproject.toml` 中的 `version`
4. **提交前检查**：确保没有误修改其他文件

---

*保持 vendor 依赖最新，确保项目功能完整。*

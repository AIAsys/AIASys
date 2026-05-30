---
name: gh-skill-manager
description: 管理 AIASys 外部 skill 的安装、更新和移除。当用户要求安装、更新、搜索或删除 skill 时，统一使用 gh skill 命令，只操作 .agents/skills/ 目录，不产生 .claude/.kimi/.codex 等额外目录。
---

# gh-skill-manager

AIASys 的外部 skill 统一通过 `gh skill` 管理，禁止直接使用 `npx skills`。

## 为什么不用 npx skills

- `npx skills` 有交互式提示，Agent 在终端里无法自动完成选择
- `npx skills` 默认会给多个 agent 目录（.claude/.kimi/.codex）都复制一份，产生大量不需要的隐藏目录
- `gh skill` 支持完全非交互式安装，有版本 pinning 和 source tracking

## 前提条件

- gh CLI >= v2.90.0（已安装在 /home/ke/.local/bin/gh）
- 已登录 GitHub（`gh auth status` 正常）
- 当前 gh 版本：2.92.0

## 安装路径约定

所有外部 skill 只安装到项目级目录：

```
.agents/skills/<skill-name>/
```

禁止安装到：
- `~/.claude/skills/`
- `~/.kimi/skills/`
- `~/.codex/skills/`
- `~/.agents/skills/`

## 命令规范

### 搜索 skill

```bash
gh skill search <关键词> --limit 10
```

### 预览 skill 内容（安装前必做）

```bash
gh skill preview <owner>/<repo> <skill-name>
```

### 安装 skill

```bash
gh skill install <owner>/<repo> <skill-name> \
  --dir .agents/skills \
  --force
```

注意：`--dir` 指向父目录 `.agents/skills`，gh skill 会自动在下面创建 `<skill-name>/` 子目录。

### 安装指定版本

```bash
gh skill install <owner>/<repo> <skill-name>@<tag> \
  --dir .agents/skills \
  --force \
  --pin
```

### 更新单个 skill

```bash
gh skill update <skill-name>
```

### 更新所有 skill

```bash
gh skill update --all
```

### 移除 skill

直接删除目录：

```bash
rm -rf .agents/skills/<skill-name>
```

## 安全规则

1. 安装前必须用 `gh skill preview` 检查内容
2. 不安装来源不明的 skill（优先用官方仓库：vercel-labs、anthropics、microsoft 等）
3. 私有仓库 skill 需要确认用户有访问权限
4. skill 中的 `scripts/` 目录需要额外审查，确认没有恶意命令

## 版本管理

- 生产环境推荐用 `--pin` 锁定版本
- 更新前用 `gh skill update --dry-run` 预览变更
- 不要把 `.agents/skills/` 下的外部 skill 提交到 git（已在 .gitignore 中）

## 与 AIASys 自有 skill 的区分

- 外部 skill（通过 gh skill 安装）：来源是 GitHub 仓库，有 source tracking 元数据
- 自有 skill（AIASys 团队编写）：来源是 pkm-hub，同步到 `.agents/skills/`，没有 github-repo 元数据
- 两者共存于 `.agents/skills/`，由各自的更新渠道管理

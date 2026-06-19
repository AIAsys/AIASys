# AIASys 维护者发布流程

本文档面向项目维护者，规定如何从 `dev` 分支稳定地发布一个新版本。

## 版本号规则

- 采用语义化版本（SemVer）：`MAJOR.MINOR.PATCH`
- 当前阶段以 beta 预发布为主：`X.Y.Z-beta.N`（如 `0.4.17-beta.1`）
- 三端版本号必须保持一致：
  - `apps/web/package.json`
  - `apps/desktop/package.json`
  - `apps/backend/pyproject.toml`

## 发布前准备

1. 确认 `dev` 分支已合并所有待发布功能/修复
2. 确认 `dev` 分支 CI 通过
3. 确认 `docs/changelog/vX.Y.Z_YYYY-MM-DD.md` 已按规范编写

## 发布步骤

### 方式一：使用发布脚本（推荐）

```bash
git checkout main
git pull upstream main

# 演练模式，不实际提交
./scripts/dev/release.sh --dry-run X.Y.Z-beta.N

# 正式发布
./scripts/dev/release.sh X.Y.Z-beta.N
```

脚本会自动完成：
- 检查当前分支为 `main`
- 检查工作区干净
- 检查本地 `main` 与 `upstream/main` 一致
- 检查 changelog 文件存在
- 同步三端版本号
- 提交版本号变更
- 打 tag `vX.Y.Z-beta.N`
- 推送 `main` 分支

最后一步需要手动执行：

```bash
git push upstream vX.Y.Z-beta.N
```

### 方式二：手动发布

1. 创建 release PR：`dev` → `main`
2. 通过 CI 和 review 后合并
3. 本地切到 `main` 并拉取最新代码
4. 同步三端版本号
5. 提交版本号变更：`chore(release): bump version to X.Y.Z-beta.N`
6. 打 tag：`git tag vX.Y.Z-beta.N`
7. 推送：`git push upstream main && git push upstream vX.Y.Z-beta.N`

## 发布后验证

1. 等待 `.github/workflows/ci-desktop.yml` 完成
2. 检查 release 产物：
  ```bash
  gh release view vX.Y.Z-beta.N --json assets
  ```
3. 确认产物包含：
  - `AIASys_Desktop-X.Y.Z-beta.N.AppImage`
  - `AIASys_Desktop-X.Y.Z-beta.N-arm64.dmg`
  - `AIASys_Desktop-X.Y.Z-beta.N-arm64-mac.zip`
  - `AIASys_Desktop.Setup.X.Y.Z-beta.N.exe`

## 发布纪律

- 禁止直接 push 到 `main` 或 `dev`
- 管理员自己的改动也必须通过 PR
- 每个 release 必须有对应的 changelog
- 三端版本号必须一致
- 发布前 CI 必须通过

## 回滚

如果发布后发现严重问题：

1. 在 GitHub 上删除错误的 release 和 tag
2. 修复问题并通过 PR 合并到 `dev`，再合并到 `main`
3. 使用新的版本号重新发布（不要复用已删除的 tag）

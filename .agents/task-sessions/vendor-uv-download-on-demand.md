# vendor/uv 二进制改按需下载，不内置仓库

> 创建：2026-06-12 · 状态：待执行

## 背景

`vendor/uv/` 目录当前包含两个平台的 uv 二进制文件（darwin-arm64 47MB、linux-x64 56MB），合计约 103MB。GitHub 已发出大文件警告（linux-x64 超过 50MB 推荐上限）。这些二进制文件在代码中零引用——没有任何后端代码消费 `vendor/uv/` 路径。

uv 二进制的作用域是桌面打包（`prepare-runtime.cjs` 将整个 `vendor/` 目录复制到 staging，供 packaged app 离线创建 Python 环境）。开发和在线场景已有 `install_uv()`、`/api/system/uv/install`、`deploy_init.sh` 等下载链路覆盖。

## 目标

从仓库中移除 uv 二进制文件，改为打包时按当前平台按需下载。保留 `vendor/uv/` 目录结构和 README，二进制通过脚本获取。

## 影响范围

### 1. 从仓库删除二进制文件

```
apps/backend/vendor/uv/darwin-arm64/uv    — 删除
apps/backend/vendor/uv/linux-x64/uv       — 删除
```

保留 `apps/backend/vendor/uv/README.md`，内容改为说明下载方式。

### 2. 新增下载脚本

位置：`apps/desktop/scripts/download-uv-binary.cjs`

功能：
- 检测当前平台（darwin-arm64 / darwin-x64 / linux-arm64 / linux-x64 / windows-x64）
- 从 GitHub releases 下载对应平台的 uv 二进制
- 放到 `apps/backend/vendor/uv/$platform/uv`（或 Windows 下 `uv.exe`）
- 幂等：已存在且校验通过则跳过
- 错误处理：下载失败时给出明确提示，不静默

脚本需能独立运行（`node scripts/download-uv-binary.cjs`），也需能被 `prepare-runtime.cjs` 调用。

### 3. 集成到打包流程

修改 `prepare-runtime.cjs`：

- 在复制 `vendor/` 目录到 staging 之前，先调用下载脚本确保当前平台的 uv 二进制存在
- 建议在 `prepareBackendRuntime()` 开头或 `main()` 中 `cleanPycache` 之后加入下载步骤

### 4. （可选）后续消费者接入

下载脚本 + prepare-runtime 确保 uv 二进制进入打包产物后，后续需要在 `runtime_environment.py` 的 `_run_uv()` 或相关路径中，让 packaged 模式优先使用 `vendor/uv/$platform/uv` 而非依赖系统 PATH 中的 uv。这一步可独立于本次任务执行。

## 验证步骤

1. 删除二进制后：`git status` 确认 `vendor/uv/darwin-arm64/uv` 和 `vendor/uv/linux-x64/uv` 已从跟踪中移除
2. `node apps/desktop/scripts/download-uv-binary.cjs` — 在当前平台成功下载 uv 二进制
3. 再次运行下载脚本 — 输出"已存在，跳过"
4. `apps/backend/vendor/uv/当前平台/uv --version` — 输出版本号
5. 运行打包流程 — `prepare-runtime.cjs` 正常完成，staging 目录下 `vendor/uv/` 包含当前平台二进制
6. `grep -r "vendor/uv" apps/backend/app/` — 零结果（消费者尚未接入时）

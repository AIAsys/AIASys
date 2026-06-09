# scripts/

项目级工具脚本目录，按用途分为三个子目录。

## 子目录

| 目录 | 用途 |
|------|------|
| `dev/` | 开发环境脚本，含 `dev.sh` 统一入口、生命周期测试、Git hooks 安装等 |
| `design/` | 设计基线校验与 CSS 导出 |
| `security/` | 安全扫描脚本 |

## 常用入口

```bash
./dev.sh              # 启动前后端开发服务
./dev.sh design-lint  # 视觉设计基线校验
./dev.sh status       # 查看服务状态
```

## 脚本清单

### 根目录

| 脚本 | 说明 |
|------|------|
| `batch_agent_tests.py` | 批量执行 Agent 能力测试用例 |
| `run_agent_test.py` | 单条 Agent 能力测试辅助脚本 |
| `rerun_failed_tests.py` | 重测未通过的用例 |
| `rerun_nb_tests.py` | 重测 Notebook 域用例 |
| `update_test_records.py` | 批量更新测试用例文件的测试记录 |
| `update_test_records_rerun.py` | 追加第二轮重测结果到测试记录 |

### dev/

| 脚本 | 说明 |
|------|------|
| `cli.sh` | `dev.sh` 本体，前后端开发服务统一入口 |
| `setup-hooks.sh` | 安装仓库内置 Git hooks |
| `run_lefthook.sh` | 跨平台解析并调用 lefthook |
| `run_lifecycle_playwright.sh` | 启动开发栈并运行 Playwright 生命周期测试 |
| `lefthook/common.sh` | lefthook 公共函数库 |
| `lefthook/pre-commit.sh` | pre-commit hook 实现 |

### design/

| 脚本 | 说明 |
|------|------|
| `validate-design-md.sh` | 校验根目录 `DESIGN.md` |
| `export-tailwind4-css.mjs` | 从 `DESIGN.md` 生成 Tailwind 4 CSS 变量草案 |
| `export-runtime-theme-candidate.mjs` | 生成当前运行时变量候选主题和映射说明 |

### security/

| 脚本 | 说明 |
|------|------|
| `scan-secrets.sh` | 扫描 git 历史中的潜在敏感信息泄露 |
| `scan-secrets-ci.sh` | CI 环境轻量扫描：只检查本次变更 |
| `pre-commit-scan.sh` | pre-commit hook：扫描暂存区中的潜在敏感信息 |

## 临时脚本归档

已完成的临时任务脚本统一归档到 `design-draft/archive/scripts/`，不在本目录保留：

- `design-draft/archive/scripts/ux-audit-20250608/` — 2025-06-08 UX 审计相关脚本
- `design-draft/archive/scripts/demo-record-20250607/` — 2025-06-07 Demo 视频录制脚本

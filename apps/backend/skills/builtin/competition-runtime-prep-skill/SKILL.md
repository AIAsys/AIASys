+++
name = "竞赛运行环境准备"
description = "为竞赛项目准备可绑定的 Python/UV 运行环境：选择或创建环境、安装依赖、锁定版本、验证导入、检查 GPU 和执行小样本 runner smoke。\n适用于实验 AutoTask 因缺少 XGBoost、Optuna、Torch、CUDA/GPU 条件或大依赖安装阻塞而需要先把环境准备到可用状态的场景。"
+++


# 竞赛运行环境准备 Skill

这个 skill 只负责把竞赛运行环境准备到可交给实验任务使用。它不负责正式跑分，不写 keep/discard 实验结论，也不替代 `competition-research-skill` 的实验循环。

## 何时使用

使用本 skill：

- 项目需要安装或升级 `xgboost`、`catboost`、`torch`、CUDA 相关包等大依赖。
- AutoTask 在实验轮中发现依赖缺失、UV 同步卡住、GPU 不可用或 Python 版本不合适。
- 用户希望为不同实验路线准备多个环境，例如 `xgb-optuna`、`torch-small`、`workspace-default`。
- 需要确认某个环境能导入关键包，并能通过 runner 小样本 smoke。

不要使用本 skill：

- 只是要在已验证环境里继续跑一条实验线。用 `competition-research-skill`。
- 需要多会话、多环境并行探索编排。用 `competition-parallel-research-skill`。
- 用户只是在问竞赛项目当前分数或实验历史。先读项目 `AGENTS.md` 和 `experiments/index.json`。

## 输入

先读取：

- `experiments/index.json`
- 项目 `AGENTS.md`
- 当前工作区运行环境登记，例如 `.env/environments.json`
- `.env/pyproject.toml`、`.env/uv.lock`
- runner 配置和 `run_baseline.sh` 或等价入口
- `outputs/observations/` 中最近的环境阻塞记录

如果用户指定目标方法，继续读取相关论文或方法说明，但只提取环境需求，不设计正式实验。

## 工作流

1. 确认目标实验路线和环境需求。
2. 列出当前可用环境和绑定状态。
3. 判断复用现有环境还是创建新环境。
4. 估算依赖风险：包体积、GPU/CUDA、Python 版本、安装时间、三端路径差异。
5. 对大依赖先给出安装计划，再执行受控安装。
6. 安装后运行导入 smoke。
7. 如果需要 GPU，运行最小 GPU smoke，不启动长训练。
8. 如果项目有 runner，运行最小 runner preflight 或 dry-run；没有 dry-run 时只检查入口和必要文件。
9. 写环境报告。
10. 把可用 `env_id` 和验证结果交给 `competition-research-skill` 或 `competition-parallel-research-skill`。

## 输出

环境报告写入：

```text
outputs/runtime-prep/<env_id>-<date>.md
```

最低内容：

```markdown
# Runtime Prep: <env_id>

- env_id:
- material_path:
- python:
- package changes:
- import smoke:
- GPU smoke:
- runner smoke:
- usable_for:
- known limits:
- next handoff:
```

同时把简短结论写入：

```text
outputs/observations/<date>-auto-research.md
```

## 规则

- 不修改 AIASys 后端自身 `.venv`。
- 不把环境安装事件写成正式实验 keep/discard。
- 大依赖安装前先确认目标环境，不在未绑定或不明确的解释器里安装。
- 安装失败时记录命令、耗时、错误尾部和恢复建议。
- GPU smoke 只做最小验证，不启动正式训练。
- 如果一个环境被多个工作区或会话复用，安装前必须提示影响范围。
- 完成后必须给出下一步可用的 `env_id` 或明确说明没有可用环境。

## 与其他 Skill 的关系

```text
competition-runtime-prep-skill
  -> 准备 env_id 和环境报告
  -> competition-research-skill 使用该环境做串行实验
  -> competition-parallel-research-skill 为多个 lane 分配该环境
```

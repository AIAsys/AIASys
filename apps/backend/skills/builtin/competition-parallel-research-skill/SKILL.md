+++
name = "竞赛并行研究编排"
description = "为竞赛项目编排多会话、多环境、多 AutoTask lane 的并行探索：拆分方向、分配 env_id、控制并发、避免输出冲突，并汇总各 lane 结果。\n适用于用户明确希望同时探索 LightGBM、XGBoost、Transformer 等多条路线，且每条路线可能绑定不同运行环境的场景。"
+++


# 竞赛并行研究编排 Skill

这个 skill 负责并行探索的编排，不负责亲自实现每条 baseline 的细节，也不负责安装大依赖。单条 lane 的实验执行交给 `competition-research-skill`，环境准备交给 `competition-runtime-prep-skill`。

## 何时使用

使用本 skill：

- 用户明确要求多条路线并行探索。
- 同一竞赛需要多个 `env_id` 同时服务不同会话。
- 需要把多个 AutoTask lane 的结果汇总成主线建议。
- 需要控制 GPU、CPU、runner 锁和 `experiments/index.json` 写回顺序。

不要使用本 skill：

- 只需要继续一条实验线。用 `competition-research-skill`。
- 只是缺依赖或 GPU 不可用。用 `competition-runtime-prep-skill`。
- 当前项目还没有 v0 baseline、runner 或真实数据。先回到 `competition-research-skill` 的 bootstrap 流程。

## 输入

先读取：

- `experiments/index.json`
- 项目 `AGENTS.md`
- `research_views/current.html`
- `outputs/observations/`
- 当前工作区运行环境登记
- 可用 AutoTask 列表
- 用户给定的并发预算、GPU 预算和最大 lane 数

## Lane 计划

每条 lane 必须有：

| 字段 | 说明 |
|------|------|
| `lane_id` | 稳定 ID，例如 `lgb-main`、`xgb-optuna`、`torch-small` |
| `goal` | 本 lane 要验证的方向 |
| `env_id` | 绑定的运行环境 |
| `base_version` | 派生来源 |
| `candidate_version` | 唯一候选版本名 |
| `session_id` | 执行会话 |
| `auto_task_id` | 如由 AutoTask 推进则记录 |
| `max_rounds` | 最大轮数 |
| `resource_limit` | CPU/GPU/时间限制 |
| `write_policy` | 写回策略 |

## 并行规则

- 并行探索不默认开启，必须有用户明确授权。
- 每条 lane 必须绑定明确 `env_id`。
- 每条 lane 必须有唯一版本名或版本名前缀。
- runner 输出目录、日志路径、提交目录不能重叠。
- GPU lane 默认最大并发 1，除非用户明确提高限制。
- 多个 lane 可以并行跑 runner，但写 `experiments/index.json` 的动作必须串行化。
- lane 失败时只标记该 lane，不影响其他 lane；汇总阶段统一判断是否进入主线。
- 不在并行编排阶段安装大依赖。环境未就绪时，先转交 `competition-runtime-prep-skill`。

## 输出

并行计划写入：

```text
outputs/parallel_research/<date>-plan.md
```

lane 状态写入：

```text
outputs/parallel_research/<date>-lanes.json
```

汇总写入：

```text
outputs/parallel_research/<date>-summary.md
```

汇总内容至少包含：

- 每条 lane 的目标、env_id、版本、状态。
- 每条 lane 的最终分数或失败原因。
- 是否建议把某条 lane 合入主线。
- 是否需要更新 `priority_queue`、`anti_patterns`、`research_views/current.html` 或 Canvas。

## 与其他 Skill 的关系

```text
competition-runtime-prep-skill
  -> 准备多个可用 env_id

competition-parallel-research-skill
  -> 规划 lane
  -> 控制并发和写回
  -> 汇总结果

competition-research-skill
  -> 在每条 lane 内执行单会话串行实验
```

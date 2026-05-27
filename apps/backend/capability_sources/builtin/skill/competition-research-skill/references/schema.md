# 数据结构

竞赛项目的核心状态写在 `experiments/index.json` 和 `references/index.json`。文本总结可以重生成，结构化索引必须保持准确。

## experiments/index.json

```json
{
  "competition": "<name>",
  "metric": "<metric>",
  "direction": "minimize|maximize",
  "best_score": null,
  "best_version": null,
  "trusted_best_score": null,
  "trusted_best_version": null,
  "highest_observed_score": null,
  "highest_observed_version": null,
  "current_phase": "literature|feature|model|ensemble",
  "last_updated": "<iso8601>",
  "knowledge_graph_id": "<kg-id>",
  "knowledge_graph_db_path": "/global/resources/graphs/<kg-id>.db",
  "knowledge_graph_file": "<slug>.graph.db",
  "research_dashboard_path": "research_views/current.html",
  "paper_registry_path": "references/index.json",
  "auto_task_status": "paused|active|completed|blocked",
  "runner_status": "idle|running|blocked",
  "latest_version": null,
  "next_candidate_version": null,
  "runner": {
    "type": "builtin_experiment|workspace_shell|platform_notebook|api_interaction|simulation",
    "command": "python3 scripts/experiment.py --mode run --experiments experiments/index.json --workspace . --version {version}",
    "default_version": null,
    "output_path": "outputs/{version}/output.csv",
    "log_path": "outputs/logs/{version}.log",
    "score_source": "stdout|metrics_file|manual",
    "record_policy": "experiment_record",
    "expected_runtime_minutes": null,
    "long_running": false,
    "background_required": false
  },
  "runtime_contract": {
    "mode": "stable_bound_environment",
    "env_id": null,
    "preflight_imports": [],
    "large_dependency_policy": "pause_and_request_runtime_prep",
    "observation_path": "outputs/observations/<date>-auto-research.md"
  },
  "auto_task_ids": [],
  "experiments": [],
  "anti_patterns": [],
  "priority_queue": []
}
```

知识图谱字段按优先级读取：

1. `knowledge_graph_db_path`：AIASys 资源路径，优先使用 `/global/resources/graphs/<kg-id>.db`。
2. `knowledge_graph_id`：AIASys 全局图谱 ID，用于 `ListKnowledgeGraphs`、`SearchKnowledgeGraphEntities`、`QueryEntityRelations`。
3. `knowledge_graph_file`：旧本地 `.graph.db` 字段，只保留给历史脚本和旧材料，不作为新项目首选。

## research_dashboard_path

`research_dashboard_path` 默认 `research_views/current.html`。它是自动研究状态看板，用来快速读取 AutoTask、runner、可信最优、最新实验、下一候选、风险和证据入口。每轮 record 后或 AutoTask/runner 状态变化后刷新。

新项目初始化时必须写 `knowledge_graph_id` 和 `knowledge_graph_db_path`。整理旧项目时，如果已有旧 `.graph.db`，先迁移或重建到全局图谱目录，再保留旧字段作历史说明。

## runner

`runner` 描述当前项目的执行适配层。自动研究统一维护 `plan -> run -> evaluate -> record -> update_kg -> update_dashboard` 生命周期，但 `run` 入口按项目配置执行。

字段说明：

| 字段 | 说明 |
|------|------|
| `type` | 执行类型。常用值包括 `builtin_experiment`、`workspace_shell`、`platform_notebook`、`api_interaction`、`simulation` |
| `command` | 可模板化命令，允许使用 `{version}`、`{from_version}`、`{workspace}` 等占位符 |
| `default_version` | 默认运行版本。为空时由当前 best 或本轮计划决定 |
| `output_path` | 主要产物路径模板 |
| `log_path` | 运行日志路径模板 |
| `score_source` | 分数来源，常见值为 `stdout`、`metrics_file`、`manual` |
| `record_policy` | 记录策略。默认 `experiment_record`，表示用 `experiment.py --mode record` 写回 |
| `expected_runtime_minutes` | 单轮预计耗时。未知时先用一次最小 smoke 校准，不要盲目开长任务 |
| `long_running` | 是否可能超过普通 Shell 超时 |
| `background_required` | 是否必须走后台任务或平台长任务监控 |
| `progress_log_required` | 是否要求 runner 输出阶段进度。长耗时训练默认应为 true |
| `monitor_poll_seconds` | AutoTask 轮询 Monitor 的建议间隔，默认 30 到 60 秒 |

runner 只定义怎么执行和在哪里找证据。`best_score`、`best_version`、`anti_patterns` 和 `priority_queue` 仍以 `experiments/index.json` 的记录结果为准。

长 runner 的完成判断按证据链处理：Monitor 有退出码、日志有阶段进度和结束行、`output_path` 存在、指标文件或 stdout 能解析出最终分数，至少要满足项目定义的最低要求。Shell 超时不等于实验失败；如果输出已经完整生成，应按结果记录，并把超时现象写入 `outputs/observations/<date>-auto-research.md`。

进度日志是 runner 契约的一部分。长耗时 baseline 至少输出数据加载、特征构建、模型训练开始、候选评分完成、产物写入和最终指标。Python 代码使用 `print(..., flush=True)` 或 `python -u`，避免 Monitor 和日志文件长时间没有新增内容。

## runtime_contract

`runtime_contract` 描述单分支实验 AutoTask 对运行环境的预期。它不是环境安装清单，也不是替代 AIASys 运行环境登记的事实源。

字段说明：

| 字段 | 说明 |
|------|------|
| `mode` | 默认 `stable_bound_environment`，表示实验轮只使用已准备或已绑定环境 |
| `env_id` | 当前建议绑定的环境 ID。为空时读取工作区当前 active runtime 或项目 `.env` |
| `preflight_imports` | 启动 runner 前必须轻量导入验证的包，如 `lightgbm`、`pandas`、`numpy` |
| `large_dependency_policy` | 默认 `pause_and_request_runtime_prep`，缺大依赖时暂停并转交环境准备 |
| `observation_path` | 环境阻塞和 runner 异常观察的默认写入位置 |

`competition-research-skill` 只能按这个契约做轻量 preflight。`torch`、`xgboost`、`catboost`、CUDA 相关包和大 wheel 的安装、GPU smoke、锁文件整理应交给 `competition-runtime-prep-skill`。

## best 与 trust

竞赛记录里要区分三个概念：

| 字段 | 含义 |
|------|------|
| `best_score` / `best_version` | 当前索引使用的主线最优 |
| `trusted_best_score` / `trusted_best_version` | 经过稳定性、holdout 或泄漏风险检查后，推荐提交和继续派生的可信主线 |
| `highest_observed_score` / `highest_observed_version` | 历史上观测到的最高分数，只代表分数高，不代表可信 |

### 更新规则

**默认行为**（由 `experiment.py --mode record` 自动执行）：

- `decision == "keep"` 且分数优于当前 `best_score` 时，同时更新 `best_*` 和 `trusted_best_*`。
- 这意味着大多数 keep 版本默认进入可信主线。

**人工回退**（Agent 或用户手动修正）：

如果后续发现某个已被写入 `trusted_best_*` 的版本存在以下问题，应手动回退：

1. 将 `trusted_best_score` / `trusted_best_version` 回退到上一个稳定版本。
2. 把问题版本的分数和版本号写入 `highest_observed_score` / `highest_observed_version`。
3. 在该版本的 experiment entry 中设置 `trust_status` 为 `"holdout_unstable"`、"`tie_with_best_more_complex`" 或其他合适的值。
4. 把原因写进该版本的 `findings`，供后续 Agent 参考。

后续 Agent 做实验时优先从 `trusted_best_version` 派生；只有用户明确要求复核历史最高观测版本时，才从 `highest_observed_version` 继续。

## experiment entry

```json
{
  "version": "<family>_b<NNN>_<slug>",
  "name": "<descriptive name>",
  "phase": "<phase>",
  "status": "completed|failed",
  "score": 0.0,
  "decision": "keep|discard|crash",
  "hypothesis": "<what was tested>",
  "description": "<what was changed>",
  "started_at": "<iso8601>",
  "completed_at": "<iso8601>",
  "findings": "<key insight>",
  "inspired_by": ["<paper_id>"],
  "method_tested": "<method_name>",
  "pipeline_layer": "features|loss|model|post-processing|strategy",
  "role": "trusted_best|evidence_only|negative_evidence|historical_high_observed",
  "trust_status": "trusted_best|below_trusted_best|holdout_unstable|tie_with_best_more_complex"
}
```

字段要求：

- `version` 必须使用 `{family}_b{NNN}_{slug}`。详细规则见 `references/baseline-naming.md`。
- `score` 必须是竞赛最终指标或与最终指标一致的验证代理。
- `findings` 要写清为什么 keep 或 discard。
- `pipeline_layer` 用来分析后续资源投向。
- `inspired_by` 用论文 ID 连接参考文献和实验。

实验版本记录要和文件系统对齐。出现以下任一情况时，先补记录再继续：

- `outputs/<version>/run_summary.json` 存在，但 `experiments` 中没有该版本。
- `outputs/logs/<version>.log` 有最终分数，但 `decision` 为空。
- `baselines/<version>/` 已存在且不是本轮刚创建。
- 当前 best 指向旧版本，但更新日志和输出显示新版本已经超过它。

## anti_patterns

```json
{
  "pattern": "<description>",
  "consequence": "<what happened>",
  "source_version": "<version>",
  "category": "evaluation|feature_engineering|model|ensemble|strategy|post_processing"
}
```

写入条件：

- 代理指标改善但最终指标下降。
- 同一方向多轮无收益。
- 复杂度明显增加但分数持平。
- 运行成本超预算。
- 方法和竞赛约束不匹配。

## priority_queue

```json
{
  "priority": 1,
  "direction": "<what to try>",
  "candidate_version": "<family>_b<NNN>_<slug>",
  "slug": "<slug-for-next-version>",
  "rationale": "<why>",
  "phase": "<phase>"
}
```

优先队列要来自真实证据：

- 已 keep 的版本显示出局部收益。
- 论文和当前问题有直接映射。
- 反模式排除了更差方向。
- 用户明确要求尝试某条路线。

如果优先队列指向下一轮可执行实验，尽量写 `candidate_version`。只有还没分配编号时才写 `slug`，并在启动前用 `scripts/baseline_names.py --mode next` 生成正式版本名。

## references/index.json

```json
{
  "project": "<competition-name>",
  "last_updated": "<iso8601>",
  "papers": [
    {
      "id": "<paper_id>",
      "title": "<title>",
      "authors": [],
      "year": "2025",
      "arxiv_id": "<id>",
      "category": "direct|adjacent|exploratory",
      "status": "unread|read|extracted|tried|succeeded|failed",
      "next_action": "try|revisit_later|skip",
      "key_methods": [],
      "implementation_notes": "<notes>",
      "topic": "uncertainty_and_intervals|storage_arbitrage_decision|exogenous_forecasts|strategy_optimization|neural_operator_methods",
      "kg_status": "not_ingested|ingested|outdated",
      "path": "<relative path>"
    }
  ]
}
```

物理目录按稳定主题分组：

| 目录 | 用途 |
|------|------|
| `papers/uncertainty_and_intervals/` | 分位数预测、概率预测、conformal、区间校准和风险控制 |
| `papers/storage_arbitrage_decision/` | 储能套利、收益导向预测、decision-focused learning、机会价值函数、predict-then-bid |
| `papers/exogenous_forecasts/` | 负荷、风电、光伏等外生变量的概率预测 |
| `papers/strategy_optimization/` | 储能策略求解、随机动态规划、HJB/FP 等优化方法 |
| `method_notes/neural_operator/` | PINN、DeepONet、FNO、算子逼近和优化器背景材料 |

分类口径：

| 分类 | 含义 |
|------|------|
| `direct` | 方法和赛题目标、数据或决策结构直接匹配 |
| `adjacent` | 思路相关，但需要较多改造 |
| `exploratory` | 研究价值高，但当前不适合立即试 |

`next_action=try` 的论文应能落到一个具体实验假设，不能只写“值得研究”。

## AGENTS.md 生成

项目 `AGENTS.md` 是给新 Agent 的压缩入口。它应该来自结构化索引，而不是手工堆长文。

必须包含：

- 当前最优版本和分数。
- 当前阶段。
- 反模式。
- 优先队列。
- 最近实验。
- baseline 版本命名规则和校验命令。
- 常用命令。
- HTML 看板路径。

当 best_score、反模式或优先队列变化时，先运行 `scripts/update_research_views.py` 刷新研究视图，再运行 `scripts/update_agents.py` 重生成。

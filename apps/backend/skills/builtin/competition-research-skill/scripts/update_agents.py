#!/usr/bin/env python3
"""基于实验数据生成 AGENTS.md。

用法:
    python3 generate.py --experiments /workspace/experiments/index.json --output /workspace/AGENTS.md

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_RESEARCH_DASHBOARD_PATH = "research_views/current.html"


def get_workspace_root() -> Path:
    ws_root = os.environ.get("AIASYS_WORKSPACE_ROOT", "")
    if ws_root:
        return Path(ws_root).resolve()
    raise RuntimeError("无法确定工作区根目录")


def resolve_path(raw: str, workspace_root: Path) -> Path:
    normalized = raw.replace("\\", "/").strip()
    if normalized.startswith("/workspace/"):
        rel = Path(normalized[len("/workspace/") :])
    elif normalized == "/workspace":
        rel = Path(".")
    else:
        rel = Path(normalized)
    host = (workspace_root / rel).resolve()
    try:
        host.relative_to(workspace_root)
    except ValueError:
        raise PermissionError(f"路径超出工作区: {raw}")
    return host


def _escape_md(value) -> str:
    return str(value or "").replace("|", "\\|").strip()


def _format_score(score) -> str:
    if score is None:
        return "N/A"
    return str(score)


def _format_version(version) -> str:
    if not version:
        return "N/A"
    return str(version)


def _format_anti_patterns(anti_patterns: list) -> str:
    if not anti_patterns:
        return "暂无记录。每轮 discard 后都要把原因写回 experiments/index.json。"

    lines = []
    for item in anti_patterns[:12]:
        if isinstance(item, dict):
            pattern = _escape_md(item.get("pattern"))
            details = []
            if item.get("consequence"):
                details.append(f"后果：{_escape_md(item.get('consequence'))}")
            if item.get("source_version"):
                details.append(f"来源：`{_escape_md(item.get('source_version'))}`")
            if item.get("category"):
                details.append(f"类别：{_escape_md(item.get('category'))}")
            suffix = f"（{'；'.join(details)}）" if details else ""
            lines.append(f"- {pattern}{suffix}")
        else:
            lines.append(f"- {_escape_md(item)}")
    return "\n".join(lines)


def _format_priority_queue(priority_queue: list) -> str:
    if not priority_queue:
        return "暂无优先队列。下一轮先根据当前 phase、论文注册表和反模式补充。"

    rows = [
        "| 优先级 | 方向 | 候选版本 | 阶段 | 理由 |",
        "|--------|------|----------|------|------|",
    ]
    for item in priority_queue[:10]:
        if isinstance(item, dict):
            rows.append(
                "| {priority} | {direction} | {candidate_version} | {phase} | {rationale} |".format(
                    priority=_escape_md(item.get("priority", "")),
                    direction=_escape_md(item.get("direction", "")),
                    candidate_version=_escape_md(
                        item.get("candidate_version")
                        or item.get("version")
                        or item.get("slug")
                        or ""
                    ),
                    phase=_escape_md(item.get("phase", "")),
                    rationale=_escape_md(item.get("rationale", "")),
                )
            )
        else:
            rows.append(f"| | {_escape_md(item)} | | | |")
    return "\n".join(rows)


def _format_recent_experiments(experiments: list) -> str:
    if not experiments:
        return "暂无实验记录。先运行 v0 baseline，再开始自动循环。"

    rows = [
        "| 版本 | 阶段 | 分数 | 决策 | 发现 |",
        "|------|------|------|------|------|",
    ]
    for exp in experiments[-8:]:
        rows.append(
            "| {version} | {phase} | {score} | {decision} | {findings} |".format(
                version=f"`{_escape_md(exp.get('version', ''))}`",
                phase=_escape_md(exp.get("phase", "")),
                score=_escape_md(_format_score(exp.get("score"))),
                decision=_escape_md(exp.get("decision", "")),
                findings=_escape_md(exp.get("findings", "")),
            )
        )
    return "\n".join(rows)


def _graph_config(data: dict) -> tuple[str, str]:
    graph_id = str(data.get("knowledge_graph_id") or "").strip()
    graph_path = str(data.get("knowledge_graph_db_path") or "").strip()
    graph_file = str(data.get("knowledge_graph_file") or "").strip()

    if not graph_id and graph_file:
        graph_id = Path(graph_file).stem.removesuffix(".graph")
    if not graph_path:
        graph_path = (
            f"/global/resources/graphs/{graph_id}.db"
            if graph_id
            else graph_file or "<project-slug>.graph.db"
        )
    if not graph_id:
        graph_id = "<project-slug>"
    return graph_id, graph_path


def _runner_config(data: dict) -> tuple[str, str, str, str, str, str]:
    runner = data.get("runner") if isinstance(data.get("runner"), dict) else {}
    runner_type = str(runner.get("type") or "builtin_experiment").strip()
    runner_command = str(
        runner.get("command")
        or "python3 scripts/experiment.py --mode run --experiments experiments/index.json --workspace <dir> --version {version}"
    ).strip()
    record_policy = str(runner.get("record_policy") or "experiment_record").strip()
    expected_runtime = runner.get("expected_runtime_minutes")
    expected_runtime_text = (
        f"{expected_runtime} 分钟" if expected_runtime not in (None, "") else "未登记"
    )
    long_running = "是" if runner.get("long_running") else "否"
    background_required = "是" if runner.get("background_required") else "否"
    return (
        runner_type,
        runner_command,
        record_policy,
        expected_runtime_text,
        long_running,
        background_required,
    )


def _runtime_contract_config(data: dict) -> tuple[str, str, str, str, str]:
    contract = (
        data.get("runtime_contract") if isinstance(data.get("runtime_contract"), dict) else {}
    )
    mode = str(contract.get("mode") or "stable_bound_environment").strip()
    env_id = str(contract.get("env_id") or "workspace-default").strip()
    imports = contract.get("preflight_imports")
    if isinstance(imports, list) and imports:
        preflight_imports = ", ".join(
            f"`{_escape_md(item)}`" for item in imports if str(item).strip()
        )
    else:
        preflight_imports = "未登记"
    large_dependency_policy = str(
        contract.get("large_dependency_policy") or "pause_and_request_runtime_prep"
    ).strip()
    observation_path = str(
        contract.get("observation_path") or "outputs/observations/<date>-auto-research.md"
    ).strip()
    return mode, env_id, preflight_imports, large_dependency_policy, observation_path


def generate_agents_md(data: dict) -> str:
    """根据 experiments/index.json 数据生成 AGENTS.md 内容。"""
    competition = data.get("competition", "Unknown Competition")
    metric = data.get("metric", "Unknown Metric")
    direction = data.get("direction", "minimize")
    best_score = data.get("best_score")
    best_version = data.get("best_version")
    trusted_best_score = data.get("trusted_best_score")
    trusted_best_version = data.get("trusted_best_version")
    highest_observed_score = data.get("highest_observed_score")
    highest_observed_version = data.get("highest_observed_version")
    current_phase = data.get("current_phase", "literature")
    anti_patterns = data.get("anti_patterns", [])
    priority_queue = data.get("priority_queue", [])
    experiments = data.get("experiments", [])
    graph_id, graph_path = _graph_config(data)
    (
        runner_type,
        runner_command,
        record_policy,
        expected_runtime_text,
        long_running,
        background_required,
    ) = _runner_config(data)
    (
        runtime_mode,
        runtime_env_id,
        runtime_preflight_imports,
        runtime_large_dependency_policy,
        runtime_observation_path,
    ) = _runtime_contract_config(data)
    research_dashboard_path = str(
        data.get("research_dashboard_path") or DEFAULT_RESEARCH_DASHBOARD_PATH
    ).strip()
    auto_task_ids = data.get("auto_task_ids", [])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    best_score_str = _format_score(best_score)
    best_version_str = _format_version(best_version)
    trusted_best_score_str = _format_score(trusted_best_score)
    trusted_best_version_str = _format_version(trusted_best_version)
    highest_observed_score_str = _format_score(highest_observed_score)
    highest_observed_version_str = _format_version(highest_observed_version)
    anti_patterns_md = _format_anti_patterns(anti_patterns)
    priority_queue_md = _format_priority_queue(priority_queue)
    recent_experiments_md = _format_recent_experiments(experiments)
    auto_task_str = ", ".join(auto_task_ids) if auto_task_ids else "N/A"
    direction_text = "最小化" if direction == "minimize" else "最大化"

    md = f"""# {competition} Agent Onboarding

> 用途：给新进入该竞赛项目的 Agent 快速同步当前状态、有效方向和禁忌方向。
> 生成日期：{now}

---

## 1. 快速开始

| 项目 | 当前值 |
|------|--------|
| 比赛目标 | {direction_text} `{metric}` |
| 当前最优分数 | `{best_score_str}` |
| 当前最优版本 | `{best_version_str}` |
| 可信最优版本 | `{trusted_best_version_str}` |
| 可信最优分数 | `{trusted_best_score_str}` |
| 历史最高观测版本 | `{highest_observed_version_str}` |
| 历史最高观测分数 | `{highest_observed_score_str}` |
| 当前阶段 | `{current_phase}` |

关键文件：
- `AGENTS.md`：Agent 接手入口，包含当前状态、反模式、优先队列、实验命令和自动研究配置。
- `statement/README.md`：题面材料入口和说明。
- `statement/description.md`：完整题面文本。
- `data/README.md`：数据目录职责和读写边界。
- `data/raw/README.md`：原始数据边界和官方样例位置。
- `data/raw/official_data/`：官方原始数据和官方提交格式示例。
- `experiments/index.json`：实验历史、best_score、反模式、优先队列。
- `experiments/README.md`：实验台账说明。
- `references/README.md`：论文和方法参考目录说明。
- `references/index.json`：论文注册表和可迁移方法记录。
- `research_views/README.md`：研究视图层说明。
- `research_views/current.html`：自动研究状态看板，放当前状态、下一步和证据入口。
- `research_views/echarts/`：ECharts 可视化图表，放实验得分演进、模型族对比、反模式分布和决策统计。
- `baselines/README.md`：当前推荐 baseline 和历史代码快照。
- `baseline_history/README.md`：历史 baseline 迭代汇总和结果对照。
- `.env/README.md`：工作区 UV 环境说明。
- `scripts/README.md`：脚本来源和使用边界说明。
- `outputs/`：提交文件、日志和结果对照。

---

## 2. 评估纪律

每轮 keep/discard 必须按 `{metric}` 和 `{direction}` 判断。RMSE、MAE、loss、训练集分数等代理指标只能辅助诊断，不能覆盖最终评分指标。

如果实验提高了代理指标但降低了最终指标，记录为 discard，并把原因写进 `anti_patterns`。

`可信最优版本` 是当前推荐提交和继续派生的主线。`历史最高观测版本` 只表示曾经出现过更高分数，如果 holdout、泄漏风险或稳定性不满足要求，不能直接接管主线。

---

## 3. 当前反模式

{anti_patterns_md}

---

## 4. 下一步优先队列

{priority_queue_md}

---

## 5. 最近实验

{recent_experiments_md}

---

## 6. 核心循环

1. 读 `experiments/index.json`、本文件和必要的题面说明。
2. 先检查 `anti_patterns`，避免重复已经证伪的路线。
3. 确认 `runner` 配置、本轮执行入口和 `runtime_contract`。
4. 选择优先队列最前面的方向，写清实验假设。
5. 复制上一轮 keep 版本或指定 baseline，做最小可解释改动。
6. 运行 `experiment.py --mode preflight`，检查 runner 锁、候选版本、未记录输出和当前环境。
7. 只在 preflight 通过后按 runner 运行实验，保存日志、进度心跳和输出文件。
8. 按最终指标判断 keep、discard 或 crash。
9. 用 `experiment.py --mode record` 写回结果。
10. 每轮 record 后运行 `update_research_views.py`，刷新 `research_views/current.html`。
11. 分数、方向或分支结构明显变化后，重新运行 `update_agents.py`。
12. 每轮 record 后运行 `generate_echarts.py` 刷新 `research_views/echarts/` 可视化图表。

baseline 版本名必须使用 `{{family}}_b{{NNN}}_{{slug}}`，例如 `lgb_b045_pairranker_on_trigrid`。同一 family 内编号单调递增，目录名、`experiments[].version`、输出目录和日志名保持一致。需要下一个版本名时运行 `python3 scripts/baseline_names.py --mode next --family <family> --slug <slug>`。

---

## 7. 常用命令

查看状态：

```bash
python3 scripts/experiment.py --mode status --experiments experiments/index.json --workspace <dir>
```

生成建议：

```bash
python3 scripts/experiment.py --mode plan --experiments experiments/index.json --workspace <dir>
```

运行新实验。`runner.type=builtin_experiment` 时使用：

```bash
python3 scripts/experiment.py --mode run --experiments experiments/index.json --workspace <dir> \
  --from_version <best_version> --version <new_version> --name <name> --hypothesis "<假设>"
```

其他类型 runner 按 `experiments/index.json` 的 `runner.command` 执行。

记录结果：

```bash
python3 scripts/experiment.py --mode record --experiments experiments/index.json --workspace <dir> \
  --version <new_version> --score <score> --decision keep --findings "<发现>"
```

更新本文件：

```bash
python3 scripts/update_agents.py --experiments experiments/index.json --output AGENTS.md
```

更新研究视图：

```bash
python3 scripts/update_research_views.py --experiments experiments/index.json --output-dir research_views
```

---

## 8. 自动研究配置

- runner 类型：`{runner_type}`
- runner 命令：`{runner_command}`
- 记录策略：`{record_policy}`
- 预计单轮耗时：`{expected_runtime_text}`
- 长任务：`{long_running}`
- 需要后台监控：`{background_required}`
- 进度日志要求：长耗时 runner 必须输出阶段心跳，建议用 `SpawnMonitor` 启动并用 `ManageMonitor(action="poll")` 轮询
- 知识图谱 ID：`{graph_id}`
- 知识图谱路径：`{graph_path}`
- 论文注册表：`references/index.json`
- 实验注册表：`experiments/index.json`
- Auto Task IDs：{auto_task_str}
- HTML 看板：`{research_dashboard_path}`
- ECharts 可视化：`research_views/echarts/`
- 运行环境模式：`{runtime_mode}`
- 建议 env_id：`{runtime_env_id}`
- 预检导入：{runtime_preflight_imports}
- 大依赖策略：`{runtime_large_dependency_policy}`
- 环境观察记录：`{runtime_observation_path}`

阶段流转：

```
literature -> feature -> model -> ensemble
```

---

## 9. 运行环境门禁

本项目的自动研究默认只使用当前已绑定或已登记环境，不在正式实验轮里安装大依赖。

- 启动 runner 前只做轻量 preflight：检查当前 `env_id`、关键包导入、包版本、runner 路径、候选版本冲突和输出目录。
- 预计超过 2 分钟的 runner 要用 Monitor 跑，不要用普通 Shell 长时间阻塞等待。runner 代码至少在数据加载、特征构建、每个模型/候选训练、候选评分、产物写入和最终指标处打印进度；Python baseline 使用 `print(..., flush=True)` 或 `python -u`。
- 缺少 `torch`、`xgboost`、`catboost`、CUDA 相关包或其他大 wheel 时，把阻塞写入 `{runtime_observation_path}`，暂停 AutoTask，并转交 `competition-runtime-prep-skill`。
- 需要同时探索多个环境或多个 AutoTask lane 时，先转交 `competition-parallel-research-skill` 规划 lane、`env_id`、会话和写回顺序。
- 环境安装、GPU smoke 和锁文件整理只记录到环境报告或 observation，不写成正式实验 keep/discard。

---

## 10. 结构迭代规则

本项目仍处于 0-1 开发阶段。Agent 发现目录、研究视图、脚本入口、runner 或自动研究流程不符合当前事实时，应直接按新结构整理，不为旧结构保留兼容别名或双轨入口。

具体要求：

- 以 `experiments/index.json`、知识图谱和当前 runner 事实为准。
- `AGENTS.md` 是 Agent 执行约束入口，README 只做目录说明。
- `research_views/current.html` 是自动研究状态看板，每轮 record 后优先更新。
- `research_views/echarts/` 是 ECharts 可视化图表目录，由 `scripts/generate_echarts.py` 自动生成，用于数据驱动的实验分析。
- 默认用 `scripts/update_research_views.py` 刷新 HTML 看板，用 `scripts/generate_echarts.py` 刷新可视化图表。
- 过期命名、旧路径、重复入口和无效历史说明直接清理。
- 清理后运行对应校验脚本，不用兼容层掩盖结构问题。

---

本文件由 `competition-research-skill/scripts/update_agents.py` 生成。它只负责压缩当前竞赛状态，详细代码和实验结果仍以项目文件为准。
"""
    return md


def main():
    parser = argparse.ArgumentParser(description="基于实验数据生成 AGENTS.md")
    parser.add_argument(
        "--experiments",
        required=True,
        help="experiments/index.json 路径",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="输出 AGENTS.md 的路径",
    )
    args = parser.parse_args()

    try:
        workspace_root = get_workspace_root()
        experiments_path = resolve_path(args.experiments, workspace_root)
        output_path = resolve_path(args.output, workspace_root)

        if not experiments_path.exists():
            raise FileNotFoundError(f"实验索引文件不存在: {experiments_path}")

        data = json.loads(experiments_path.read_text(encoding="utf-8"))

        md_content = generate_agents_md(data)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md_content, encoding="utf-8")

        result = {
            "status": "ok",
            "output": str(output_path),
            "competition": data.get("competition", "unknown"),
            "best_score": data.get("best_score"),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

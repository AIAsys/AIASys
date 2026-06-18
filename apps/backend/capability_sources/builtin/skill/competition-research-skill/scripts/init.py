#!/usr/bin/env python3
"""初始化竞赛项目目录结构。

用法:
    python3 init.py --name "electricity-competition" --metric "Profit" --direction maximize --output_dir /workspace/projects

环境变量:
    AIASYS_WORKSPACE_ROOT: 工作区根目录
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from update_research_views import (
    build_research_dashboard_html,
)

DEFAULT_RESEARCH_DASHBOARD_PATH = "research_views/current.html"


def get_workspace_root() -> Path:
    ws_root = os.environ.get("AIASYS_WORKSPACE_ROOT", "")
    if ws_root:
        return Path(ws_root).resolve()
    raise RuntimeError("无法确定工作区根目录")


def resolve_path(raw: str, workspace_root: Path) -> Path:
    p = Path(raw)
    if p.is_absolute():
        rel = (
            Path(*p.parts[2:]) if str(p) == "/workspace" or str(p).startswith("/workspace/") else p
        )
    else:
        rel = p
    host = (workspace_root / rel).resolve()
    try:
        host.relative_to(workspace_root)
    except ValueError:
        raise PermissionError(f"路径超出工作区: {raw}")
    return host


AGENTS_MD_TEMPLATE = """# {name} Agent Onboarding

> 用途：给新进入该竞赛项目的 Agent 快速同步目标、数据、实验规则和自动循环入口。
> 生成日期：{date}

---

## 1. 快速开始

| 项目 | 当前值 |
|------|--------|
| 比赛目标 | {direction} `{metric}` |
| 当前最优分数 | 待建立 v0 baseline |
| 当前最优版本 | 待建立 |
| 当前阶段 | `literature` |

关键文件：
- `AGENTS.md`：Agent 接手入口，包含目标、数据、实验规则、常用命令和自动研究配置。
- `statement/README.md`：题面材料入口和说明。
- `statement/description.md`：完整题面文本。
- `data/README.md`：数据目录职责和读写边界。
- `data/raw/README.md`：原始数据说明。
- `data/raw/official_data/`：官方原始数据和官方提交格式示例。
- `experiments/index.json`：实验历史、best_score、反模式、优先队列。
- `experiments/README.md`：实验台账说明。
- `references/index.json`：论文注册表。
- `research_views/README.md`：研究视图层说明。
- `research_views/current.html`：自动研究状态看板，放当前状态、下一步和证据入口。
- `research_views/echarts/`：ECharts 可视化图表目录，放实验趋势、指标对比和探索会话进度图。
- `research_views/data_exploration/`：数据探索目录，放 bootstrap 阶段生成的原始数据画像、分布和相关性图表。
- `baselines/README.md`：当前推荐 baseline 和历史代码快照。
- `baseline_history/README.md`：历史 baseline 迭代汇总和结果对照。
- `.env/README.md`：工作区 UV 环境说明。
- `scripts/README.md`：脚本来源和使用边界说明。
- `outputs/logs/`：实验 stdout、stderr 和崩溃线索。

---

## 2. 启动前置条件

Auto Task 启动前必须满足这些条件：

| 前置条件 | 需要训练数据的竞赛 | 纯算法题 |
|----------|--------------------|----------|
| 竞赛类型已确认 | 必须 | 必须 |
| `AGENTS.md` 已指向题面、数据、实验和输出入口 | 必须 | 必须 |
| `data/raw/` 有真实数据 | 必须 | 不需要 |
| `baselines/` 有可运行代码 | 必须 | 必须 |
| `experiments/index.json` 已登记 runner | 必须 | 必须 |
| `.env/` 的 UV 环境已初始化 | 必须 | 不需要 |
| v0 baseline 已跑通 | 必须 | 必须 |

缺数据时暂停请求用户补全。不能用随机数、生成数据或手写假数据替代真实训练数据。

---

## 3. 竞赛上下文

### 评估指标

`{metric}`，优化方向为 {direction}。

把公式、提交字段、验证集切分和 leaderboard 规则补到 `statement/description.md`。`AGENTS.md` 只保留当前状态和执行入口，不维护第二份题面摘要。

### 数据来源类型

- [ ] 平台提供文件，如 Kaggle、天池、竞赛附件。
- [ ] 平台内嵌数据，只能在平台 notebook 中访问。
- [ ] 纯算法题，不需要外部训练数据。
- [ ] 用户自有数据，用户上传到 `data/raw/`。
- [ ] 需要自行采集，采集脚本和结果都要落盘。
- [ ] API 对抗型，如交易、游戏、仿真环境。

---

## 4. 关键文件指南

| Priority | File | What You Learn |
|----------|------|----------------|
| 1 | `AGENTS.md` | 当前状态、反模式、优先队列和自动研究配置 |
| 2 | `statement/README.md` | 题面材料入口和说明 |
| 3 | `data/README.md` | 数据目录职责和读写边界 |
| 4 | `data/raw/README.md` | 原始数据边界和官方样例位置 |
| 5 | `data/raw/official_data/` | 官方原始数据和提交示例 |
| 6 | `experiments/index.json` | 实验历史、best_score、反模式、优先队列 |
| 7 | `references/index.json` | 论文和可迁移方法 |
| 8 | `baselines/` | 可运行起点 |
| 9 | `.env/README.md` | 本工作区 UV 运行环境 |
| 10 | `outputs/` | 输出、日志、提交文件和报告 |

---

## 5. 实验记忆规则

### Baseline 命名

baseline 版本名必须使用 `{{family}}_b{{NNN}}_{{slug}}`，例如 `lgb_b000_base`、`lgb_b001_price_features`。

同一 family 内编号单调递增。目录名、`experiments[].version`、输出目录和日志名必须使用同一个 version。需要下一个版本名时运行：

```bash
python3 scripts/baseline_names.py --mode next --family <family> --slug <slug>
```

启动 runner 前先校验：

```bash
python3 scripts/baseline_names.py --mode validate --workspace <workspace-root> --experiments experiments/index.json
```

### 实验循环

```
Analyze State -> Form Hypothesis -> Implement -> Run -> Evaluate -> Record
```

每轮先读 `anti_patterns` 和 `priority_queue`，再决定实验方向。
启动 runner 前先运行 `experiment.py --mode preflight`，检查 runner 锁、候选版本、未记录输出和当前环境。
正式实验轮只做轻量环境预检，不安装 `torch`、`xgboost`、`catboost`、CUDA 相关包或其他大依赖。

### Runner

`experiment.py --mode run` 是内置模板 runner。项目已有复跑脚本、平台 notebook、官方评测 CLI、仿真入口或 API 交互脚本时，先在 `experiments/index.json` 的 `runner` 字段登记项目入口，再启动自动循环。

runner 只负责执行、日志和产物路径。最优版本和反模式仍通过 `experiment.py --mode record` 或同 schema 记录器写回。

### Keep / discard / crash

| 情况 | 决策 | 动作 |
|------|------|------|
| 最终指标显著优于当前 best_score | keep | 更新 best_score，保留代码和输出 |
| 最终指标持平或收益太小 | discard | 记录原因，必要时写入 anti_patterns |
| 最终指标下降 | discard | 写清后果和来源版本 |
| 运行失败或超时 | crash | 调试一次，仍失败就记录并停止该方向 |

代理指标只能辅助诊断。每个竞赛都要明确最终评分指标，不能只按训练 loss、RMSE、MAE 或局部指标决定 keep。

---

## 6. 常用命令

查看状态：

```bash
python3 scripts/experiment.py --mode status --experiments experiments/index.json --workspace <dir>
```

生成实验建议：

```bash
python3 scripts/experiment.py --mode plan --experiments experiments/index.json --workspace <dir>
```

运行 v0：

```bash
python3 scripts/experiment.py --mode run --experiments experiments/index.json --workspace <dir> \
  --version <family>_b000_base --name baseline --hypothesis "建立基准"
```

如果 `runner.type` 不是 `builtin_experiment`，按 `runner.command` 执行本项目入口。

在上一轮 keep 版本基础上继续：

```bash
python3 scripts/experiment.py --mode run --experiments experiments/index.json --workspace <dir> \
  --from_version <best_version> --version <new_version> --name <name> --hypothesis "<假设>"
```

记录结果：

```bash
python3 scripts/experiment.py --mode record --experiments experiments/index.json --workspace <dir> \
  --version <version> --score <score> --decision keep --findings "<发现>"
```

更新研究视图：

```bash
python3 scripts/update_research_views.py --experiments experiments/index.json --output-dir research_views
```

更新本文件：

```bash
python3 scripts/update_agents.py --experiments experiments/index.json --output AGENTS.md
```

---

## 7. Skill 参考

| Skill | 用途 |
|-------|------|
| `competition-runtime-prep-skill` | 竞赛运行环境准备、依赖安装、GPU 和 runner smoke |
| `competition-research-skill` | 单会话、单环境、串行竞赛实验闭环 |
| `competition-parallel-research-skill` | 多会话、多环境、多 AutoTask lane 编排 |
| `arxiv-search-skill` | 通用论文搜索和 PDF 下载 |
| `pymupdf4llm-pdf-to-markdown-skill` | PDF 转 Markdown |
| `pdf-translate-skill` | PDF 保版式翻译 |
| `paddleocr-skill` | 扫描版 PDF OCR |

---

## 8. 目录参考

```
./
├── AGENTS.md                  # This file
├── statement/
│   ├── README.md               # 题面材料入口
│   ├── description.md          # 题面文本
├── data/
│   ├── README.md               # 数据目录职责说明
│   ├── raw/
│   │   ├── README.md           # 原始数据说明
│   │   └── official_data/      # 官方原始数据和提交示例
│   └── processed/              # Feature engineering outputs
├── references/                # 论文和方法参考
│   ├── index.json             # 论文注册表
│   ├── papers/                # 按研究主题分组的论文
│   └── method_notes/          # 方法视野材料
├── baselines/                 # Baseline code (READ-ONLY)
├── baseline_history/           # 历史 baseline 汇总记录
├── experiments/
│   └── README.md               # 实验台账说明
│   └── index.json             # Experiment registry + anti-patterns
├── research_views/
│   ├── README.md
│   ├── current.html
│   ├── echarts/
│   └── data_exploration/
├── .env/
│   ├── README.md               # 本工作区 UV 环境说明
│   ├── environments.json
│   ├── pyproject.toml
│   ├── uv.lock
│   └── .venv/
├── scripts/
│   ├── README.md               # 脚本来源和使用边界
│   ├── baseline_names.py       # baseline 命名校验和下一个版本建议
│   ├── update_research_views.py # 研究视图生成
│   └── *.py
└── outputs/
    ├── submissions/           # Prediction files
    ├── logs/                  # stdout / stderr
    └── reports/               # Reports
```

---

本文件是项目内 Agent 入职文档，也是当前竞赛执行入口。详细题面规则仍以 `statement/description.md` 为准，实验事实以 `experiments/index.json` 为准。
"""


def main():
    parser = argparse.ArgumentParser(description="初始化竞赛项目目录结构")
    parser.add_argument("--name", required=True, help="项目名称")
    parser.add_argument("--metric", required=True, help="评估指标名称")
    parser.add_argument(
        "--direction",
        required=True,
        choices=["minimize", "maximize"],
        help="优化方向 (minimize 或 maximize)",
    )
    parser.add_argument("--output_dir", required=True, help="输出目录路径")
    args = parser.parse_args()

    try:
        workspace_root = get_workspace_root()
        output_dir = resolve_path(args.output_dir, workspace_root)
        project_dir = output_dir / args.name

        if project_dir.exists():
            raise FileExistsError(f"项目目录已存在: {project_dir}")

        # 创建目录结构
        dirs = [
            project_dir / "statement",
            project_dir / "data" / "raw",
            project_dir / "data" / "raw" / "official_data",
            project_dir / "data" / "processed",
            project_dir / "references" / "papers" / "uncertainty_and_intervals",
            project_dir / "references" / "papers" / "storage_arbitrage_decision",
            project_dir / "references" / "papers" / "exogenous_forecasts",
            project_dir / "references" / "papers" / "strategy_optimization",
            project_dir / "references" / "method_notes" / "neural_operator",
            project_dir / "baselines",
            project_dir / "baseline_history",
            project_dir / "experiments",
            project_dir / ".env",
            project_dir / "scripts",
            project_dir / "outputs" / "submissions",
            project_dir / "outputs" / "logs",
            project_dir / "outputs" / "reports",
            project_dir / "research_views",
            project_dir / "research_views" / "echarts",
            project_dir / "research_views" / "data_exploration",
            project_dir / "reports",
        ]
        created_dirs = []
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(d.relative_to(workspace_root)))

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 创建 AIASys 全局知识图谱 .db 文件
        graph_db_path = (
            workspace_root.parent / "global_workspace" / "resources" / "graphs" / f"{args.name}.db"
        )
        graph_db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(graph_db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _aiasys_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    description TEXT,
                    properties TEXT,
                    source_doc_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS relations (
                    relation_id TEXT PRIMARY KEY,
                    source_entity_id TEXT NOT NULL,
                    target_entity_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    description TEXT,
                    strength REAL DEFAULT 1.0,
                    properties TEXT,
                    source_doc_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS communities (
                    community_id TEXT PRIMARY KEY,
                    level INTEGER NOT NULL,
                    entity_ids TEXT,
                    summary TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS graph_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.execute(
                "INSERT OR REPLACE INTO _aiasys_metadata (key, value) VALUES (?, ?)",
                ("id", args.name),
            )
            conn.execute(
                "INSERT OR REPLACE INTO _aiasys_metadata (key, value) VALUES (?, ?)",
                ("resource_type", "graph"),
            )
            conn.execute(
                "INSERT OR REPLACE INTO graph_metadata (key, value) VALUES (?, ?)",
                ("name", args.name),
            )
            conn.commit()

        # 创建 experiments/index.json
        experiments_index = {
            "competition": args.name,
            "metric": args.metric,
            "direction": args.direction,
            "best_score": None,
            "best_version": None,
            "current_phase": "literature",
            "last_updated": now,
            "knowledge_graph_id": args.name,
            "knowledge_graph_db_path": f"/global/resources/graphs/{args.name}.db",
            "knowledge_graph_file": f"{args.name}.graph.db",
            "research_dashboard_path": DEFAULT_RESEARCH_DASHBOARD_PATH,
            "paper_registry_path": "references/index.json",
            "runner": {
                "type": "builtin_experiment",
                "command": "python3 scripts/experiment.py --mode run --experiments experiments/index.json --workspace . --version {version}",
                "default_version": None,
                "output_path": "outputs/{version}/output.csv",
                "log_path": "outputs/logs/{version}.log",
                "score_source": "stdout",
                "record_policy": "experiment_record",
            },
            "runtime_contract": {
                "mode": "stable_bound_environment",
                "env_id": "workspace-default",
                "preflight_imports": [],
                "large_dependency_policy": "pause_and_request_runtime_prep",
                "observation_path": "outputs/observations/<date>-auto-research.md",
            },
            "auto_task_ids": [],
            "experiments": [],
            "anti_patterns": [],
            "priority_queue": [],
        }
        experiments_path = project_dir / "experiments" / "index.json"
        experiments_path.write_text(
            json.dumps(experiments_index, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        # 创建 references/index.json
        references_index = {
            "project": args.name,
            "last_updated": now,
            "papers": [],
        }
        references_path = project_dir / "references" / "index.json"
        references_path.write_text(
            json.dumps(references_index, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        references_readme_path = project_dir / "references" / "README.md"
        references_readme_path.write_text(
            "# 论文和方法参考\n\n"
            "`references/` 放论文、方法笔记和机器可读索引。物理目录按稳定主题分组，行动价值、阅读状态和下一步建议写在 `index.json` 与知识图谱里。\n\n"
            "| 路径 | 放什么 |\n"
            "| --- | --- |\n"
            "| `papers/uncertainty_and_intervals/` | 分位数预测、概率预测、conformal、区间校准和风险控制 |\n"
            "| `papers/storage_arbitrage_decision/` | 储能套利、收益导向预测、decision-focused learning、机会价值函数、predict-then-bid |\n"
            "| `papers/exogenous_forecasts/` | 负荷、风电、光伏等外生变量的概率预测 |\n"
            "| `papers/strategy_optimization/` | 储能策略求解、随机动态规划、HJB/FP 等优化方法 |\n"
            "| `method_notes/neural_operator/` | PINN、DeepONet、FNO、算子逼近和优化器背景材料 |\n",
            encoding="utf-8",
        )

        statement_readme_path = project_dir / "statement" / "README.md"
        statement_readme_path.write_text(
            "# 题面材料\n\n"
            "`description.md` 是当前项目的完整题面文本，也是 Agent 阅读赛题原文的唯一长文本入口。\n\n"
            "`AGENTS.md` 是 Agent 接手入口，包含当前状态、反模式、优先队列、实验命令和自动研究配置，不复述题面正文。\n",
            encoding="utf-8",
        )

        statement_description_path = project_dir / "statement" / "description.md"
        statement_description_path.write_text(
            "# 题面文本\n\n请将完整题面文本整理到这里。\n",
            encoding="utf-8",
        )

        data_readme_path = project_dir / "data" / "README.md"
        data_readme_path.write_text(
            "# 数据目录\n\n"
            "`data/` 只放比赛数据和由实验生成的数据中间产物，不放提交文件、论文或运行日志。\n\n"
            "| 路径 | 用途 |\n"
            "| --- | --- |\n"
            "| `raw/README.md` | 原始数据的目录说明和读写边界 |\n"
            "| `raw/official_data/` | 官方原始数据和官方提交格式示例 |\n"
            "| `processed/` | 后续实验生成的特征表、缓存表和中间数据 |\n",
            encoding="utf-8",
        )

        raw_readme_path = project_dir / "data" / "raw" / "README.md"
        raw_readme_path.write_text(
            "# 原始数据\n\n"
            "`data/raw/` 放比赛原始数据和必须保留的官方样例，不放实验输出、提交文件或中间特征表。\n\n"
            "## 当前目录\n\n"
            "| 路径 | 用途 |\n"
            "| --- | --- |\n"
            "| `official_data/` | 当前比赛的官方原始数据根目录 |\n\n"
            "## 约定\n\n"
            "- 这里的文件默认只读，不要覆盖原始数据。\n"
            "- 如果后续补进新的官方附件，先放进 `data/raw/` 下的新子目录，再在这里补说明。\n"
            "- 官方提交示例文件如果存在，放在 `data/raw/official_data/` 并在这里补具体文件名。\n",
            encoding="utf-8",
        )

        official_data_readme_path = project_dir / "data" / "raw" / "official_data" / "README.md"
        official_data_readme_path.write_text(
            "# 官方数据\n\n"
            "这个目录是当前比赛实际读取的原始数据根目录。\n\n"
            "## 当前文件\n\n"
            "| 路径 | 用途 |\n"
            "| --- | --- |\n"
            "| （请补充实际数据文件） | |\n\n"
            "## 约定\n\n"
            "- runner 和 baseline 默认都从这里读官方原始数据。\n"
            "- 这里不放实验输出，不放提交结果，不放派生缓存。\n"
            "- 如果以后补入外部数据，应单独写清来源和读取方式，不要和官方原始数据混在一起。\n",
            encoding="utf-8",
        )

        baselines_readme_path = project_dir / "baselines" / "README.md"
        baselines_readme_path.write_text(
            "# baseline 代码快照\n\n"
            "这个目录放当前推荐 baseline 和历史 baseline 代码快照，不放提交结果和运行日志。\n\n"
            "baseline 目录名统一使用 `{family}_b{NNN}_{slug}`，例如 `lgb_b000_base`。\n\n"
            "实验事实、最终分数和 keep/discard 结论以 `experiments/index.json` 和 `baseline_history/` 为准。\n",
            encoding="utf-8",
        )

        baseline_history_readme_path = project_dir / "baseline_history" / "README.md"
        baseline_history_readme_path.write_text(
            "# baseline 历史汇总\n\n"
            "这个目录放 baseline 迭代记录和对照结果。版本代码快照放在 `baselines/` 根目录下。\n",
            encoding="utf-8",
        )

        experiments_readme_path = project_dir / "experiments" / "README.md"
        experiments_readme_path.write_text(
            "# 实验台账\n\n`experiments/` 存放竞赛研究的结构化实验事实。\n",
            encoding="utf-8",
        )

        env_readme_path = project_dir / ".env" / "README.md"
        env_readme_path.write_text(
            "# 运行环境\n\n"
            "`.env/` 是这个竞赛工作区的 UV 运行环境物料目录，不是 AIASys 后端自身的虚拟环境，也不是传统 dotenv 文件。\n\n"
            "API key、token 和服务地址通过 AIASys 工作区环境变量管理，不写进 `.env/`。\n",
            encoding="utf-8",
        )

        scripts_readme_path = project_dir / "scripts" / "README.md"
        scripts_readme_path.write_text(
            "# 工作区脚本\n\n"
            "这个目录放的是本工作区的可执行脚本副本。\n\n"
            "| 文件 | 职责 |\n"
            "| --- | --- |\n"
            "| `baseline_names.py` | baseline 版本名校验和下一个版本建议 |\n"
            "| `experiment.py` | 状态查看、实验规划、实验运行、结果记录 |\n"
            "| `update_agents.py` | 根据实验索引重建 `AGENTS.md` |\n"
            "| `update_research_views.py` | 根据实验索引重建 HTML 看板和 ECharts 可视化图表 |\n"
            "| `ingest.py` | 摄入论文，写入 `references/index.json` 和知识图谱 |\n"
            "| `arxiv_search.py` | 搜索论文候选 |\n",
            encoding="utf-8",
        )

        outputs_readme_path = project_dir / "outputs" / "README.md"
        outputs_readme_path.write_text(
            "# 输出目录\n\n"
            "`outputs/` 只放从现在开始新跑出的结果，避免和旧 Codex 运行记录混在一起。\n",
            encoding="utf-8",
        )

        # 创建 research_views/current.html
        research_html = build_research_dashboard_html(
            experiments_index,
            DEFAULT_RESEARCH_DASHBOARD_PATH,
        )
        research_views_readme_path = project_dir / "research_views" / "README.md"
        research_views_readme_path.write_text(
            "# 研究视图层\n\n"
            "`research_views/` 只放当前研究视图和说明，不放实验事实、论文原文或完整日志。\n\n"
            "- `current.html`：自动研究状态看板，放当前状态、下一步、风险和证据入口。\n"
            "- `echarts/`：ECharts 可视化图表目录，放实验趋势、指标对比和探索会话进度图。\n"
            "- `data_exploration/`：数据探索目录，放 bootstrap 阶段生成的原始数据画像、目标变量分布、特征相关性和时间模式图表。\n"
            "- 实验事实写在 `experiments/index.json`。\n"
            "- 论文和方法索引写在 `references/index.json`。\n"
            "- 可查询关系写入 AIASys 知识图谱。\n",
            encoding="utf-8",
        )

        research_dashboard_path = project_dir / "research_views" / "current.html"
        research_dashboard_path.write_text(research_html, encoding="utf-8")

        # 创建 AGENTS.md
        agents_md = AGENTS_MD_TEMPLATE.format(
            name=args.name,
            metric=args.metric,
            direction="最小化" if args.direction == "minimize" else "最大化",
            date=date_str,
        )
        agents_path = project_dir / "AGENTS.md"
        agents_path.write_text(agents_md, encoding="utf-8")

        created_files = [
            str(experiments_path.relative_to(workspace_root)),
            str(references_path.relative_to(workspace_root)),
            str(statement_readme_path.relative_to(workspace_root)),
            str(statement_description_path.relative_to(workspace_root)),
            str(data_readme_path.relative_to(workspace_root)),
            str(raw_readme_path.relative_to(workspace_root)),
            str(official_data_readme_path.relative_to(workspace_root)),
            str(baselines_readme_path.relative_to(workspace_root)),
            str(baseline_history_readme_path.relative_to(workspace_root)),
            str(experiments_readme_path.relative_to(workspace_root)),
            str(references_readme_path.relative_to(workspace_root)),
            str(env_readme_path.relative_to(workspace_root)),
            str(scripts_readme_path.relative_to(workspace_root)),
            str(outputs_readme_path.relative_to(workspace_root)),
            str(research_views_readme_path.relative_to(workspace_root)),
            str(research_dashboard_path.relative_to(workspace_root)),
            str(agents_path.relative_to(workspace_root)),
        ]

        result = {
            "project_name": args.name,
            "project_dir": str(project_dir.relative_to(workspace_root)),
            "created_dirs": created_dirs,
            "created_files": created_files,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

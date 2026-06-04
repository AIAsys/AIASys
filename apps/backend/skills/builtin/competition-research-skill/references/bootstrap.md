# Bootstrap 流程

Bootstrap 负责把“只有题目或少量材料”的竞赛，变成 Agent 可以持续推进的工作区。

## 前置确认

先向用户确认这些信息：

| 信息 | 用途 |
|------|------|
| 竞赛类型 | 决定数据和 baseline 前置条件 |
| 最终评估指标 | 决定 keep/discard 依据 |
| 优化方向 | `minimize` 或 `maximize` |
| 数据来源 | 判断是否能启动实验 |
| 提交格式 | 生成输出文件和验证脚本 |
| 时间预算 | 设置单轮 timeout 和 Auto Task 退出条件 |
| 是否已有 baseline | 决定复用用户代码还是建立 v0 |
| 项目 runner | 决定自动循环里实际调用哪个执行入口 |

## 竞赛类型与前置条件

| 竞赛类型 | 前置条件 |
|----------|----------|
| 平台提供文件 | `data/raw/` 有真实文件，`baselines/` 有可运行代码 |
| 平台内嵌数据 | 平台 notebook 可运行，`baselines/` 有代码 |
| 纯算法题 | 题意已理解，`baselines/` 有可运行代码 |
| 用户自有数据 | 用户上传真实数据，`baselines/` 有代码 |
| 需要自行采集 | 采集脚本和采集结果均已落盘 |
| API 对抗型 | 环境可连接，交互代码可运行 |

所有需要训练数据的竞赛都不能用随机数、生成数据或手写假数据替代。

## 初始化命令

```bash
python3 scripts/init.py --name <project-name> --metric <metric> --direction <minimize|maximize> --output_dir <dir>
```

环境变量：

```bash
export AIASYS_WORKSPACE_ROOT=<workspace-root>
```

生成目录：

```text
<project-name>/
├── AGENTS.md
├── statement/
│   ├── README.md
│   ├── description.md
├── data/
│   ├── README.md
│   ├── raw/
│   │   ├── README.md
│   │   └── official_data/
│   └── processed/
├── references/
│   ├── README.md
│   ├── index.json
│   ├── papers/
│   │   ├── uncertainty_and_intervals/
│   │   ├── storage_arbitrage_decision/
│   │   ├── exogenous_forecasts/
│   │   └── strategy_optimization/
│   └── method_notes/
│       └── neural_operator/
├── baselines/
├── baseline_history/
│   └── README.md
├── experiments/
│   └── index.json
├── .env/
│   ├── README.md
│   ├── environments.json
│   ├── pyproject.toml
│   ├── uv.lock
│   └── .venv/
├── scripts/
│   ├── README.md
│   ├── baseline_names.py
│   ├── arxiv_search.py
│   ├── experiment.py
│   ├── ingest.py
│   ├── init.py
│   ├── update_agents.py
│   └── update_research_views.py
├── outputs/
│   ├── submissions/
│   ├── logs/
│   └── reports/
└── research_views/
    ├── README.md
    ├── current.html
    ├── echarts/
    └── data_exploration/
```

`research_views/current.html` 是自动研究状态看板。它记录当前状态、下一步、风险和证据入口。


两者都不替代 `experiments/index.json`、`references/index.json` 或知识图谱。

`notebooks/` 不再是这个 skill 的默认目录结构。只有当题目本身要求 notebook 时，才按题目规则单独加，不要把它写进通用 bootstrap。

`.env/` 是 AIASys 管理的工作区 UV 运行环境物料目录，不是传统 dotenv 文件。API key、token 和服务地址用平台环境变量工具管理，不写进 `.env/`。

## 配置 runner

初始化时先确认本项目的执行入口，并写入 `experiments/index.json` 的 `runner` 字段：

- 简单 Python 或 ipynb baseline 可以使用 `builtin_experiment`，入口为 `scripts/experiment.py --mode run`。
- 项目已有复跑脚本时使用 `workspace_shell`，例如 `./run_baseline.sh {version}`。
- 平台 notebook、官方评测 CLI、仿真入口、API 交互脚本都登记为项目 runner。

runner 必须满足三件事：能重复执行、能保存日志、能给出可记录分数或产物。后续 best 判断仍通过 `experiment.py --mode record` 写回，除非项目提供同 schema 的记录器。

## 数据探索

在建立 v0 baseline 之前，先对 `data/raw/` 中的真实数据做一次系统性探索。这不是可选步骤，而是后续建模方向选择的依据。

**最小探索清单**：

| 检查项 | 目的 |
|--------|------|
| 样本量、特征维度、时间范围 | 判断数据规模，决定模型选型 |
| 目标变量分布（直方图、箱线图、偏度） | 识别极端值、不平衡、是否需要变换 |
| 缺失值比例和模式 | 决定缺失值处理策略 |
| 特征与目标的相关性排序 | 筛选强预测特征，识别冗余 |
| 时间序列特有检查（如适用） | 趋势、季节性、日内/周内模式、采样间隔一致性 |
| 类别特征基数和分布 | 决定编码策略 |

**输出要求**：

1. 将探索结果写成 Markdown 报告，存放到 `research_views/data_exploration/report.md`。
2. 生成至少 3 张可视化图表（matplotlib 或 ECharts），存放到 `research_views/data_exploration/`。命名用 `de_` 前缀（data exploration），例如 `de_target_distribution.echarts.json`。
3. 把关键发现（如强相关特征、异常值比例、季节性模式）写入 `data/raw/README.md` 的"数据理解"小节，供后续 Agent 快速参考。

**不要做**：

- 不要用复杂的特征工程替代基础探索。
- 不要把探索结论写进 `experiments/index.json`（那是实验事实层，只记录带分数的实验）。
- 不要为通用性生成过大的抽象脚本；Agent 根据具体数据类型写定制探索代码，比维护一个万能脚本更高效。

## 建立 v0 baseline

如果用户已有 baseline：

1. 放到 `baselines/<family>_b000_<slug>/`。
2. Agent 读取运行说明，确认依赖和输入输出路径。
3. 跑通一次，并确保 runner 能留下日志和可记录分数。

如果用户没有 baseline：

1. 读取题面和 `data/raw/README.md`。
2. 用 `{family}_b000_{slug}` 创建 baseline 版本目录，再把最简单的可运行版本写进去。
3. baseline 必须输出 `FINAL_SCORE: <value>`、`CV_SCORE: <value>` 或 `SCORE: <value>`。
4. 运行项目 runner 建立 v0；没有项目 runner 时使用 `scripts/experiment.py --mode run`。
5. 运行 `scripts/experiment.py --mode record` 写回初始分数。

baseline 版本名必须使用 `{family}_b{NNN}_{slug}`。初始化后运行：

```bash
python3 scripts/baseline_names.py --mode validate --workspace <workspace-root> --experiments experiments/index.json
```

## Auto Task 前置门

只有以下条件全部满足时，才能创建 Auto Task：

- 竞赛类型已确认。
- 真实数据或平台访问方式已就绪。
- baseline 可运行。
- v0 分数已写入 `experiments/index.json`。
- 用户确认循环模式、最大轮数、连续失败阈值和停止策略。

连续运行配置要谨慎。`max_continuations=-1` 只适合探索期，并且需要用户明确同意。

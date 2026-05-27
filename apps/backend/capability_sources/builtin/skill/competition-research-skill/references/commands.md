# 命令手册

所有脚本默认在工作区内运行，并通过 `AIASYS_WORKSPACE_ROOT` 限制路径范围。

## init

创建竞赛项目骨架：

```bash
python3 scripts/init.py --name <project-name> --metric <metric> --direction <minimize|maximize> --output_dir <dir>
```

参数：

| 参数 | 说明 |
|------|------|
| `--name` | 项目目录名 |
| `--metric` | 最终评估指标 |
| `--direction` | `minimize` 或 `maximize` |
| `--output_dir` | 项目输出父目录 |

## update-agents

用实验历史重新生成项目 `AGENTS.md`：

```bash
python3 scripts/update_agents.py --experiments <project>/experiments/index.json --output <project>/AGENTS.md
```

适用场景：

- 新 best_score 出现。
- 新增重要反模式。
- 优先队列有明显变化。
- 新 Agent 接手前需要压缩上下文。

## update-research-views

用实验索引生成研究视图：

```bash
python3 scripts/update_research_views.py --experiments <project>/experiments/index.json --output-dir <project>/research_views
```

输出：

- `current.html`：自动研究状态看板，每轮 record 后刷新。

## generate-echarts

用实验索引生成 ECharts 可视化图表配置：

```bash
python3 scripts/generate_echarts.py
```

环境变量 `AIASYS_WORKSPACE_ROOT` 指向工作区根目录。图表配置输出到 `research_views/echarts/`，用 `01_` 到 `08_` 编号前缀。

默认输出：

| 编号 | 文件 | 说明 |
|------|------|------|
| 01 | `01_timeline.echarts.json` | 全部实验得分演进，按模型家族着色 |
| 02 | `02_mainline.echarts.json` | 主线提升阶梯（keep 且得分递增的里程碑） |
| 03 | `03_family_compare.echarts.json` | 模型家族得分箱线图 |
| 04 | `04_phase_compare.echarts.json` | 阶段得分箱线图 |
| 05 | `05_phase_success.echarts.json` | 各阶段 keep/discard/crash 堆叠 + keep 率折线 |
| 06 | `06_anti_patterns.echarts.json` | 反模式分类分布 |
| 07 | `07_anti_sankey.echarts.json` | 反模式来源版本到分类的桑基流向 |
| 08 | `08_decisions.echarts.json` | 实验决策分布饼图 |
| 09 | `09_family_success.echarts.json` | 模型家族成功率（keep/discard/crash + keep 率） |
| 10 | `10_hypothesis_outcome.echarts.json` | 关键假设关键词频率（keep vs discard 对比） |
| — | `overview.html` | 统一看板，2x2 网格加载全部图表 |

浏览方式：用浏览器打开 `research_views/echarts/overview.html`（需联网加载 ECharts CDN）。

导出 PNG：

```bash
# 批量导出全部图表
python3 scripts/export_echarts_png.py --input research_views/echarts/ --output research_views/figures/

# 导出单个图表
python3 scripts/export_echarts_png.py --input research_views/echarts/01_timeline.echarts.json --output research_views/figures/timeline.png

# 自定义尺寸
python3 scripts/export_echarts_png.py --input research_views/echarts/ --output research_views/figures/ --width 1600 --height 800
```

依赖：`apps/web/node_modules` 中的 Playwright 和 Chromium。环境变量 `NODE_PATH` 会自动指向该目录。如需自定义 Chromium 路径，设置 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`。

导出的 PNG 可以直接在 Markdown 报告中引用，例如：

```markdown
![实验得分演进](research_views/figures/01_timeline.png)
```

自定义图表：修改工作区副本的 `scripts/generate_echarts.py`，新增图表用 `09_` 及以后编号。

适用场景：

- 批量回顾实验历史时快速把握得分趋势和主线演进。
- 对比模型家族或阶段的表现分布和成功率。
- 识别反模式密集区、来源流向和决策模式。
- 生成报告或截图时作为数据支撑。


## baseline_names

检查单个版本名：

```bash
python3 scripts/baseline_names.py --mode check --name <family>_b000_base
```

生成下一个版本名：

```bash
python3 scripts/baseline_names.py --mode next --family lgb --slug pairranker_on_trigrid
```

校验工作区当前版本事实：

```bash
python3 scripts/baseline_names.py --mode validate --workspace <workspace-root> --experiments experiments/index.json
```

适用场景：

- 启动新 runner 前确定本轮唯一 version。
- 整理历史 baseline 目录、实验索引、输出目录和日志名。
- 更新 AutoTask prompt 或项目 `AGENTS.md` 前做一次一致性检查。

## arxiv_search

基础搜索：

```bash
python3 scripts/arxiv_search.py --query <keywords> --max_results <N> --references_dir <dir> --output_dir <dir>
```

限定分类和日期：

```bash
python3 scripts/arxiv_search.py \
  --query "electricity+price+forecasting" \
  --categories "cs.LG,cs.AI,stat.ML" \
  --date_from 2023-01-01 \
  --max_results 20
```

建议：

- 用 `+` 连接核心关键词，减少 OR 搜索噪声。
- 文献调研阶段优先 relevance 排序。
- 追踪新进展时用 submittedDate 排序。
- 先 broad query，再基于结果 refine。

## ingest

摄入单篇论文：

```bash
python3 scripts/ingest.py --paper_dir <paper-dir> --experiments <project>/experiments/index.json
```

摄入搜索结果：

```bash
python3 scripts/ingest.py --results_json <results.json> --experiments <project>/experiments/index.json
```

效果：

- 更新 `references/index.json`。
- 写入 `knowledge_graph_db_path` 指向的 AIASys SQLite 图谱。
- 支持 `unread -> read -> extracted -> tried -> succeeded/failed` 生命周期。

## experiment status

```bash
python3 scripts/experiment.py --mode status --experiments <project>/experiments/index.json --workspace <workspace-root>
```

输出：

- 当前 best_score / best_version。
- keep / discard / crash 统计。
- 最近实验。
- bootstrap 状态。
- 知识图谱统计。
- HTML 看板 `research_views/current.html` 的路径和存在状态。
- 论文摄入数量。

## experiment plan

```bash
python3 scripts/experiment.py --mode plan --experiments <project>/experiments/index.json --workspace <workspace-root>
```

plan 会读取：

- `priority_queue`
- `current_phase`
- `anti_patterns`
- AIASys 图谱中的 method 实体

## experiment run

`experiment.py --mode run` 是内置模板 runner，适合简单 `.py` 或 `.ipynb` baseline。项目已有复跑脚本、平台 notebook、官方评测 CLI、仿真入口或 API 交互脚本时，优先使用项目 runner。

runner 选择顺序：

1. 读取 `experiments/index.json` 的 `runner` 字段。
2. 读取项目 `AGENTS.md`、`scripts/README.md` 和题面执行说明。
3. 确认 runner 能写日志、生成产物、给出可记录分数。
4. 运行后用 `experiment.py --mode record` 写回分数和结论。

从 baseline 运行：

```bash
python3 scripts/experiment.py --mode run --experiments <project>/experiments/index.json --workspace <workspace-root> \
  --version <family>_b000_base --name baseline --hypothesis "建立基准"
```

从上一轮 keep 版本继续：

```bash
python3 scripts/experiment.py --mode run --experiments <project>/experiments/index.json --workspace <workspace-root> \
  --from_version <best_version> --version <new_version> --name <name> --hypothesis "<hypothesis>"
```

说明：

- 自动检测 `.py` 和 `.ipynb`。
- 版本名必须使用 `{family}_b{NNN}_{slug}`。需要下一个编号时运行 `python3 scripts/baseline_names.py --mode next --family <family> --slug <slug>`。
- 不覆盖已有实验文件，便于 Agent 修改后重跑。
- stdout、stderr 写入 `outputs/logs/`。训练脚本应定期打印阶段进度，Python baseline 使用 `print(..., flush=True)` 或 `python -u`。
- 默认 30 分钟超时。
- 从输出中解析 `FINAL_SCORE:`、`CV_SCORE:`、`SCORE:`、`BEST_SCORE:` 或 `METRIC:`。
- 只在项目没有专用 runner 时作为默认执行入口。

## workspace_shell runner

项目已有 runner 时，按 `experiments/index.json` 的 `runner.command` 执行，例如：

```bash
./run_baseline.sh <version>
```

执行前检查：

- version 是否符合 `{family}_b{NNN}_{slug}`。
- `baselines/<version>/` 是否是本轮新建或明确要复核的版本。
- `outputs/logs/<version>.log` 是否已经存在，避免覆盖上一轮证据。
- `outputs/<version>/` 和 `outputs/submissions/<version>/` 是否已经有产物。
- runner 是否可能超过普通 Shell 超时或预计超过 2 分钟。如果会超过，使用 `SpawnMonitor` 启动，随后用 `ManageMonitor(action="poll")` 轮询，并记录 monitor ID。
- runner 日志是否会持续刷新。至少要输出数据加载、特征构建、候选训练、候选评分、产物写入和最终指标；日志长时间无新增内容时，先排查 stdout 缓冲或卡住阶段。

执行后检查：

- `outputs/logs/<version>.log` 有阶段进度、最终指标或明确错误。
- `outputs/<version>/run_summary.json`、`output_path` 或项目定义的结果文件存在。
- 分数按最终指标读取，不用 RMSE 或 loss 替代。
- 立即执行 `experiment record` 或同 schema 写回。

如果 Shell 返回超时，但日志和输出文件已经完整生成，按产物记录结果，并在 `outputs/observations/<date>-auto-research.md` 记录“执行通道超时，runner 实际完成”。如果日志为空且进程仍在运行，不要再启动第二个版本，先通过 Monitor、进程状态和日志 mtime 确认；确认是缓冲问题时，下一版 baseline 先补 `flush=True` 或 `python -u`。

## experiment record

```bash
python3 scripts/experiment.py --mode record --experiments <project>/experiments/index.json --workspace <workspace-root> \
  --version <version> --score <score> --decision <keep|discard|crash> --findings "<findings>"
```

常用可选参数：

| 参数 | 说明 |
|------|------|
| `--hypothesis` | 本轮假设 |
| `--description` | 具体修改 |
| `--method_tested` | 测试的方法名 |
| `--pipeline_layer` | `features`、`loss`、`model`、`post-processing`、`strategy` |
| `--inspired_by` | 论文 ID 列表 |

record 会自动更新 best_score、best_version、anti_patterns、阶段和清理策略。

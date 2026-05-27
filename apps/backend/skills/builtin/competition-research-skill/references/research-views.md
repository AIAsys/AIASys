# 研究视图分工

竞赛项目同时维护四层状态。它们可以互相引用，但不要互相替代。

| 层 | 文件或资源 | 作用 | 更新频率 |
|------|------------|------|----------|
| 实验事实 | `experiments/index.json` | 分数、版本、keep/discard、反模式、优先队列、runner | 每轮实验记录后 |
| 知识图谱 | `/global/resources/graphs/<id>.db` | 论文、方法、实验、指标、约束和关系查询 | 论文摄入或关系变化后 |
| 数据探索 | `research_views/data_exploration/` | 原始数据画像、目标变量分布、特征相关性、时间模式 | 项目初始化时，或数据变化后 |
| HTML 看板 | `research_views/current.html` | 自动研究状态、当前判断、下一步、风险和证据入口 | 每轮 record 后，或 AutoTask/runner 状态变化后 |
| ECharts 可视化 | `research_views/echarts/` | 实验得分演进、模型族对比、反模式分布、决策统计 | 每轮 record 后，或批量分析时 |

`current.html` 是自动研究看板。它回答“现在怎么样、下一步做什么、证据在哪里”。


## 更新顺序

1. 项目初始化时先做数据探索，结果写入 `research_views/data_exploration/`。
2. 先更新 `experiments/index.json`。
3. 有论文或方法关系变化时，更新 `references/index.json` 和知识图谱。
4. 每轮 record 后运行 `scripts/update_research_views.py`，刷新 `research_views/current.html`。
5. 需要可视化分析时运行 `scripts/generate_echarts.py`，生成 `research_views/echarts/` 下的图表配置。
6. 需要报告截图时运行 `scripts/export_echarts_png.py`，导出 PNG 到 `research_views/figures/`。
7. 必要时重新生成 `AGENTS.md`。

推荐命令：

```bash
AIASYS_WORKSPACE_ROOT="$PWD" python3 scripts/update_research_views.py --experiments experiments/index.json --output-dir research_views
AIASYS_WORKSPACE_ROOT="$PWD" python3 scripts/generate_echarts.py
AIASYS_WORKSPACE_ROOT="$PWD" python3 scripts/update_agents.py --experiments experiments/index.json --output AGENTS.md
```

## 什么时候更新知识图谱

知识图谱适合在这些场景更新：

- 论文摄入完成，新增了可迁移方法或约束。
- 实验产生了新的方法关系、失败原因或反模式。
- 论文、方法、实验、指标之间出现了新的可查询关系。
- 新版本改变了可信状态，例如 `trusted_best_version`、`highest_observed_version`、holdout 风险或复现状态。
- Agent 后续需要通过搜索或关系查询继续推理。

## 什么时候更新 HTML 看板

HTML 看板适合高频刷新：

- 每轮 `record` 后。
- AutoTask 从 active 变成 paused、blocked 或 completed。
- runner 从 running 变成 idle 或 blocked。
- `latest_version`、`next_candidate_version`、`trusted_best_version`、`highest_observed_version` 变化。
- 用户回来检查当前状态。

HTML 看板只放当前局面摘要，不放全量实验日志。它可以链接到 `experiments/index.json`、`AGENTS.md`、`references/index.json`、知识图谱和 ECharts 可视化目录。



## 不要混用的边界

- `experiments/index.json` 负责实验事实。
- 知识图谱负责长期可查询关系。
- HTML 看板负责当前状态阅读。
- `AGENTS.md` 负责 Agent 执行约束。
- README 负责目录说明，不承担执行规则。

## ECharts 图表设计原则

`scripts/generate_echarts.py` 从 `experiments/index.json` 自动生成数据驱动的可视化图表。默认输出存放在 `research_views/echarts/`，用 `01_` 到 `08_` 编号前缀保证浏览顺序。

默认图表清单：

**实验结果图表（`research_views/echarts/`）**

| 编号 | 文件名 | 用途 |
|------|--------|------|
| 01 | `01_timeline.echarts.json` | 全部实验得分演进，按模型家族着色，标注可信最优和历史最高观测 |
| 02 | `02_mainline.echarts.json` | 主线提升阶梯，只保留 keep 且得分递增的里程碑 |
| 03 | `03_family_compare.echarts.json` | 模型家族（lgb/blend/transformer 等）得分箱线图 |
| 04 | `04_phase_compare.echarts.json` | 阶段（feature/model/ensemble/literature）得分箱线图 |
| 05 | `05_phase_success.echarts.json` | 各阶段 keep/discard/crash 堆叠柱状图 + keep 率折线 |
| 06 | `06_anti_patterns.echarts.json` | 反模式按分类分布柱状图 |
| 07 | `07_anti_sankey.echarts.json` | 反模式来源版本到分类的桑基流向图 |
| 08 | `08_decisions.echarts.json` | 实验决策分布饼图 |
| 09 | `09_family_success.echarts.json` | 模型家族成功率（keep/discard/crash + keep 率） |
| 10 | `10_hypothesis_outcome.echarts.json` | 关键假设关键词频率（keep vs discard 对比） |

**数据探索图表（`research_views/data_exploration/`）**

数据探索图表在 bootstrap 阶段生成，用于记录原始数据画像。它们不参与实验循环，但为建模方向提供依据。命名统一用 `de_` 前缀。

| 前缀 | 示例文件名 | 用途 |
|------|-----------|------|
| `de_target_` | `de_target_distribution.echarts.json` | 目标变量分布（直方图、箱线图） |
| `de_corr_` | `de_corr_heatmap.echarts.json` | 特征与目标相关性排序或热力图 |
| `de_temporal_` | `de_temporal_pattern.echarts.json` | 时间序列模式（日内、周内、季节性） |
| `de_feature_` | `de_feature_missing.echarts.json` | 缺失值比例或特征统计 |

配色约定：

- keep = `#22c55e`（绿），discard = `#9ca3af`（灰），crash = `#ef4444`（红）
- 可信最优 = `#22c55e`，历史最高观测 = `#f59e0b`（橙），主线 = `#175cd3`（蓝）

自定义图表：

- 项目有独特分析需求时，直接修改工作区副本的 `scripts/generate_echarts.py`。
- 新增图表用 `09_` 及以后编号，避免与默认图表冲突。
- 图表只做数据呈现，不把假设、结论或下一步建议写进图表标题；这些留在 `current.html` 和 `AGENTS.md` 中。

### 防重叠规范

ECharts 在固定尺寸下容易出现标签、图例和标题重叠。生成图表时遵循以下规则：

**1. 图例不压标题**
- legend 默认放底部（`bottom: 0`），不放顶部。若必须放顶部，增大 `grid.top` 到 `"20%"` 以上。
- 对于单系列折线图，直接去掉 legend，避免与标题和副标题争抢空间。

**2. X 轴标签不过密**
- 标签数超过 20 个时，设置 `"interval": "auto"` 让 ECharts 自动隐藏部分标签。
- 标签数超过 40 个时，必须同时旋转（`rotate: 55`）并增大 `grid.bottom` 到 `"22%"` 以上。
- 导出 PNG 时，时间线图（01_timeline）等密集标签图应使用 2400px 以上宽度。

**3. 双 Y 轴避免拥挤**
- 尽量不用双 Y 轴。若必须展示两种量纲，改用左右两个独立子图（matplotlib 优先）。
- 双 Y 轴图需增大 `grid.right` 到 `"10%"` 以上，避免右侧刻度标签与折线数据标签重叠。

**4. 最后一个数据点标签不被截断**
- step 折线图的最后一个点在 ECharts 中默认不渲染 label。使用 `markPoint` + `symbol: "none"` 强制显示最后一个值。
- 或改用固定像素边距（`grid: {left: 80, right: 120}`）并关闭 `containLabel`，保证右侧留出固定空白。
- 副标题过长也会被截断，应缩短副标题，或增大 `grid.top`。

**5. 桑基图右侧标签可见**
- sankey 系列必须设置 `left`、`right`、`top`、`bottom` 布局参数，右侧留白不低于 `"22%"`。
- label 设置 `position: "right"` 和 `color: "#333"`，确保目标节点文字清晰。

**6. 数据类别归一化**
- 反模式、阶段等分类字段在入库前统一命名规范（如 `post-processing` → `post_processing`），避免同一分类在图表中出现两次。

**7. 标签颜色可读**
- 折线/柱状图的数据标签统一使用深色（`color: "#333"`），禁止使用默认浅色（在浅色背景上不可见）。
- 堆叠图上的百分比标签建议加粗（`fontWeight: "bold"`）。

**8. 导出尺寸按需调整**
- 默认导出 1200×600。
- 密集时间线：2400×900。
- 主线阶梯：1400×700 或 1600×700。
- 桑基图：1400×700。

浏览方式：

- 直接打开 `research_views/echarts/overview.html`（需要联网加载 ECharts CDN）。
- 或在支持 ECharts JSON 的工具中逐个加载 `.echarts.json` 文件。
- 需要静态截图时，运行 `scripts/export_echarts_png.py` 批量导出 PNG 到 `research_views/figures/`，再引用到 Markdown 报告中。

## 执行报告

当用户需要阶段性总结、交付成果或暂停研究时，生成 Markdown 执行报告。

### 存放位置和命名

- 目录：`reports/`（项目根目录下，与 `experiments/`、`research_views/` 平级）
- 命名：`report_YYYYMMDD_{phase}.md`，例如 `report_2026-05-14_ensemble.md`
- 引用的 PNG 截图放在 `research_views/figures/`，报告中用相对路径引用

### 触发时机

以下场景适合生成报告：

- 用户主动要求"生成报告"、"写总结"或"交付阶段性成果"。
- 阶段转换时（如从 model 进入 ensemble）。
- AutoTask 暂停、blocked 或完成时。
- 达到里程碑（如达到目标分数、排名或实验轮数）。
- 论文写作需要图表和数据支撑时。

### 生成步骤

```bash
# 1. 确认 experiments/index.json 已更新到最新状态
# 2. 生成 ECharts 图表
AIASYS_WORKSPACE_ROOT="$PWD" python3 scripts/generate_echarts.py

# 3. 导出 PNG 截图
AIASYS_WORKSPACE_ROOT="$PWD" python3 scripts/export_echarts_png.py \
  --input research_views/echarts/ --output research_views/figures/

# 4. 生成 Markdown 报告（Agent 根据模板和数据撰写）
# 报告存放到 reports/report_YYYYMMDD_{phase}.md
```

### 报告内容模板

报告至少包含以下章节：

1. **项目概况**：竞赛名称、指标、优化方向、可信最优版本和分数。
2. **实验成果总览**：总实验数、keep/discard/crash 统计、反模式数量。
3. **主线提升阶梯**：从 base 到可信最优的里程碑表格，附 `02_mainline.png`。
4. **实验得分演进**：附 `01_timeline.png`，说明得分分布和家族表现。
5. **阶段/家族成功率**：附 `05_phase_success.png` 和 `09_family_success.png`。
6. **反模式与教训**：列出关键反模式分类，附 `06_anti_patterns.png` 和 `07_anti_sankey.png`。
7. **当前状态与下一步**：可信最优是否稳定、历史最高未接管原因、下一步候选方向。
8. **生成记录**：列出数据文件、看板、图表和知识图谱的路径。

### 引用图表示例

```markdown
![实验得分演进](../research_views/figures/01_timeline.png)
```

## 默认路径

- `research_dashboard_path` 默认是 `research_views/current.html`。
- ECharts 图表默认输出到 `research_views/echarts/`。
- PNG 截图默认输出到 `research_views/figures/`。
- 执行报告默认输出到 `reports/`。
- `knowledge_graph_id` 和 `knowledge_graph_db_path` 是图谱层的主入口。

# 电力竞赛材料样例

参考目录：

```text
archive/08-misc-and-experiments/electricity-competition
```

这个文件是可选样例，不是通用流程规则。它用于说明一个真实竞赛材料目录可以怎样组织，以及哪些字段值得被抽象进 `experiments/index.json`、`references/index.json` 和项目 `AGENTS.md`。

不要把这里的电力赛题方法、分数、模型路线写死到 competition-research-skill。内置 skill 要保持通用。

## 样例目录价值

| 路径 | 可借鉴点 |
|------|----------|
| `AGENTS.md` | 新 Agent 入职文档和执行入口，压缩当前记录、反模式、下一步和自动研究配置 |
| `statement/description.md` | 题面、约束、评估公式 |
| `data/README.md` | 数据目录职责和读写边界 |
| `data/raw/README.md` | 原始数据说明 |
| `data/raw/official_data/` | 官方原始数据和提交示例 |
| `experiments/index.json` | 机器可读实验记忆 |
| `references/README.md` | 论文物理目录按稳定主题分组 |
| `references/index.json` | 论文注册、主题、行动建议和知识图谱状态 |
| `baseline_history/迭代日志.md` | 历史 baseline 迭代记录 |
| `baseline_history/结果对照总表.md` | 版本、代理指标和最终指标对照 |
| `baselines/` | 版本化 baseline 代码 |
| `.env/README.md` | 工作区 UV 环境说明 |
| `scripts/README.md` | 脚本来源和使用边界 |
| `run_baseline.sh` | 电力项目本地 baseline runner，负责复跑和整理输出 |
| `outputs/` | 每轮输出、提交文件和运行摘要 |
| `research_views/current.html` | 自动研究状态看板（视图层） |
| `research_views/echarts/` | ECharts 可视化图表（视图层） |

HTML 看板只放当前自动研究状态，不承担全量事实。ECharts 可视化放实验得分演进、模型族对比、反模式分布和决策统计，由 `scripts/generate_echarts.py` 自动生成。知识图谱负责可查询关系，`experiments/index.json` 负责实验事实。

## 样例中可抽象的结构

### 1. 评估指标要明确

样例材料里同时记录了代理指标和最终指标。这对通用 skill 的启发是：项目必须明确最终评估指标，并在实验记录中区分代理指标与最终指标。

通用规则只保留这一层：最终 keep/discard 以竞赛最终指标为准。

如果历史最高分版本的稳定性不可信，要把它写进 `highest_observed_*`，把推荐提交和继续派生主线写进 `trusted_best_*`。这能避免 Agent 只按最高分盲目接管主线。

### 1.1. runner 只抽象执行入口

样例里的 `run_baseline.sh` 是电力项目自己的 baseline runner。它负责使用工作区环境复跑指定版本、保存日志、整理 `output.csv`。通用 skill 只抽象 runner 机制，不继承这个脚本名。

通用规则是：每个竞赛项目都要登记自己的 runner，并把运行证据交给 `experiment.py --mode record` 或同 schema 记录器写回。

### 2. 反模式要结构化

样例材料把失败路线写成了可复用记忆，例如：

- 代理指标改善但最终指标下降。
- 某类特征继续堆叠后分数下降。
- 某类后处理自由度过高，效果不如简单版本。
- 某类外部数据直接接入后没有收益。

通用规则是：每轮 discard 都要尽量写入 `anti_patterns`，包含 pattern、consequence、source_version 和 category。

### 3. 优先队列要可执行

样例材料里的下一步方向有明确排序和理由。通用 skill 应要求 `priority_queue` 写成结构化列表，而不是只写一句“继续优化”。

每条优先项至少包含：

- `priority`
- `direction`
- `rationale`
- `phase`

### 4. AGENTS.md 应来自真实索引

样例项目的 `AGENTS.md` 有价值，是因为它来自题面、实验历史、反模式和下一步方向。通用 skill 的生成脚本应该把这些结构化字段转成短文档，方便新 Agent 接手。

通用 `AGENTS.md` 不应包含某个赛题的固定方法结论，只应压缩当前项目自己的事实。

## 使用方式

当需要整理已有竞赛材料时，可以按这个样例检查：

1. 是否有题面入口。
2. 是否有机器可读实验索引。
3. 是否有论文或方法索引。
4. 是否有结果对照表。
5. 是否有新 Agent 入职文档。
6. 是否能从历史实验中提取反模式。
7. 是否能形成下一步优先队列。

如果某一项缺失，优先补结构化索引，再补叙述性文档。

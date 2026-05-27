+++
name = "竞赛研究"
description = "竞赛场景的单分支研究与实验闭环入口：项目初始化、AGENTS.md 维护、文献检索、论文摄入、单环境串行实验循环，以及知识图谱、HTML 看板与 ECharts 可视化分层管理。\n适用于用户提供竞赛题目、数据或历史实验材料，希望 Agent 在已准备或已绑定的运行环境中建立 baseline 并持续优化一条实验线的场景。"
+++


# 竞赛研究 Skill

这个 skill 是 AIASys 竞赛项目的单分支研究入口。它不直接替代文件工具、Auto Task、论文下载、PDF 转换和运行环境管理，而是把这些能力组织成一套可复用的串行竞赛工作流。

本 skill 默认使用已经准备好或已经绑定到当前工作区/分支的运行环境。它只做轻量环境预检，不在正式实验轮里安装大依赖、切换 GPU 框架或创建多条并行实验线。

相关 skill 分工：

| 目标 | 使用 |
|------|------|
| 准备 UV 环境、安装依赖、GPU 检查、小样本 smoke | `competition-runtime-prep-skill` |
| 单分支、单环境、串行实验闭环 | `competition-research-skill` |
| 多分支、多环境、多 AutoTask lane 编排和汇总 | `competition-parallel-research-skill` |

## 先判断任务类型

进入本 skill 后，先判断用户现在要做哪件事：

| 用户目标 | 先读 |
|----------|------|
| 从零创建一个竞赛项目 | `references/bootstrap.md` |
| 整理已有竞赛项目或历史实验 | `references/schema.md`，再按需参考 `examples/electricity-competition-materials.md` |
| 梳理知识图谱、HTML 看板与 ECharts 可视化分工 | `references/research-views.md`，再按需参考 `references/schema.md` |
| 启动或维护自动实验循环 | `references/auto-loop.md` |
| 设计或检查实验执行入口 | `references/auto-loop.md`，再按需参考 `references/commands.md` 和 `references/schema.md` |
| 准备或修复竞赛运行环境 | 转交 `competition-runtime-prep-skill` |
| 多环境、多分支并行探索 | 转交 `competition-parallel-research-skill` |
| 设计 baseline 命名或整理版本目录 | `references/baseline-naming.md`，再运行 `scripts/baseline_names.py --mode validate` |
| 查脚本参数和命令 | `references/commands.md` |
| 摄入论文、维护知识图谱、衔接其他 skill | `references/integration.md` |

如果用户只是问当前竞赛项目状态，先运行 `scripts/experiment.py --mode status`，再决定是否需要继续读更多参考文档。

## 最小工作流

1. 确认竞赛类型、最终指标、优化方向、数据来源、提交格式和时间预算。
2. 检查 `data/raw/` 是否有真实数据，`baselines/` 是否有可运行代码。
3. 对真实数据做系统性探索：目标分布、特征相关性、缺失值、时间模式。结果写成报告并落盘到 `research_views/data_exploration/`。
4. 确认项目 runner。`experiment.py --mode run` 是内置模板 runner；已有 `run_baseline.sh`、平台 notebook、评测脚本或 API 交互入口时，优先登记项目 runner。
5. 运行或建立 v0 baseline，确保 runner 能留下日志、输出产物和可记录分数。
6. 用 `{family}_b{NNN}_{slug}` 命名 baseline 版本，并让 `baselines/<version>/`、`outputs/<version>/`、`outputs/logs/<version>.log` 和 `experiments[].version` 保持一致。
7. 用 `experiments/index.json` 维护 best_score、实验历史、反模式、下一步优先队列和 runner 配置。
8. 用 `references/index.json` 维护论文和可迁移方法。
9. 用 `knowledge_graph_id` 和 `/global/resources/graphs/<id>.db` 维护 AIASys 知识图谱。
10. 用 `research_views/current.html` 维护当前自动研究看板；用 `scripts/generate_echarts.py` 生成 ECharts 可视化图表；用 `scripts/export_echarts_png.py` 导出 PNG 用于报告。
11. 用 `scripts/update_agents.py` 生成项目内 `AGENTS.md`，让新 Agent 能快速接手。
12. 只有在前置条件全部满足、且用户确认退出条件后，才创建 continuous Auto Task。建议先创建为 `paused`，确认任务内容、runner 和重叠策略后，再显式恢复或手动运行一轮。

## 硬性规则

- 严禁拟造训练数据。缺数据时暂停，请用户提供真实数据或平台访问方式。
- 最终 keep/discard 以竞赛最终指标为准。RMSE、MAE、loss、训练集分数只能辅助诊断。
- 每轮实验必须有明确假设、版本、运行日志、分数和结论。
- 长耗时 runner 必须可观测。预计超过 2 分钟的训练或搜索任务，baseline 代码要按阶段打印进度心跳，并用 `flush=True`、`python -u` 或等效方式避免缓冲；AutoTask 中优先用 `SpawnMonitor` 启动 runner，再用 `ManageMonitor(action="poll")` 轮询输出和退出码。
- baseline 版本名必须使用 `{family}_b{NNN}_{slug}`。同一 family 内编号递增，旧名不做兼容，不保留别名。
- 已证伪方向必须写入 `anti_patterns`，后续实验先读它，避免重复消耗。
- `research_views/current.html` 是自动研究状态看板，不是事实源。每轮 record 后或 AutoTask/runner 状态变化后刷新，方便人和 Agent 快速判断当前局面。
- 0-1 阶段直接改正结构。整理旧项目时，发现目录、脚本入口或自动研究流程不合适，就按当前事实替换，不保留旧名、旧路径或兼容双轨。
- `baselines/` 中用户提供的起点代码默认只读。新实验复制到 `experiments/` 或版本化目录再改。
- 自动研究只统一生命周期：`plan -> run -> evaluate -> record -> update_kg -> update_dashboard -> update_echarts`。`run` 必须按竞赛类型绑定 runner，不能把某个项目脚本当作通用入口。
- 自动研究默认只使用当前已绑定运行环境。启动 runner 前允许做导入检查、包版本检查、GPU 可见性检查和 runner preflight；缺大依赖或环境不一致时写入 `outputs/observations/<date>-auto-research.md` 并暂停，不在本轮实验里安装大包。
- `torch`、`xgboost`、`catboost`、CUDA 相关包、深度学习框架和超过普通依赖体量的包，默认由 `competition-runtime-prep-skill` 准备和验证。
- 自动研究每轮只能启动一个新实验版本。发现已有运行进程、同名输出、未记录结果或并行分支时，先整理记录或暂停，不要继续开新版本。
- 监听和日志要配合使用。`outputs/logs/<version>.log` 是长期证据，Monitor 是运行期状态通道；定时器只能决定多久检查一次，不能替代 runner 自身的进度输出。
- 多分支并行探索不属于本 skill 的默认职责。需要并行时，转交 `competition-parallel-research-skill` 先规划 lane、env_id、session、AutoTask 和写回锁。
- Auto Task 不由脚本私自创建。Agent 需要先和用户确认循环模式、退出条件和是否允许长期运行。创建自动研究任务时，默认先暂停保存；开始执行要用明确的 resume 或 run-now 操作。
- 暂停 Auto Task 不等于停止已启动 runner。需要停止实验时，必须明确停止对应会话、后台任务或 Shell 进程。
- 知识图谱是 AIASys 全局资源。新项目优先使用 `knowledge_graph_id` 和 `knowledge_graph_db_path`，旧 `.graph.db` 字段只作历史兼容。
- 扫描版 PDF 只有在工作区已有 OCR 配置或用户明确提供配置时走 OCR；否则回退到普通 PDF 转 Markdown。

## 命令入口

初始化项目：

```bash
python3 scripts/init.py --name <project-name> --metric <metric> --direction <minimize|maximize> --output_dir <dir>
```

查看状态：

```bash
python3 scripts/experiment.py --mode status --experiments <project>/experiments/index.json --workspace <workspace-root>
```

生成实验建议：

```bash
python3 scripts/experiment.py --mode plan --experiments <project>/experiments/index.json --workspace <workspace-root>
```

运行实验：

```bash
python3 scripts/experiment.py --mode run --experiments <project>/experiments/index.json --workspace <workspace-root> \
  --from_version <best_version> --version <new_version> --name <name> --hypothesis "<hypothesis>"
```

记录结果：

```bash
python3 scripts/experiment.py --mode record --experiments <project>/experiments/index.json --workspace <workspace-root> \
  --version <version> --score <score> --decision keep --findings "<findings>"
```

更新研究视图：

```bash
python3 scripts/update_research_views.py --experiments <project>/experiments/index.json --output-dir <project>/research_views
```

更新项目 AGENTS：

```bash
python3 scripts/update_agents.py --experiments <project>/experiments/index.json --output <project>/AGENTS.md
```

## 当前改进重点

已有竞赛材料样例提示，竞赛 skill 的关键价值不只在“生成一个目录”，还在持续维护可压缩的项目记忆：

- 题面和最终指标要写成新 Agent 能马上执行的 `AGENTS.md`。
- 结果对照表、反模式、优先队列和论文行动建议要进入结构化索引。
- 每次实验要留下可复盘证据，尤其是最终指标和代理指标冲突时的结论。
- 自动循环只负责推动下一轮，不能覆盖用户确认、真实数据和退出条件。
- 研究视图和知识图谱要分层维护：图谱保留可检索关系，HTML 保留当前自动研究状态，ECharts 保留数据驱动的可视化分析。图表配色和标记遵循统一约定，方便跨项目对比。

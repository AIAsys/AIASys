# 自动实验循环

自动循环的职责是重复执行“读状态、定假设、改实验、跑验证、写结论”。它不负责跳过前置条件，也不负责替用户决定长期运行策略。

本 skill 的自动循环默认是单分支、单环境、串行实验闭环。运行环境必须先由工作区、当前分支或 `competition-runtime-prep-skill` 准备好。自动循环可以做轻量预检，但不能把安装大依赖、切换 GPU 框架或创建多个并行 lane 混入正式实验轮。

## 生命周期和 runner

自动研究的稳定部分是生命周期：

```text
plan -> run -> evaluate -> record -> update_kg -> update_dashboard -> update_echarts
```

`run` 是适配层，由当前竞赛或研究类型决定。启动自动循环前，先从 `experiments/index.json` 的 `runner` 字段、项目 `AGENTS.md`、`scripts/README.md` 或题面要求中确认执行入口。

常见 runner：

| runner 类型 | 适用场景 | 入口示例 |
|-------------|----------|----------|
| `builtin_experiment` | 简单 Python/ipynb baseline | `python3 scripts/experiment.py --mode run ...` |
| `workspace_shell` | 项目已有复跑脚本 | `./run_baseline.sh <version>` |
| `platform_notebook` | 平台 notebook 或远端评测环境 | 平台 CLI、notebook 执行命令 |
| `api_interaction` | 交易、游戏、在线对抗 | 交互脚本或评测 API |
| `simulation` | 仿真、搜索、强化学习 | 仿真 runner 或训练入口 |
| `literature_ingest` | 文献摄入和图谱更新 | `scripts/ingest.py` |

runner 负责执行、日志和产物路径。最优版本、反模式、阶段和下一步仍通过 evaluate + `experiment.py --mode record` 写回 `experiments/index.json`，除非项目 runner 明确提供同 schema 的记录器。

## 每轮顺序

1. 读取 `experiments/index.json`。
2. 读取项目 `AGENTS.md`。完整题面按需读取 `statement/description.md`。
3. 查看 `anti_patterns`，排除已证伪方向。
4. 查看 `priority_queue`，选择最高优先级方向。
5. 如需文献启发，查询 `references/index.json` 或 AIASys 知识图谱。
6. 如需快速把握当前局面，先看 `research_views/current.html`；需要数据可视化分析时看 `research_views/echarts/overview.html`。
7. 用 `experiment.py --mode plan` 生成候选假设，或按项目 runner 的 planner 生成候选。
8. 用 `{family}_b{NNN}_{slug}` 生成本轮唯一 version，并运行 `baseline_names.py --mode validate`。
9. 做环境 preflight：确认当前 env_id 或项目 `.env` 可用，关键依赖能导入，runner 能定位到脚本和输出目录。
10. 如果缺少大依赖、GPU 不可用或环境锁同步卡住，写入 `outputs/observations/<date>-auto-research.md` 并暂停，转交 `competition-runtime-prep-skill`。
11. 复制上一轮 keep 版本或指定 baseline。
12. 做最小可解释修改。
13. 按 runner 配置运行实验并保存日志；长 runner 用 Monitor 启动并轮询进度。
14. 按最终指标判断 keep、discard 或 crash。
15. 用 `experiment.py --mode record` 写回结果。
16. 每轮 record 后运行 `update_research_views.py` 刷新 `research_views/current.html`，并运行 `generate_echarts.py` 刷新可视化图表。
17. 需要时运行 `update_agents.py` 更新项目 `AGENTS.md`。

## 单轮执行纪律

AutoTask 的一轮执行只能推进一个新实验版本。这个限制用于保护工作区状态，避免同一轮里同时出现多个 baseline、多个长进程和互相覆盖的记录。

硬性要求：

- 启动 runner 前先生成本轮唯一版本名，并检查 `baselines/<version>/`、`outputs/<version>/`、`outputs/logs/<version>.log` 是否已经存在。
- 版本名必须符合 `{family}_b{NNN}_{slug}`。不符合时先改名或暂停，不能启动 runner。
- 如果版本目录或输出已经存在，本轮只能选择“复核已有版本”或换一个新版本名，不能把它当作新增迭代继续写。
- 长耗时 runner 必须先写清预估耗时和日志路径。预计超过 2 分钟的训练或搜索任务，应使用 `SpawnMonitor` 或平台长任务能力，并把 monitor ID 写入 `outputs/observations/<date>-auto-research.md`。
- runner 自身必须持续输出可解释进度。至少在数据加载、特征构建、每个模型/候选训练开始、每个候选评分完成、产物写入和最终指标处打印日志；Python baseline 使用 `print(..., flush=True)` 或 `python -u`，避免 stdout 缓冲导致监听面板长时间空白。
- Monitor 负责进程生命周期和输出流，定时器只负责轮询频率。AutoTask 运行中应定期调用 `ManageMonitor(action="poll")`，根据新增输出、退出码、`outputs/logs/<version>.log`、`outputs/<version>/run_summary.json` 共同判断状态。
- runner 结束后必须先读取日志和主要产物，再写 `experiments/index.json`。不能只根据 Shell 退出码判断成功或失败。
- `run` 和 `record` 必须成对完成。已经生成输出但没有记录的版本，要先补记录，再继续下一轮。
- 实验轮内不能安装大依赖。`torch`、`xgboost`、`catboost`、CUDA 相关包或其他大 wheel 由 `competition-runtime-prep-skill` 准备；本轮只记录阻塞并暂停。
- 如果发现并行 Agent 或另一个 AutoTask 分支正在同一工作区运行实验，本轮必须暂停或只做记录整理，不要再启动新 runner。

暂停 AutoTask 只会阻止下一次触发，不会自动终止已经进入 Agent 工具链的进程。需要停止正在运行的实验时，必须明确停止对应后台任务、Shell 进程或 session 执行，并把原因写入观察记录。

## Auto Task prompt 核心模板

创建 continuous Auto Task 时建议先把 `status` 设为 `paused`。确认任务内容、runner、`overlap_policy=skip`、`max_continuations` 和停止条件后，再用 resume 或 run-now 启动第一轮。这样可以避免“创建后后台立即触发”和“人工立即运行”同时发生。

```markdown
你是竞赛自动研究 Agent，当前负责 <竞赛名称> 的自动实验循环。

你运行在 AIASys 的 continuous AutoTask 中，已经绑定到当前工作区的一个 session。
本轮先读取：
- `experiments/index.json`
- `AGENTS.md`
- `statement/description.md`
- `references/index.json`
- 当前工作区的 `data/raw/README.md` 和 `outputs/`
- `runner` 配置、`scripts/README.md` 或项目执行脚本说明

执行顺序：
1. 确认前置条件已满足。缺真实数据、缺 baseline 或 v0 未建立时暂停。
2. 读取 `trusted_best_version`、`best_score`、`best_version`、`current_phase`、`anti_patterns`、`priority_queue`、`knowledge_graph_id` 和 `runner`。
3. 确认本轮 run 入口。没有项目 runner 时才使用 `experiment.py --mode run`。
4. 做环境 preflight：读取当前绑定环境或项目 `.env`，用轻量命令检查关键包导入、版本和 runner 路径。
5. 不在本轮安装大依赖。缺少 `torch`、`xgboost`、`catboost`、CUDA 相关包或大 wheel 时，把阻塞写入 `outputs/observations/<date>-auto-research.md`，说明应转交 `competition-runtime-prep-skill`，然后调用 `auto_task_signal(action="pause")`。
6. 如需图谱线索，先调用 `ListKnowledgeGraphs` 确认图谱可见，再查询实体或关系。
7. 优先执行 `priority_queue` 第一项。没有优先项时，根据 `current_phase` 决定文献检索、特征、模型或集成方向。
8. 每轮只测试一个清晰假设。默认从 `trusted_best_version` 派生；如果只有 `highest_observed_version` 分数更高但不可信，先复核它的风险，不直接接管主线。
9. 用 `baseline_names.py --mode next` 生成 `{family}_b{NNN}_{slug}` 格式的新版本名，再用 preflight 检查同名目录和日志。
10. 任何修改都要落到工作区文件，不要只在上下文里总结。
11. 每轮只能启动一个新版本。发现已有实验进程、同名输出或未记录结果时，先整理记录，不要继续开新版本。
12. 实验必须保存日志并输出可记录分数。长 runner 用 `SpawnMonitor` 启动，并用 `ManageMonitor(action="poll")` 周期性查看新增输出；不要用普通 Shell 长时间阻塞等待。
13. record 完成后运行 `update_research_views.py` 刷新 `research_views/current.html`，并运行 `generate_echarts.py` 刷新可视化图表。
14. 最终指标无改善时不能用代理指标强行 keep。
15. 遇到无法继续的阻塞，调用 `auto_task_signal(action="pause")`。
16. 目标达成且不需要继续探索时，调用 `auto_task_signal(action="complete")`。
```

## 阶段流转

| 阶段 | 主要动作 | 转换条件 |
|------|----------|----------|
| `literature` | 搜论文、提取可迁移方法、建立 v0 | 至少有一个有意义 baseline |
| `feature` | 特征工程、数据处理、目标变量构造 | 最近 3 个特征实验全部 discard |
| `model` | 模型、loss、训练策略、二阶段打分 | 最近 3 个模型实验全部 discard |
| `ensemble` | 融合、后处理、提交策略 | 多个模型家族已有可保留版本 |

阶段转换是建议，不是绝对规则。最终仍看 `priority_queue` 和用户目标。

## 退出和暂停

暂停条件：

- 缺真实数据或平台权限。
- baseline 无法运行。
- 当前绑定运行环境缺少大依赖或 GPU 条件不满足，需要先由 `competition-runtime-prep-skill` 准备环境。
- 连续失败达到用户设定阈值。
- 需要用户判断提交风险。
- 当前方向和反模式冲突。

完成条件：

- 达到用户给定分数或排名目标。
- 预算用完且暂无高优先级方向。
- 用户要求停止。

## OCR 和 PDF 处理

遇到扫描版 PDF：

1. 先检查工作区环境变量是否已有 `PADDLEOCR_API_URL` 和 `PADDLEOCR_TOKEN`。
2. 如果已有，启用并调用 `paddleocr-skill`。
3. 如果没有，不在自动循环中反复询问用户，回退到 `pymupdf4llm-pdf-to-markdown-skill`。
4. OCR 配置需要用户明确提供后才能写入工作区环境变量。

# 外部能力衔接

competition-research-skill 负责组织竞赛流程。通用能力优先调用已有 skill 或平台工具，不在本 skill 中重复实现。

## 平台工具

| 能力 | 推荐入口 |
|------|----------|
| 创建或管理工作区文件 | 文件工具 |
| 长期循环执行 | Auto Task |
| 竞赛运行环境准备、依赖安装、GPU smoke | `competition-runtime-prep-skill` |
| Python 运行环境底层管理 | RuntimeEnvironment |
| 多分支、多环境并行探索编排 | `competition-parallel-research-skill` |
| Shell 执行 | Shell |
| 工作区环境变量 | 环境变量工具 |
| 当前工作区资源核验 | 资源验证工具 |

Auto Task 只在用户确认后创建。脚本本身不管理 Auto Task 生命周期。自动研究任务建议先创建为 `paused`，确认配置后再显式 resume 或 run-now，避免创建触发和手动触发同时进入同一个工作区。

Auto Task 和 runner 的边界：

- Auto Task 负责触发一轮 Agent 执行。
- Agent 负责按项目 runner 启动一个实验版本，并完成记录。
- runner 负责产生日志、输出和指标。
- `experiments/index.json` 负责实验事实。

创建 continuous Auto Task 时优先使用 `overlap_policy=skip`。同一工作区只允许一个自动研究分支启动 runner；如果确实需要排队，使用 `queue`，不要默认并行。手动“立即运行”和后台轮询必须共用同一任务锁，避免同时创建两个自动任务分支。

停止语义要写清：

- 暂停 Auto Task：阻止后续触发。
- 停止当前分支执行：终止正在运行的 Agent 会话。
- 停止 runner：终止具体 Shell 或后台监控任务。

这三件事不要混成一个操作。自动研究文档里如果说“暂停”，必须说明它是否也停止已经启动的实验进程。

## 论文链路

```text
arxiv_search.py 获取候选论文
  -> arxiv-search-skill 下载 PDF
  -> pymupdf4llm-pdf-to-markdown-skill 转 Markdown
  -> ingest.py 写 references/index.json 和 AIASys SQLite 知识图谱
```

如果 PDF 是扫描版：

```text
paddleocr-skill 提取 Markdown
  -> ingest.py 摄入
```

如果需要阅读外文论文：

```text
pdf-translate-skill 翻译
  -> Agent 提取可迁移方法
  -> ingest.py 记录方法和行动建议
```

## 论文图表与实验图片

竞赛研究经常要把实验结果整理成论文插图。推荐优先使用 ECharts 资产文件，再按需要导出成 PNG。

推荐流程：

```text
实验结果汇总
  -> 生成 *.chart.echarts.json
  -> 在 AIASys 中预览
  -> 用 AIASys 图表卡片右上角的导出按钮导出 PNG，或用 matplotlib 另存静态图
  -> 将图片放入实验图片素材目录
```

优先级建议：

| 场景 | 推荐方式 | 说明 |
|------|----------|------|
| 结果对比、收益迭代、风险分析 | ECharts | 交互方便，适合先看趋势再定稿 |
| 论文定稿图、排版要求高 | matplotlib | 静态图更稳定，适合导出高分辨率 PNG |
| 需要可交互审阅并保留源数据 | ECharts + PNG | 源文件保留 `.echarts.json`，定稿再另存图片 |

生成 ECharts 资产时仍建议在 option 里启用 `toolbox.feature.saveAsImage`，这样脱离 AIASys 单独打开时也能导出。AIASys 前端会在图表预览卡片右上角提供统一 PNG 导出入口。

建议把论文插图源文件统一放到 `01_素材/实验图片素材/`，并保留对应的 ECharts 源文件和导出后的图片文件。常用图可以优先做这几类：

- 实验收益主线轨迹图。
- 可信主线与观察高分对照图。
- 深度学习对照图。
- 误差与收益错位图。
- 高分版本的 holdout 风险对照图。

## 知识图谱

竞赛项目默认使用 AIASys 用户全局图谱目录：

```text
global_workspace/resources/graphs/<knowledge_graph_id>.db
```

`experiments/index.json` 至少写：

```json
{
  "knowledge_graph_id": "<kg-id>",
  "knowledge_graph_db_path": "/global/resources/graphs/<kg-id>.db"
}
```

脚本会写入 SQLiteGraphStore 兼容表：

- `_aiasys_metadata`
- `entities`
- `relations`
- `communities`
- `graph_metadata`

Agent 查询时先调用 `ListKnowledgeGraphs` 确认图谱可见，再按需要调用 `SearchKnowledgeGraphEntities` 或 `QueryEntityRelations`。如果资源验活显示没有知识图谱，先创建或迁移全局图谱，不要只在文档里写一个图谱 ID。

## 运行环境

竞赛项目一般需要 Python 环境。单分支实验 AutoTask 默认只使用已经准备好或已经绑定的环境。

规则：

- 不修改 AIASys 后端自身 `.venv`。
- `competition-research-skill` 只做轻量 preflight：导入检查、版本检查、runner 路径检查、GPU 是否可见。
- 缺少 `torch`、`xgboost`、`catboost`、CUDA 相关包或大 wheel 时，写入 `outputs/observations/<date>-auto-research.md` 并暂停，不在正式实验轮里安装。
- 竞赛依赖安装、锁文件整理、GPU smoke、小样本 runner smoke 交给 `competition-runtime-prep-skill`。
- 需要系统库、GPU、容器隔离时，由环境准备任务先评估，再考虑 Docker 沙盒材料。
- 脚本运行前设置 `AIASYS_WORKSPACE_ROOT`，路径解析必须限制在工作区内。
- 长任务优先登记在工作区环境和 runner 元数据中，不要把临时命令直接复制成多个项目脚本。

## 并行探索

本 skill 默认不启动多个并行实验分支。需要同时探索多条路线时，先转交 `competition-parallel-research-skill`。

并行编排必须先确定：

- 每条 lane 的唯一版本名或版本名前缀。
- 每条 lane 绑定的 `env_id`。
- 每条 lane 的 session / AutoTask。
- 最大并发数，GPU lane 默认最大并发 1。
- `experiments/index.json` 写回策略，写主索引的动作必须串行化。

## 安全边界

- 不把用户数据复制到工作区之外。
- 不把 token 写入项目代码。
- 下载论文和外部数据时记录来源。
- 自动循环里不执行未解释来源的大段外部代码。
- 处理比赛提交文件前，先确认格式和路径。

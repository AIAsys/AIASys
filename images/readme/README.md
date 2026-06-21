# README 配图索引

本目录存放根目录 `README.md` 使用的展示图。图片按功能分组，标注当前版本状态，方便后续维护时判断是否需要重截。

| 文件名 | 说明 | 拍摄日期 | 状态 |
|--------|------|----------|------|
| `home-hero.png` | 产品官网首页 / 入口页 | 2026-06-21 | 已更新至 v0.4.22 |
| `workspace-layout.png` | 工作区三栏布局（Activity Bar / 主画布 / 当前工作区） | 2026-06-21 | 已新增 |
| `aiasys-workspace-loop.png` | 工作区运行闭环示意 | 2026-06-17 | 可用 |
| `demo-sales-overview.png` | 销售洞察分析工作区总览 | 2026-06-17 | 可用 |
| `demo-sales-report.png` | 销售洞察分析报告 | 2026-06-17 | 可用 |
| `demo-sales-chart.png` | 销售洞察图表预览 | 2026-06-17 | 可用 |
| `demo-industrial-monitor.png` | 工业运行监控工作区 | 2026-06-19 | 可用 |
| `demo-knowledge-graph-exploration.png` | 知识图谱实体关系探索 | 2026-06-19 | 可用 |
| `demo-003-notebook-analysis-overview.png` | Notebook 代码执行与图表预览 | 2026-06-19 | 可用 |
| `demo-003-notebook-analysis-notebook.png` | Notebook 编辑界面 | 2026-06-19 | 可用 |
| `demo-env-vars-overview.png` | 环境变量注入面板 | 2026-06-17 | 可用 |
| `demo-008-knowledge-base-qa-overview.png` | 知识库问答总览 | 2026-06-19 | 可用 |
| `demo-008-knowledge-base-qa-kb.png` | 知识库文档管理 | 2026-06-19 | 可用 |
| `demo-canvas-workflow.png` | Canvas 工作流画布 | 2026-06-17 | 可用 |
| `demo-data-table.png` | 多维表格实验记录 | 2026-06-17 | 可用 |
| `demo-db-query-overview.png` | 工作区数据库 SQL 查询 | 2026-06-17 | 可用 |
| `demo-005-subagent-collaboration-overview.png` | 子 Agent 并行协作总览 | 2026-06-19 | 可用 |
| `demo-005-subagent-collaboration-subagent.png` | 子 Agent 详情 | 2026-06-19 | 可用 |
| `demo-006-autotask-monitoring-overview.png` | AutoTask 自动化任务总览 | 2026-06-19 | 可用 |
| `demo-006-autotask-monitoring-autotask.png` | AutoTask 任务详情 | 2026-06-19 | 可用 |
| `demo-model-config-panel.png` | 模型配置弹窗（默认模型 + 服务商） | 2026-06-21 | 已更新至 v0.4.22 |
| `demo-pdf-translation-dual.png` | PDF 翻译后双栏预览 | 2026-06-17 | 可用 |

## 待补充图（后续可补）

- 能力市场 / MCP 市场 / Skill 市场入口
- 监控任务（Monitor）面板
- 终端面板
- 桌面版系统托盘与原生窗口（Windows/macOS/Linux）

## 重截脚本

需要重新生成首页或模型配置弹窗截图时，可复用 `apps/web/scripts/` 下的 Playwright 脚本（尚未沉淀为稳定脚本，建议按 `frontend-screenshot` Skill 的规范临时编写）。

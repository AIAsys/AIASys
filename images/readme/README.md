# README 配图索引

本目录存放根目录 `README.md` 使用的展示图。图片按功能分组，标注当前版本状态，方便后续维护时判断是否需要重截。

| 文件名 | 说明 | 拍摄日期 | 状态 |
|--------|------|----------|------|
| `home-hero.png` | 产品官网首页 / 入口页 | 2026-06-21 | 已更新至 v0.4.23 |
| `workspace-layout.png` | 工作区三栏布局（Activity Bar / 主画布 / 当前工作区） | 2026-06-21 | 已新增 |
| `panel-current-workspace.png` | Activity Bar「当前工作区」面板 | 2026-06-21 | 已新增 |
| `panel-global-workspace.png` | Activity Bar「全局工作区」面板 | 2026-06-21 | 已新增 |
| `panel-data-query.png` | Activity Bar「数据查询」面板 | 2026-06-21 | 已新增 |
| `panel-file-search.png` | Activity Bar「文件搜索」面板 | 2026-06-21 | 已新增 |
| `panel-subagents.png` | Activity Bar「专家协作节点」面板 | 2026-06-21 | 已新增 |
| `panel-file-changes.png` | Activity Bar「文件变更」面板 | 2026-06-21 | 已新增 |
| `panel-capability-management.png` | 全局控制面板「能力管理」页 | 2026-06-21 | 已新增 |
| `aiasys-workspace-loop.png` | 工作区运行闭环示意 | 2026-06-22 | 已升采样至 3200x2000 |
| `demo-sales-overview.png` | 销售洞察分析工作区总览 | 2026-06-22 | 已更新至 v0.4.23，高分辨率 2x |
| `demo-sales-report.png` | 销售洞察分析报告 | 2026-06-22 | 已更新至 v0.4.23，高分辨率 2x |
| `demo-sales-chart.png` | 销售洞察图表预览 | 2026-06-22 | 已更新至 v0.4.23，高分辨率 2x |
| `demo-industrial-monitor.png` | 工业运行监控工作区 | 2026-06-19 | 可用 |
| `demo-knowledge-graph-exploration.png` | 知识图谱实体关系探索 | 2026-06-19 | 可用 |
| `demo-003-notebook-analysis-overview.png` | Notebook 代码执行与图表预览 | 2026-06-19 | 可用；建议后续重截真正的 Notebook 编辑界面 |
| `demo-env-vars-overview.png` | 环境变量注入与验证 | 2026-06-22 | 已更新至 v0.4.23，高分辨率 2x |
| `demo-008-knowledge-base-qa-overview.png` | 知识库问答总览 | 2026-06-19 | 可用 |
| `demo-008-knowledge-base-qa-kb.png` | 知识库文档管理 | 2026-06-19 | 可用 |
| `demo-canvas-workflow.png` | Canvas 工作流画布 | 2026-06-22 | 已更新至 v0.4.23，高分辨率 2x |
| `demo-data-table.png` | 多维表格实验记录 | 2026-06-22 | 已更新至 v0.4.23，带真实数据，高分辨率 2x |
| `demo-db-query-overview.png` | 工作区数据库 SQL 查询 | 2026-06-22 | 已更新至 v0.4.23，高分辨率 2x |
| `demo-005-subagent-collaboration-overview.png` | 子 Agent 并行协作总览 | 2026-06-19 | 可用 |
| `demo-006-autotask-monitoring-overview.png` | AutoTask 自动化任务总览 | 2026-06-19 | 可用 |
| `demo-model-config-panel.png` | 模型配置弹窗（默认模型 + 服务商） | 2026-06-21 | 已更新至 v0.4.23 |
| `demo-pdf-translation-dual.png` | PDF 翻译产物与过程说明 | 2026-06-22 | 已更新至 v0.4.23，高分辨率 2x |

## 待补充图（后续可补）

- 能力市场 / MCP 市场 / Skill 市场入口
- 监控任务（Monitor）面板
- 终端面板
- 桌面版系统托盘与原生窗口（Windows/macOS/Linux）

## 重截脚本

需要重新生成 L2 demo 展示图时，可复用 `apps/web/scripts/committed/capture-readme-demos.mjs`，用法见脚本头部注释。

# AIASys Data Visualization Guide Skill

AIASys 内置 Skill，为数据分析子 Agent 提供数据可视化规范。

## 内容

- ECharts 图表资产规范和 JSON 结构示例
- CSV 表格预览 directive 用法
- matplotlib 静态图片 fallback 规则
- aiasys-file directive 引用协议
- base64 嵌入禁令

## 使用方式

由 `data_analyst` 子 Agent 在需要输出图表或展示数据时通过 `LoadSkill(name="aiasys-data-viz-guide-skill")` 加载。

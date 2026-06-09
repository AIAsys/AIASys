# AIASys Notebook-first Workflow Skill

AIASys 内置 Skill，为数据分析子 Agent 提供 Notebook-first 工作流指南。

## 内容

- Notebook 工具使用顺序和常见调用模式
- 默认工作流（列 notebook → 创建/复用 → 拆分 cells → 运行 → 交付）
- Notebook 文件编辑规则（12 条）
- 数据观察精简原则（防止 DataFrame 输出挤占上下文）

## 使用方式

由 `data_analyst` 子 Agent 在执行数据分析任务前通过 `LoadSkill(name="aiasys-notebook-first-skill")` 加载。

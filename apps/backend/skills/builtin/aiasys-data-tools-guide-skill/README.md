# AIASys Data Tools Guide Skill

AIASys 内置 Skill，为数据分析子 Agent 提供领域工具使用指南。

## 内容

- 数据库访问（db helper、handles、读写示例）
- 知识库工具集（查询、管理）
- 知识图谱工具集（搜索、实体详情、写入原则）
- 多维表工具集
- Canvas 工具集

## 使用方式

由 `data_analyst` 子 Agent 在涉及数据库、知识库、知识图谱、多维表或 Canvas 时通过 `LoadSkill(name="aiasys-data-tools-guide-skill")` 加载。

# 竞赛研究

竞赛场景的单分支研究与实验闭环入口。覆盖项目初始化、AGENTS.md 维护、文献检索、论文摄入、单环境串行实验循环，以及知识图谱和可视化看板管理。

## 适用场景

- 用户提供了竞赛题目、数据或历史实验材料
- 需要在已准备的运行环境中建立 baseline
- 单分支、单环境的持续优化实验

## 相关 Skill 分工

| 目标 | 使用 Skill |
|------|-----------|
| 准备 UV 环境、安装依赖、GPU 检查 | `competition-runtime-prep-skill` |
| 单分支、单环境、串行实验闭环 | `competition-research-skill`（本 Skill） |
| 多分支、多环境、并行探索编排 | `competition-parallel-research-skill` |

## 注意事项

- 本 skill 只做轻量环境预检，不在正式实验轮里安装大依赖
- 默认使用已准备好或已绑定到当前工作区的运行环境

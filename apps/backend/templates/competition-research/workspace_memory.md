## 长期目标
- 在竞赛中建立可运行的 baseline，通过实验循环持续优化分数

## 关键术语
- Baseline：可运行的最小实验版本，用于验证 runner 和记录初始分数
- v0：第一个 baseline，通常是最简单的可行方案
- Runner：项目执行入口，必须满足可重复执行、保存日志、给出可记录分数
- Keep/Discard：实验结论，以竞赛最终指标为唯一判断标准
- Anti-pattern：已验证不可行的方向或方法，避免重复踩坑
- Trusted best：经过稳定性检查后的可信最优版本

## 稳定约束
- 严禁拟造训练数据，缺数据时暂停并请用户提供
- 建立 baseline 前必须完成系统性数据探索
- Baseline 命名必须遵循 `{family}_b{NNN}_{slug}` 格式
- 每轮实验必须有明确假设、版本名、运行日志、分数和结论
- 最终 keep/discard 以竞赛最终指标为准，代理指标只做辅助诊断
- 数据探索报告和可视化图表落盘到 `research_views/data_exploration/`

## 已确认决策
-

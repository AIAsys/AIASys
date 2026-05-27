# 竞赛并行研究编排

为竞赛项目编排多会话、多环境、多 AutoTask lane 的并行探索。拆分方向、分配 env_id、控制并发、避免输出冲突，并汇总各 lane 结果。

## 适用场景

- 需要同时探索 LightGBM、XGBoost、Transformer 等多条路线
- 同一竞赛需要多个 env_id 服务不同会话
- 需要把多个 AutoTask lane 的结果汇总成主线建议

## 注意事项

- 本 skill 只负责编排，不亲自实现每条 baseline 的细节
- 单条 lane 的实验执行交给 `competition-research-skill`
- 环境准备交给 `competition-runtime-prep-skill`

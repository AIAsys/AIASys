# 竞赛运行环境准备

为竞赛项目准备可绑定的 Python/UV 运行环境。包括选择或创建环境、安装依赖、锁定版本、验证导入、检查 GPU 和执行小样本 runner smoke。

## 适用场景

- 需要安装 XGBoost、Optuna、Torch、CUDA 相关包等大依赖
- AutoTask 因依赖缺失、UV 同步卡住或 GPU 不可用而阻塞
- 为不同实验路线准备多个环境（如 `xgb-optuna`、`torch-small`）

## 注意事项

- 本 skill 只负责环境准备，不负责正式跑分和实验结论
- 不写 keep/discard 实验结论
- 不替代 `competition-research-skill` 的实验循环

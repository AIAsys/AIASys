# Kaggle House Prices — 竞赛攻关

## 竞赛信息

- **竞赛名称**：House Prices - Advanced Regression Techniques
- **评估指标**：RMSE（均方根误差）
- **优化方向**：minimize（越小越好）
- **数据来源**：Ames Housing dataset，包含 79 个解释变量描述爱荷华州艾姆斯市的住宅特征
- **提交格式**：CSV，包含 Id 和 SalePrice 两列
- **时间预算**：2 周

## 当前状态

- 竞赛类型：回归预测（房价）
- 是否已有 baseline：是（v0 已完成）
- 当前最优分数：0.14235 RMSE
- 当前阶段：ensemble（模型融合优化）
- 项目 runner：`scripts/experiment.py`

## 目录结构

```
.
├── statement/          # 赛题描述和数据说明
├── data/               # 数据目录
│   ├── raw/            # 原始数据（train.csv, test.csv）
│   └── processed/      # 处理后数据（特征工程产物）
├── baselines/          # baseline 版本目录
├── baseline_history/   # baseline 历史记录和对比
├── experiments/        # 实验索引（experiments/index.json）
├── references/         # 文献与参考方法
├── scripts/            # 项目脚本
│   ├── experiment.py   # 实验运行入口
│   └── baseline_names.py  # baseline 命名验证
├── outputs/            # 输出产物
│   ├── submissions/    # 提交文件
│   ├── logs/           # 运行日志
│   └── reports/        # 实验报告
└── research_views/     # 研究看板与可视化
```

## 数据探索报告

见 `research_views/data_exploration/report.md`

关键发现：
- 训练集 1460 条，测试集 1459 条
- 缺失值最多的特征：PoolQC（99.5% 缺失）、MiscFeature（96.3% 缺失）、Alley（93.8% 缺失）
- 目标变量 SalePrice 右偏，取对数后接近正态分布
- OverallQual 与 SalePrice 相关性最强（0.79）

## 实验记录

见 `experiments/index.json`

当前最优版本：`ensemble_b003_xgb_lgb_stack`（0.14235 RMSE）

## 文献索引

见 `references/index.json`

---

*以上竞赛信息为示例（基于 Kaggle House Prices 竞赛），请替换为你实际参与的竞赛。*

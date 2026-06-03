# 竞赛攻关项目

## 项目信息

请在创建项目后替换以下内容：

- **竞赛名称**：`<请替换>`
- **评估指标**：`<如 RMSE / Accuracy / F1>`
- **优化方向**：`<minimize 或 maximize>`
- **数据来源**：`<请描述>`
- **提交格式**：`<如 CSV 含 Id 和 Target 两列>`
- **时间预算**：`<如 2 周>`

## 当前状态

- 竞赛类型：`<分类 / 回归 / 排序 / 对抗 ...>`
- 是否已有 baseline：`<否 / 是>`
- 当前最优分数：`<暂无>`
- 当前阶段：`literature`（文献调研 → baseline → 特征 → 模型 → 集成）
- 项目 runner：`scripts/experiment.py`

## 目录结构

```
.
├── statement/          # 赛题描述和数据说明
├── data/               # 数据目录
│   ├── raw/            # 原始数据
│   └── processed/      # 处理后数据
├── baselines/          # baseline 版本目录
├── baseline_history/   # baseline 历史记录
├── experiments/        # 实验索引（experiments/index.json）
├── references/         # 文献与参考方法
├── scripts/            # 项目脚本
│   ├── experiment.py   # 实验运行入口
│   └── baseline_names.py  # baseline 命名验证
├── outputs/            # 输出产物
│   ├── submissions/    # 提交文件
│   ├── logs/           # 运行日志
│   ├── reports/        # 实验报告
│   └── observations/   # 自动研究观察记录
└── research_views/     # 研究看板与可视化
    └── data_exploration/  # 数据探索报告
```

## 快速开始

1. 将竞赛数据放入 `data/raw/`
2. 在 `statement/` 中记录赛题描述和规则
3. 运行 `python3 scripts/experiment.py --mode status` 查看项目状态
4. 建立第一个 baseline，命名为 `baseline_b001_<描述>`
5. 用 `experiments/index.json` 跟踪实验历史

## 实验记录

见 `experiments/index.json`

---

*首次使用时请替换所有 `<...>` 占位符为实际项目信息。*

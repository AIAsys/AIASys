# 竞赛攻关工作区

## 角色

你是竞赛研究员，帮助用户在数据竞赛或算法竞赛中建立 baseline、持续实验优化，最终获得好成绩。

## 当前项目状态（运行时刷新）

- 竞赛：House Prices - Advanced Regression Techniques
- 最优版本：ensemble_b003_xgb_lgb_stack（0.14235 RMSE）
- 可信最优版本：ensemble_b002_xgb_lgb（0.14567 RMSE）
- 当前阶段：ensemble
- 最近实验：ensemble_b003_xgb_lgb_stack，stacking 策略有效但需验证稳定性

## 反模式

以下错误已经验证不可行，避免重复踩坑：

1. **不探索数据直接上复杂模型**
   - 后果：错过关键特征关系，模型性能低于预期
   - 正确做法：先完成数据探索报告，再建模

2. **不做交叉验证就相信单次运行的分数**
   - 后果：LB 上分但 CV 下降，最终排名下滑
   - 正确做法：以 5-fold CV 为主要评估标准

3. **在测试集上调参**
   - 后果：严重过拟合，无法泛化到 private LB
   - 正确做法：只用训练集做 CV，测试集只用于最终提交

4. **特征工程不做记录，无法复现**
   - 后果：无法回到之前有效的版本
   - 正确做法：每个版本的特征列表记录在 experiments/index.json

5. **盲目堆叠模型而不分析融合增益来源**
   - 后果：模型复杂度增加但分数不升
   - 正确做法：分析各基模型的相关性，差异大的模型融合增益高

## 优先队列

当前待验证的方向（按优先级排序）：

1. **尝试 CatBoost 作为第三个基模型**
   - 假设：CatBoost 对类别特征的处理优于 XGB/LGB，可能带来互补增益
   - 预期产出：catboost_b001 版本，目标分数 < 0.145

2. **做特征重要性分析，剔除冗余特征**
   - 假设：当前特征过多，部分冗余特征引入噪声
   - 预期产出：精简特征子集 + 模型简化

3. **尝试目标编码处理高基数类别特征**
   - 假设：Neighborhood（25 个类别）等特征用 one-hot 太稀疏
   - 预期产出：target_encoding_b001 版本

4. **分析 stacking 的 out-of-fold 预测稳定性**
   - 假设：stacking 可能在某些 fold 上过拟合
   - 预期产出：稳定性报告，决定是否需要回退到简单平均

## 工具与脚本

以下脚本通常由 `competition-research-skill` 提供或根据项目需要自行创建。
如果已安装该 skill，可从 skill 示例目录复制相关脚本到本项目 `scripts/` 目录。

```bash
# 验证 baseline 命名
python3 scripts/baseline_names.py --mode validate

# 查看实验状态
python3 scripts/experiment.py --mode status

# 运行指定版本
python3 scripts/experiment.py --mode run --version <version>

# 记录实验结果
python3 scripts/experiment.py --mode record

# 更新研究视图
python3 scripts/update_research_views.py

# 搜索论文
python3 scripts/arxiv_search.py --query "gradient boosting regression"

# 生成 ECharts 图表
python3 scripts/generate_echarts.py

# 导出图表 PNG
python3 scripts/export_echarts_png.py
```

## HTML 看板

`research_views/current.html`

## baseline 命名规则

格式：`{family}_b{NNN}_{slug}`

| family | 含义 | 示例 |
|--------|------|------|
| baseline | 最简可行方案 | baseline_b001_naive_mean |
| feature | 特征工程实验 | feature_b002_log_transform |
| model | 单一模型调参 | model_b003_xgb_depth6 |
| ensemble | 模型融合 | ensemble_b004_xgb_lgb_avg |

## 硬性规则

- 严禁拟造训练数据，缺数据时暂停并请用户提供
- 建立 baseline 前必须完成系统性数据探索（research_views/data_exploration/）
- 每轮实验必须有明确假设、版本名、运行日志、分数和结论
- 最终 keep/discard 以竞赛最终指标为准，代理指标只做辅助诊断
- 特征工程步骤必须可复现，记录在 experiments/index.json

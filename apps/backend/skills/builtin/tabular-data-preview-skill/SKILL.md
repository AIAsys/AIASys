+++
name = "表格数据预览"
description = "读取和预览 Excel、CSV 等表格文件的标准化方法论。当用户上传或提到表格文件（.xlsx / .csv / .xls 等）、需要查看表格结构、列名、数据样本、统计摘要时使用。不要直接对表格文件使用 ReadFile，ReadFile 只能读纯文本文件。"
+++


# 表格数据预览 Skill

## 能力边界

本 skill 提供表格文件的**结构化预览**能力，不是数据清洗或深度分析。

适用场景：
- 用户上传了 Excel / CSV 文件，需要了解里面有什么数据
- 需要查看列名、数据类型、缺失值情况
- 需要快速浏览数据样本（头部、尾部、随机行）
- 多 sheet Excel 需要查看每个 sheet 的概览

不适用场景：
- 深度数据清洗（去重、异常值处理等）→ 走数据分析工作流
- 复杂可视化 → 用 matplotlib / seaborn / plotly
- 建模和预测 → 用 scikit-learn

## 读取策略

ReadFile 不能读取 Excel 文件。读取表格数据一律通过 Shell 工具运行 Python 脚本。

依赖要求（通常已预装，缺失时先用 RuntimeEnvironment 安装）：
- `pandas`：DataFrame 操作
- `openpyxl`：读取 .xlsx
- `xlrd`：读取旧版 .xls

## 预览方法论

按以下顺序执行，每一步都基于上一步的结果做下一步决策：

### Step 1：文件结构识别

目标：确认文件类型、sheet 数量、行列规模。

多 sheet Excel 概览脚本：

```python
import pandas as pd

file_path = "data.xlsx"  # 替换为实际路径
xls = pd.ExcelFile(file_path)
print("文件:", file_path)
print("Sheet 列表:", xls.sheet_names)
for sheet in xls.sheet_names:
    df = pd.read_excel(xls, sheet_name=sheet)
    print(f"  [{sheet}] {len(df)} 行 x {len(df.columns)} 列")
```

CSV 概览脚本：

```python
import pandas as pd

file_path = "data.csv"  # 替换为实际路径
df = pd.read_csv(file_path)
print(f"文件: {file_path}")
print(f"维度: {len(df)} 行 x {len(df.columns)} 列")
```

### Step 2：列名与数据类型概览

目标：了解每一列的名称、类型、缺失率。

```python
print("=== 列名与数据类型 ===")
print(df.dtypes)

print("\n=== 缺失值统计 ===")
missing = df.isnull().sum()
print(missing[missing > 0] if missing.sum() > 0 else "无缺失值")
print(f"总缺失率: {df.isnull().sum().sum() / df.size:.2%}")
```

### Step 3：滑动窗口预览

目标：在不加载全量输出到对话的前提下，了解数据的实际内容。

窗口策略：
- **头部窗口**：前 5 行，验证列名与数据格式是否匹配
- **尾部窗口**：最后 5 行，检查数据截断或异常结尾
- **随机窗口**：随机采样 5 行，检验数据分布代表性
- **中间窗口**：从 25%、50%、75% 位置各取 3 行，检查中段数据质量

```python
import pandas as pd

def preview_dataframe(df, head_n=5, tail_n=5, sample_n=5):
    """滑动窗口预览 DataFrame，控制输出行数避免 token 溢出。"""
    total = len(df)
    print(f"总行数: {total}")

    # 头部窗口
    print(f"\n--- 头部前 {head_n} 行 ---")
    print(df.head(head_n).to_string())

    # 尾部窗口
    print(f"\n--- 尾部后 {tail_n} 行 ---")
    print(df.tail(tail_n).to_string())

    # 随机窗口
    if total > sample_n:
        print(f"\n--- 随机采样 {sample_n} 行 ---")
        print(df.sample(min(sample_n, total), random_state=42).to_string())

    # 中间窗口
    if total > 20:
        print("\n--- 中间位置采样 ---")
        for pct in [0.25, 0.50, 0.75]:
            idx = int(total * pct)
            window = df.iloc[idx:idx + 3]
            print(f"\n位置 {pct:.0%} (第 {idx} 行附近, {len(window)} 行):")
            print(window.to_string())

# 使用示例
# df = pd.read_excel("data.xlsx", sheet_name=0)
# preview_dataframe(df)
```

### Step 4：数值列统计摘要

目标：快速了解数值列的分布特征和异常迹象。

```python
numeric_cols = df.select_dtypes(include=["number"]).columns
if len(numeric_cols) > 0:
    print("=== 数值列统计摘要 ===")
    print(df[numeric_cols].describe().T)
    print("\n=== 分位数 (1% / 5% / 25% / 50% / 75% / 95% / 99%) ===")
    print(df[numeric_cols].quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]).T)
else:
    print("无数值列")
```

## 大数据集处理

当文件超过 10 万行或 100MB 时，先做限制预览：

```python
# 只读前 1000 行做结构预览
df = pd.read_excel(file_path, sheet_name=0, nrows=1000)

# 或者只读特定列
df = pd.read_excel(file_path, sheet_name=0, usecols=["A", "B", "C"])
```

## 输出规范

预览结果应按以下结构整理后汇报给用户：

1. **文件概览**：文件名、sheet 数量（Excel）、总行数、总列数
2. **字段清单**：列名、数据类型、缺失率（表格形式，不要全文输出原始数据）
3. **数据样本**：合并展示头部 + 尾部 + 随机采样（使用 `preview_dataframe` 控制行数）
4. **数值摘要**：数值列的 mean / std / min / max / 中位数
5. **初步观察**：基于预览结果给出 2-3 句话的数据质量判断（如"发现 price 列存在负值，需要清洗"）

## 约束

- 预览时不要修改原始文件，不要写回 Excel / CSV
- 不要把完整 DataFrame 直接 `print(df)` 输出到对话中，会超出 token 限制；始终用 `to_string()` 并控制行数
- 大数据集先用 `nrows` 做限制预览，确认结构后再决定是否全量加载
- 预览后如需要深度分析，引导用户进入数据分析工作流，将清洗和建模脚本写入 notebooks/

+++
name = "AIASys Data Visualization Guide"
description = "AIASys 数据可视化规范。涵盖 ECharts 图表资产、CSV 表格预览、matplotlib 静态图片展示和 base64 禁用规则。需要输出图表或展示数据时读取本 skill。"
+++

# 交互式图表与图片展示规范

**重要**：当你需要输出图表时，默认优先生成 ECharts 图表资产文件，再在最终回复中用 directive 引用；静态图片作为 fallback，而不是默认主链。

## ECharts 优先规则

当图表适合用交互式方式展示时，默认遵循以下规则：

1. 把图表保存为工作区图表资产文件：
   - 代码写入相对路径：`_charts/{chart_id}.chart.echarts.json`
   - 最终回复引用展示路径：`/workspace/_charts/{chart_id}.chart.echarts.json`
2. 最终回复中不要嵌入大段图表 JSON，也不要用三反引号包 `echarts`
3. 最终回复中统一使用 `aiasys-file` directive 引用文件：

```markdown
:::aiasys-file{src="/workspace/_charts/{chart_id}.chart.echarts.json" type="echarts"}
:::
```

4. 图表资产默认使用**单文件自包含 JSON**
5. 默认优先输出纯 JSON 的 `safe_spec`
6. 不要输出任意 JS、HTML 片段或 formatter 函数字符串
7. 如无必要，不要额外拆分 `csv / parquet / data.json`

## `aiasys-file` directive 类型白名单

当前只允许以下 `type`：

- `echarts`: 用于 ECharts 图表资产文件，例如 `*.chart.echarts.json`
- `csv`: 用于 CSV 表格文件，例如 `result.csv`

## 推荐的图表资产结构

```json
{
  "kind": "aiasys.chart",
  "version": 1,
  "engine": "echarts",
  "mode": "safe_spec",
  "meta": {
    "title": "销售趋势图",
    "description": "按月份展示销售额变化"
  },
  "view": {
    "title": {"text": "销售趋势图"},
    "tooltip": {"trigger": "axis"}
  },
  "dataset": {
    "mode": "inline",
    "source": [
      {"month": "1月", "sales": 120},
      {"month": "2月", "sales": 200},
      {"month": "3月", "sales": 150}
    ]
  },
  "resources": [],
  "interaction": {},
  "payload": {
    "xAxis": {"type": "category", "name": "月份"},
    "yAxis": {"type": "value", "name": "销售额"},
    "series": [
      {
        "type": "line",
        "name": "销售额",
        "encode": {"x": "month", "y": "sales"}
      }
    ]
  }
}
```

## 生成 ECharts 图表的推荐流程

```python
import json
import os

chart_dir = "_charts"
os.makedirs(chart_dir, exist_ok=True)

chart_path = os.path.join(chart_dir, "sales_trend.chart.echarts.json")

chart_spec = {
    "kind": "aiasys.chart",
    "version": 1,
    "engine": "echarts",
    "mode": "safe_spec",
    "meta": {
        "title": "销售趋势图",
        "description": "按月份展示销售额变化"
    },
    "view": {
        "title": {"text": "销售趋势图"},
        "tooltip": {"trigger": "axis"}
    },
    "dataset": {
        "mode": "inline",
        "source": [
            {"month": "1月", "sales": 120},
            {"month": "2月", "sales": 200},
            {"month": "3月", "sales": 150},
        ],
    },
    "resources": [],
    "interaction": {},
    "payload": {
        "xAxis": {"type": "category", "name": "月份"},
        "yAxis": {"type": "value", "name": "销售额"},
        "series": [
            {
                "type": "line",
                "name": "销售额",
                "encode": {"x": "month", "y": "sales"},
            }
        ],
    },
}

with open(chart_path, "w", encoding="utf-8") as f:
    json.dump(chart_spec, f, ensure_ascii=False, indent=2)

print(f"图表已保存到 {chart_path}")
```

## CSV 文件预览 directive

当你希望用户在正文里直接查看工作区中的 CSV 表格时，不要把大段 CSV 原文直接贴进最终回复。请把文件保存到工作区，然后用文件预览 directive 引用。

规范如下：

1. 把 CSV 文件保存到工作区，例如：`result.csv`
2. 在最终回复中使用以下语法：

```markdown
:::aiasys-file{src="/workspace/result.csv" type="csv"}
:::
```

## 静态图片 fallback 规则

当下列情况出现时，可以继续使用静态图片：

- 用户明确要求 PNG 图片
- 当前图表不适合快速组织成 ECharts 结构
- 需要临时输出中间结果截图
- 当前任务只是简单一次性可视化，不需要交互

### 正确的图片展示方式

```python
import matplotlib.pyplot as plt

# 1. 生成并保存图表到工作区
plt.figure(figsize=(10, 6))
plt.plot([1, 2, 3], [4, 5, 6])
plt.title('销售趋势')
plt.savefig('sales_trend.png', dpi=150, bbox_inches='tight')
plt.close()

# 2. 在最终回复中引用展示路径（不要用 base64！）
print("图表已保存到 /workspace/sales_trend.png")
```

**引用格式**：在最终回复中统一使用 `aiasys-file` directive 引用 `/workspace/` 展示路径：
```markdown
分析结果显示销售呈上升趋势：
:::aiasys-file{src="/workspace/sales_trend.png" type="image" alt="销售趋势"}
:::
```

**统一协议**：
- 代码执行时仍然优先使用相对路径写文件，例如 `sales_trend.png`
- 最终回复里统一引用 `/workspace/sales_trend.png`
- 不要改写成完整 `http(s)` 文件链接，避免把本地工作区产物误导成公网稳定地址
- 新消息不要再写相对图片路径 `![图表](sales_trend.png)`，避免前端解析歧义
- 历史消息中的 Markdown 图片语法与旧 HTML `<img>` 仍做兼容，但不是新的主协议

## 严禁使用 base64 嵌入图片

**绝对禁止**将图片转换为 base64 编码嵌入到输出中：

**错误示例（严禁）**：
```python
import base64
# 不要这样做！这会导致历史记录变得巨大
with open('chart.png', 'rb') as f:
    img_base64 = base64.b64encode(f.read()).decode()
print(f"![图表](data:image/png;base64,{img_base64})")  # 禁止！
```

## 注意事项

1. **plt.show() 不会显示图片**：当前 notebook 执行底层仍是受控本地内核，`plt.show()` 不会直接产生前端可见图片输出
2. **务必关闭图表**：使用 `plt.close()` 避免内存泄漏
3. **文件名用英文**：避免中文文件名导致的问题
4. **永远不要使用 base64**：即使是单张图片，也不要用 base64 嵌入

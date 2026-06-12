+++
name = "AIASys matplotlib 中文字体配置"
description = "AIASys matplotlib 跨平台中文字体配置指南。当 Agent 需要用 matplotlib 绘制含中文标签、标题、\n图例的图表时，必须先加载本 skill 完成字体配置，避免出现 tofu 方块（□）。\n覆盖：字体问题根因、setup_cn_font() 使用、自包含 fallback 代码、\n各平台系统字体清单、缓存清理和故障排查。"
+++


# AIASys matplotlib 跨平台中文字体配置

## 问题

matplotlib 默认字体 DejaVu Sans 不含 CJK 字形。直接用中文标题/标签/刻度，渲染出来全是方块（□）。这是 matplotlib 历史最悠久的跨平台痛点。

## 优先方案：使用 AIASys 内置 helper

AIASys 的 agent runtime 已注入 `setup_cn_font()` 和别名 `setup_chinese_font()`。Agent 在 IPython kernel 中只需调用一次：

```python
setup_cn_font()
```

该函数按 `PREFERRED_FONT_FAMILIES` 列表顺序，在系统已安装字体中匹配第一个可用的 CJK 字体，然后设置 `rcParams`：

```
Noto Sans CJK SC → Noto Sans SC → Source Han Sans SC → ... → SimHei → Microsoft YaHei → ... → PingFang SC → Heiti SC
```

三端各自命中：Windows 走到 SimHei / Microsoft YaHei，macOS 走到 PingFang SC / Arial Unicode MS，Linux 走到 Noto Sans CJK / WenQuanYi。

调用时机：**在任何 `import matplotlib.pyplot` 之前或紧接其后**，确保 rcParams 在第一次绘图前生效。

```python
from agent_runtime_helpers.font_helper import setup_cn_font
import matplotlib.pyplot as plt

setup_cn_font()

# 之后正常绘图
plt.figure(figsize=(10, 6))
plt.plot([1, 2, 3], [4, 5, 6])
plt.title("销售趋势")
plt.xlabel("月份")
plt.ylabel("金额（万元）")
plt.savefig("chart.png", dpi=150, bbox_inches="tight")
plt.close()
```

`setup_cn_font()` 返回值：

| 字段 | 含义 |
|------|------|
| `ok` | `True` 表示已成功配置字体，`False` 表示降级为默认字体 |
| `font_name` | 实际使用的字体名称，即写入 rcParams 的名称 |

## 自包含 fallback（脱离 agent_runtime_helpers 时）

如果 Agent 运行在不加载 helper 的沙盒中，用以下自包含代码：

```python
import platform
import matplotlib.pyplot as plt
from matplotlib import font_manager

def _setup_cn_font_simple():
    """自包含版中文字体配置。"""
    _FONT_CANDIDATES = {
        "Windows": ["Microsoft YaHei", "SimHei", "DengXian", "FangSong", "KaiTi"],
        "Darwin": ["Arial Unicode MS", "PingFang SC", "Heiti SC", "Songti SC", "STHeiti"],
        "Linux": [
            "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC",
            "WenQuanYi Micro Hei", "WenQuanYi Zen Hei",
        ],
    }

    system = platform.system()
    candidates = _FONT_CANDIDATES.get(system, _FONT_CANDIDATES["Linux"])
    available = {f.name for f in font_manager.fontManager.ttflist}

    for name in candidates:
        if name in available:
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            print(f"[font] 使用字体: {name}")
            return {"ok": True, "font_name": name}

    print("[font] 未找到 CJK 字体，中文将显示为方块。可安装: apt install fonts-noto-cjk")
    return {"ok": False, "font_name": None}

_setup_cn_font_simple()
```

## 各平台系统字体速查

### Windows

| 字体名称 | 类型 | 覆盖 |
|----------|------|------|
| Microsoft YaHei | 无衬线 | SC/TC，Windows 默认 UI 字体 |
| SimHei | 无衬线 | SC，最广泛支持 |
| DengXian | 无衬线 | SC，Windows 10+ 自带 |
| SimSun | 衬线 | SC，传统宋体 |
| FangSong | 衬线 | SC |
| KaiTi | 衬线 | SC |

### macOS

| 字体名称 | 类型 | 覆盖 |
|----------|------|------|
| Arial Unicode MS | 无衬线 | 多语种，含 CJK |
| PingFang SC | 无衬线 | SC，macOS 10.11+ 默认 |
| Heiti SC | 无衬线 | SC |

### Linux

| 字体名称 | 安装命令（Ubuntu/Debian） |
|----------|---------------------------|
| Noto Sans CJK SC | `sudo apt install fonts-noto-cjk` |
| WenQuanYi Micro Hei | `sudo apt install fonts-wqy-microhei` |
| WenQuanYi Zen Hei | `sudo apt install fonts-wqy-zenhei` |

## 缓存问题

matplotlib 在首次 import 时会扫描系统字体并缓存。安装新字体后必须删除缓存：

```bash
rm -rf ~/.cache/matplotlib/fontlist-*.json
```

代码内重建缓存：

```python
import matplotlib.font_manager as fm
fm.fontManager.__init__()
```

## 调试：查看可用字体

```python
import matplotlib.font_manager as fm

cjk_names = {"SC", "CJK", "Hei", "Song", "Ming", "Gothic", "Mincho"}
for f in fm.fontManager.ttflist:
    for kw in cjk_names:
        if kw.lower() in f.name.lower():
            print(f"{f.name:40s} {f.fname}")
            break
```

## 验证字体生效

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
ax.set_title("中文标题测试 123 abc")
ax.set_xlabel("X 轴标签")
fig.savefig("/tmp/font_test.png", dpi=100)
plt.close()
print("检查 /tmp/font_test.png 确认中文是否正常显示")
```

## 与数据可视化 skill 的关系

本 skill 处理 matplotlib 的字体配置问题，属于前置配置层。`aiasys-data-viz-guide-skill` 规定图表输出形式（ECharts 优先、静态图片 fallback、禁止 base64）。两 skill 互补，生成 matplotlib 静态图片时通常需要先加载本 skill 再加载 data-viz-guide-skill。

## 注意事项

1. `axes.unicode_minus = False` 必须设置，否则负号也变方块。`setup_cn_font()` 已自动处理
2. 不要在 `rcParams["font.sans-serif"]` 中放入不存在的字体名，matplotlib 不会跳过，找不到就退回到 DejaVu Sans
3. Agent sandbox 中 `plt.show()` 不会弹出 GUI 窗口，始终用 `savefig()` 生成文件再引用

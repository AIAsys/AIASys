# AIASys matplotlib 跨平台中文字体 Skill

AIASys 内置 Skill，为 Agent 在 matplotlib 绘图中配置中文字体提供统一入口。

## 覆盖内容

- CJK 字体 tofu 问题根因与解决方案
- `setup_cn_font()` 内置 helper 使用方式
- 脱离 agent_runtime_helpers 的自包含 fallback 代码
- Windows / macOS / Linux 三端系统字体速查
- matplotlib 字体缓存清理
- 故障排查与验证方法

## 使用方式

Agent 在需要生成含中文的 matplotlib 图表前，通过 `LoadSkill(name="aiasys-matplotlib-font-skill")` 加载。

## 与 aiasys-data-viz-guide-skill 的关系

本 skill 负责字体配置层；`aiasys-data-viz-guide-skill` 负责图表输出形式。两者互补，生成 matplotlib 静态图片时通常需要先加载本 skill。

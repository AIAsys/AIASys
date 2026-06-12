# 清理捆绑字体、简化 font_helper

> 创建：2026-06-11 · 状态：待执行

## 背景

实测确认 Windows 11/10、macOS、Ubuntu 桌面全部自带 CJK 无衬线体。AIASys 捆绑的 `NotoSansCJKsc.otf`（16MB）在桌面场景下不会被用到。兜底的极简 Linux / Docker 不是当前主路径，不应让全体用户带着这份冗余。

## 目标

删除捆绑字体文件，精简 `font_helper.py` 为纯系统字体名称匹配，同步清理所有引用链。

## 影响范围（7 个文件）

### 1. 删除 `apps/backend/fonts/NotoSansCJKsc.otf`

删后 `fonts/` 目录变空，一并删除目录。

### 2. 重写 `apps/backend/agent_runtime_helpers/font_helper.py`

删除：
- `PREFERRED_FONT_FILE_NAMES`
- `_bundled_font_paths()`
- `_candidate_font_paths()`
- `setup_cn_font()` 参数 `workspace`、`extra_paths`
- `setup_cn_font()` 返回值中的 `font_path`
- 文件加载路径 (`addfont`)

保留并简化：
- `PREFERRED_FONT_FAMILIES`（已是平台优先列表，无需改）
- `setup_cn_font()` 核心逻辑：遍历 `PREFERRED_FONT_FAMILIES` → 匹配系统字体 → 设 rcParams → 返回

新的 `setup_cn_font()` 签名变为 `setup_cn_font(*, quiet: bool = False) -> dict`，只有系统字体名称匹配一条路径，约 20 行。

### 3. 精简 `apps/backend/app/services/runtime/execution_support.py`

删除：
- `DOCKER_CN_FONT_PATH` 常量（行 25）
- `resolve_backend_font_path()` 函数（行 88-89）
- `rewrite_local_runtime_code()` 的 `host_font_path` 参数
- `rewrite_local_runtime_code()` 内字体路径替换逻辑（行 148-153）
- `build_local_runtime_bootstrap_code()` 中的 `project_font_path` 变量和 `extra_paths` 传参（行 168, 184-186）

变更：
- `setup_cn_font()` 调用去掉 `workspace` 和 `extra_paths` 参数（行 184-185 → 只保留 `quiet=True`）
- `rewrite_local_runtime_code` 签名从 `(code, *, workspace, host_font_path=None)` 变为 `(code, *, workspace)`

### 4. 更新 `apps/backend/app/agents/tools/local_ipython_box.py`

不需要改函数调用——`rewrite_local_runtime_code(code, workspace=workspace)` 本身没有传 `host_font_path`，删除参数不影响调用方。

但需确认 `setup_cn_font` 和 `setup_chinese_font` 仍在 `SENSITIVE_NOTEBOOK_VARIABLE_NAME_MARKERS` 中，保持不变。

### 5. 更新测试 `apps/backend/tests/test_font_helper.py`

旧测试：
```python
def test_setup_cn_font_can_use_bundled_font_without_extra_paths(tmp_path):
    result = setup_cn_font(workspace=tmp_path, quiet=True)
    assert result["ok"] is True
    assert result["font_name"] in {"Noto Sans CJK SC", "Noto Sans SC"}
```

新测试：
- 去掉 `workspace` 参数
- 去掉对 `font_path` 字段的断言
- `result["ok"]` 应为 `True`（当前系统有 Noto Sans CJK SC / WenQuanYi）
- 增加 `result["font_name"]` 应存在于 `PREFERRED_FONT_FAMILIES` 中的断言
- 增加 `plt.rcParams["font.sans-serif"]` 被正确设置的断言

### 6. 更新 skill `apps/backend/skills/builtin/aiasys-matplotlib-font-skill/SKILL.md`

修改：
- "优先方案"章节移除捆绑字体描述，改为直接说明系统字体匹配机制
- `setup_cn_font()` 调用示例去掉 `workspace` / `extra_paths` 参数
- 查找顺序改为：系统已装 CJK 字体（按 `PREFERRED_FONT_FAMILIES` 匹配，三端各自命中）
- 删除捆绑字体相关说明
- 自包含 fallback 代码保持不变（不依赖 helper）

保留：
- 各平台字体速查表
- 缓存清理方法
- 调试代码
- 与 data-viz-guide-skill 的关系说明

### 7. 更新 subagent prompt（两处）

`apps/backend/app/agents/local_sandbox_agent_config/subagent_data_analyst_prompt.md`
`apps/backend/capability_sources/builtin/subagent/data_analyst/prompt.md`

修改 "中文字体配置" 章节：
```diff
- 平台已注入 `setup_cn_font()` / `setup_chinese_font()` helper，优先直接调用
- 不要写 `/usr/share/fonts/custom/NotoSansCJKsc.otf`，那是旧容器路径
- 不要自己手写 `font_manager.fontManager.addfont(...)`
+ 平台已注入 `setup_cn_font()` helper，会自动匹配系统 CJK 字体
+ 不要硬编码字体路径或手写 addfont
```

## 验证步骤

1. `python -m pytest apps/backend/tests/test_font_helper.py -v` — 测试通过
2. `python -c "from agent_runtime_helpers.font_helper import setup_cn_font; r = setup_cn_font(); print(r)"` — 输出 `{"ok": True, "font_name": "Noto Sans CJK SC"}`
3. 生成一张含中文的 matplotlib 测试图，确认无方块
4. grep `NotoSansCJKsc.otf` 全仓库，确认零引用（除本 task-session 文档）
5. 确认 `fonts/` 目录已删除或为空

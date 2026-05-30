---
name: pencil-render-review
description: |
  当需要通过 Pencil MCP 直接查看 .pen 文件的真实渲染效果，尤其是
  “.pen 文件在 WSL 仓库里、Pencil/VS Code 在 Windows 上、还要和真实前端页面对照”
  的场景时使用。适用于打开 WSL 中的 .pen、抓取 Pencil 画板截图、核对渲染问题，
  并与浏览器中的真实前端做差异对照。
---

# pencil-render-review

## 使用场景

- 需要确认 `.pen` 文件在 Pencil 里的真实渲染效果，而不是只看 JSON 结构
- `.pen` 文件位于 WSL 路径下，但 Pencil MCP 实际连接的是 Windows 侧 VS Code / Pencil
- 需要把 Pencil 渲染截图和浏览器中的真实前端页面做 1:1 对照
- `pencil-design` 已经能指导如何设计，但当前回合还缺“如何稳定看到渲染结果”的操作步骤

## 不适用场景

- 只是修改 `.pen` JSON 结构，不需要看实际渲染
- 只是看浏览器页面，不涉及 Pencil 设计稿
- 单纯做前端设计生成，不涉及 WSL 路径和 MCP 渲染链路

## 核心规则

### 规则 1：先确认 Pencil MCP 已启用，再谈截图

先验证当前 Codex 会话里 `pencil` MCP 是否真的可用。

最小检查：

```bash
codex mcp get pencil
codex mcp list
```

如果当前会话里没有 `pencil`，先不要假设截图工具可用。

### 规则 2：WSL 里的 `.pen` 文件不要直接用 Linux 路径喂给 Pencil

Pencil MCP 连的是 Windows 侧应用。对于 WSL 里的 `.pen` 文件，优先转成 Windows 可识别的 UNC 路径。

先拿到 Windows 侧路径：

```bash
wslpath -m /home/ke/projects/AIASys/design/frontend/foo.pen
```

通常会得到类似：

```text
//wsl.localhost/Ubuntu-22.04/home/ke/projects/AIASys/design/frontend/foo.pen
```

如果 `pencil_open_document` 对这个 slash 形式超时，就改用反斜杠 UNC 路径：

```text
\\\\wsl.localhost\\Ubuntu-22.04\\home\\ke\\projects\\AIASys\\design\\frontend\\foo.pen
```

在这个主机上，反斜杠 UNC 路径更稳定。

### 规则 3：不要过度依赖 `get_editor_state` 的“当前活动文档”

`pencil_get_editor_state` 可能还显示 Windows 那边的默认临时文件，例如 `pencil-new.pen`。

这并不代表仓库里的 `.pen` 不能操作。

只要下面两类操作对目标 `filePath` 成功，就视为真正可用：

- `pencil_batch_get(filePath=...)`
- `pencil_get_screenshot(filePath=..., nodeId=...)`

因此：

- `get_editor_state` 用来确认 MCP 连通和读取 schema
- 真正读取 / 截图时，始终显式传 `filePath`

### 规则 4：先看真实前端，再看 Pencil 渲染

如果任务目标是“让 `.pen` 接近真实前端”，不要只看 Pencil。

推荐顺序：

1. 用浏览器工具看真实前端
2. 记录真实页面的关键结构、空态、按钮、间距和颜色
3. 再用 Pencil MCP 抓 `.pen` 的对应画板截图
4. 做差异比对
5. 最后再回写 `.pen`

在这个仓库里，通常和 `browser-cdp`、`pencil-design` 一起使用。

### 规则 5：截图必须按画板或局部节点验证

不要只靠节点树判断“应该没问题”。

至少要做：

- 对目标 artboard 调 `pencil_get_screenshot`
- 对关键大页面额外抽查 1-2 个局部节点
- 发现裁切、字重异常、控件错位后再回改 `.pen`

## 最短工作流

### 1. 确认 MCP 可用

```bash
codex mcp get pencil
```

### 2. 把 WSL 路径转成 Windows 可识别路径

```bash
wslpath -m /home/ke/projects/AIASys/design/frontend/aiasys-workspace-shell/aiasys-workspace-shell-v1.pen
```

### 3. 打开文档

优先尝试：

```text
pencil_open_document(//wsl.localhost/Ubuntu-22.04/...)
```

如果超时，改用：

```text
pencil_open_document(\\\\wsl.localhost\\Ubuntu-22.04\\...)
```

### 4. 读目标画板

```text
pencil_batch_get(filePath=..., nodeIds=[\"artboard-analysis\"], readDepth=1)
```

### 5. 抓截图看渲染

```text
pencil_get_screenshot(filePath=..., nodeId=\"artboard-analysis\")
```

### 6. 和真实前端对照

- 浏览器截图看真实页面
- Pencil 截图看设计稿渲染
- 先记差异，再改稿

## 常见问题

### 问题 1：`pencil_open_document` 说成功，但 `get_editor_state` 还是默认文件

这是已知现象。

处理方式：

- 不要卡在“活动文档名不对”
- 直接对目标 `filePath` 调 `batch_get` 和 `get_screenshot`
- 如果这两步成功，就继续工作

### 问题 2：WSL 路径直接传给 Pencil MCP 超时

不要直接传 `/home/...`。

改用：

- `wslpath -m` 的 Windows 侧路径
- 必要时改成反斜杠 UNC 路径

### 问题 3：只看 Pencil 截图还是不确定哪里不对

说明当前缺少真实对照面。

处理方式：

- 先去浏览器里看真实页面
- 再回来对照 Pencil 截图
- 不要反过来

## 和其他 Skill 的关系

- `pencil-design`
  - 负责 `.pen` 设计方法、组件复用、变量、布局和视觉校验
- `browser-cdp`
  - 负责看真实前端页面
- `pencil-render-review`
  - 只负责把 WSL `.pen` 文件稳定接到 Pencil MCP 并真正看到渲染结果

## 交付检查

完成一次 Pencil 渲染核对，至少满足：

- `pencil` MCP 已确认可用
- 目标 `.pen` 文件已通过 `filePath` 成功读取
- 至少抓到 1 张目标 artboard 的 Pencil 渲染截图
- 已和真实前端截图或浏览器快照做过对照
- 如发现差异，已经明确记录“哪里不同”

---

**注意**: 本 Skill 自给自足，不强制依赖 .ai-rules/ 入口。

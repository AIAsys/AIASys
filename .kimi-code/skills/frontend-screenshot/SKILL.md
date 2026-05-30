---
name: frontend-screenshot
description: |
  当需要在真实浏览器里验证正在运行的前端页面，或把结果导出成截图证据时使用。
  适用于前端交互验收、browser smoke、UI 回归排查、README/docs 截图与评审留档。
  在 AIASys 仓库里，默认浏览器入口优先走 Playwright CLI，而不是仓库内 browser-cdp 模板。
---

# frontend-screenshot

## 使用场景

- 用户说“打开前端看看效果”“帮我测一下这个弹窗/滚动/tooltip”“做一次真实浏览器验证”
- 为前端改动做 browser smoke、交互验收或 UI 回归排查
- 为根 README 生成或更新展示图
- 为 `docs/` 教程补步骤截图
- 为功能评审保留当前 UI 证据图
- 为前端改动做“真实页面 -> 验证记录 / 图片文件”的稳定导出

## 不适用场景

- 只是做静态代码阅读，不需要真实浏览器
- 只是做设计稿，不是从真实前端页面抓图
- 需要 AI 生成插画、海报、贴图，这类应走图片生成而不是截图

## 核心规则

### 规则 1：先看真实前端，不要看代码想象图

这个 skill 处理的是“真实运行中的前端页面”，不是源码想象图。

因此先确认：

- 前端服务已经启动
- 要截图的路由能真实打开
- 页面依赖的后端 / 代理链路也真实可达
- 页面关键内容已经加载完成

在 AIASys 本仓库里，默认前端地址通常是：

```text
http://127.0.0.1:13000
```

### 规则 2：AIASys 仓库内浏览器验证默认走 Playwright CLI

本仓库内新的浏览器入口是：

```bash
cd apps/web
npm run playwright:cli -- --help
```

第一个消费它的入口是：

- `apps/web/package.json` 里的 `playwright:cli` script

默认配置文件是：

- `.playwright/cli.config.json`

因此在 AIASys 仓库里做前端页面验证时，优先顺序应是：

1. Playwright CLI
2. 仓库内现有 Playwright spec / `@playwright/test`
3. 只有当 Playwright 路径当前不可用，或用户明确要求主机级共享浏览器时，才退回 `browser-cdp`

默认视口按笔记本比例处理，而不是手机比例：

```text
1440x900x1
```

如果截图看起来像窄屏手机，先修正视口，再谈页面效果。

### 规则 3：先判定“页面是否就绪”，再谈截图或验收

不要一打开路由就立刻截图，也不要刚看到页面壳子就汇报“前端没问题”。

推荐顺序：

1. 导航到目标页面
2. 先确认 `13000/api/...` 或相关后端链路是通的
3. 用 Playwright CLI 的 `snapshot` / `console` / 可视操作看结构和关键文案
4. 必要时等待关键文本出现或主动做交互
5. 需要留证时再 `screenshot`

至少确认：

- 标题出现
- 主要卡片或面板出现
- Skeleton / Loading / 空白占位已经消失
- 没有异常弹窗、菜单、hover 态遮挡内容

如果页面里直接出现 `Failed to fetch`、空白列表或一直 loading：

- 不要先怪组件
- 先查 `GET /health`
- 再查 `curl http://127.0.0.1:13000/api/...`
- 再确认 Vite 代理目标和当前活跃后端端口是否一致

### 规则 4：图片区分“临时证据”和“正式资产”

不要把所有截图都扔到同一个目录。

本仓库建议分两类：

1. 临时调试 / 评审证据
   - 放 `artifacts/`
   - 这是本地过程产物
   - 不作为长期文档资产

2. 需要提交到仓库的正式展示图
   - 放 `images/` 下的明确子目录
   - 例如：
     - `images/readme/`
     - `images/getting-started/`
     - `images/<doc-name>/`

如果用户明确说“不上传 GitHub”，默认先放 `artifacts/`。

### 规则 5：交互问题必须做对应交互，不要只看静态首屏

如果用户在问：

- 弹窗能不能滚动
- tooltip / hover 有没有问题
- 下拉、切换、切页是否正常
- 分支切换、状态提示、滚动容器是否工作

就必须在真实浏览器里做对应动作，再下结论。

不要只打开页面首屏就判定“没问题”。

### 规则 6：截图前先整理页面状态

真正用于展示的图片，不能带这些噪音：

- 浏览器右键菜单
- hover 态
- tooltip
- 未关闭的 dialog / dropdown
- 开发用 query 参数里造成的异常空态
- 滚动到一半的尴尬位置

必要时先点击、切换 tab、关闭弹层，再截图。

### 规则 7：截图不是必选项，但真实证据是必选项

如果用户只是说“你打开前端看看效果”或“帮我测一下这个 UI”，
这个 skill 依然应该触发。

区别只是：

- 需要交付图片文件时，落截图
- 不需要图片文件时，至少给出真实浏览器验证结论和关键观察

### 规则 8：截图后必须做一次人工式复查

截图成功不等于可用。

至少检查：

- 是否裁切
- 字体是否发虚
- 卡片是否被遮挡
- 间距是否异常
- 是否截到了滚动条、浏览器异常边缘、过多空白
- 文案是否正好停在加载中间态

如果不合格，立即重截，不要把坏图直接留给后续文档使用。

## 执行步骤

### 最短工作流

1. 确认前端页面和后端链路可打开

2. 进入仓库内 Playwright CLI 基线

推荐先使用：

```bash
cd apps/web
npm run playwright:cli -- open http://127.0.0.1:13000
```

常用补充命令：

```bash
cd apps/web
npm run playwright:cli -- snapshot
npm run playwright:cli -- console
npm run playwright:cli -- screenshot --filename=../../.playwright-cli/<name>.png
```

如果仓库里已经有现成 spec，优先复用：

```bash
cd apps/web
npm run test:e2e:lifecycle -- <spec>
```

3. 导航并等待页面稳定

典型顺序：

```text
open -> snapshot / console -> 必要交互 -> screenshot
```

4. 选择输出目录

- 临时证据：`artifacts/<name>.png`
- 正式文档图：`images/<scope>/<name>.png`

5. 截图后立即复查

- 如果是 README / docs 用图，确认画面足够干净和稳定
- 如果是功能证据图，确认关键状态和入口都在画面里

### 回归验证补充

如果当前目标是“验证修复是否生效”，优先顺序应是：

1. 先跑真实页面
2. 再做对应交互验证
3. 如仓库里已有 Playwright spec，补跑 spec
4. 需要留档时再补截图

不要反过来先写一堆脚本、最后才发现连页面真实链路都没通。

## 常见输出模式

### 模式 1：前端可视验收

特点：

- 不一定要求最终导出图片
- 重点是“真实浏览器里有没有复现 / 是否修好”
- 更适合滚动、hover、dialog、状态提示、路由切换这类问题

适合：

- 弹窗滚动问题
- tooltip / hover 态问题
- 右侧边栏交互回归
- 工作区 / 分支 / 调度面板的真实可视验证

### 模式 2：README 展示图

特点：

- 更关注整体气质
- 尽量选完整页面或关键主视图
- 文件放 `images/readme/`

适合：

- 首页 Hero
- 已打开工作区总览
- 知识图谱主工作台

### 模式 3：文档步骤图

特点：

- 更关注“这一步到底点哪里”
- 画面要稳定、聚焦、少噪音
- 文件放 `images/<doc-name>/`

适合：

- getting-started
- 操作流程文档
- 设置说明文档

### 模式 4：本地评审证据图

特点：

- 只要真实、可复查即可
- 可以保留一点调试语义
- 默认放 `artifacts/`

适合：

- UI 回归前后对比
- 提交前留档
- 设计稿和真实前端对照

## 常见问题

### 问题 1：为什么这个 skill 没被触发

最常见原因有两个：

1. 任务被误判成“只是读代码”，没有进入真实浏览器验证
2. skill 被误解成“只有要出图片文件时才用”

修正规则是：

- 只要用户要求“看看效果 / 实测一下 / 前端验收 / browser smoke / 真实浏览器验证”，就应该触发本 skill
- 截图只是这个 skill 的一种输出，不是唯一输出

### 问题 2：截图像手机，不像桌面

原因通常是视口不对。

先显式设置：

```text
viewport = 1440x900x1
```

### 问题 3：图里还是 loading / skeleton 或页面里直接 Failed to fetch

不要急着截图，也不要先判定成纯前端 bug。

先：

- 看 `/health`
- 看 `13000/api/...` 能否通到后端
- 看当前 Vite 代理目标是不是对的
- 再回来做页面验证

### 问题 4：图片该放哪不清楚

按是否需要提交区分：

- 要提交：`images/...`
- 只是本地证据：`artifacts/...`

### 问题 5：Playwright CLI 一次性命令太长，shell quoting 容易出错

优先做这两件事：

- 先用 `npm run playwright:cli -- <subcommand>` 做轻量验证
- 复杂流程优先落临时脚本或直接写成 Playwright spec，不要硬塞超长 one-liner

### 问题 6：一个页面太长

不要默认全页长图。

优先选择：

- 当前首屏
- 关键容器
- 关键面板

只有当用户明确需要完整长图时，才用 full-page screenshot。

## 和其他 Skill 的关系

- `frontend-screenshot`
  - 负责真实前端页面验证、browser smoke 和截图取证
- `frontend-pattern`
  - 负责前端实现与改动
- `bug-analysis`
  - 负责分析“为什么坏了”
- `browser-cdp`
  - 只在 Playwright CLI 当前不可用，或用户明确要求主机级共享浏览器时作为 fallback
- `pencil-render-review`
  - 负责看 `.pen` 的渲染效果，不负责真实前端页面截图
- `frontend-design`
  - 负责设计和视觉质量，不负责截图流程本身

## 交付检查

完成一次“前端真实页面验证 / 截图取证”，至少满足：

- 目标页面来自真实前端，而不是设计稿或静态想象
- 已优先使用 Playwright CLI 作为仓库内浏览器入口
- 截图或验收前已确认页面和后端链路稳定
- 如果用户要的是交互验证，已经做过对应交互，不是只看静态首屏
- 如果输出了图片，图片已落到明确目录
- 如果是正式展示图，文件命名和目录语义清楚
- 已复查图片质量，没有明显遮挡、裁切和加载中状态

---

**注意**: 本 Skill 自给自足，不强制依赖 .ai-rules/ 入口。

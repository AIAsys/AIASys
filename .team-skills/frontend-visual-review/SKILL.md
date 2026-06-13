---
name: frontend-visual-review
description: |
  基于真实浏览器截图/录屏证据，对前端改动进行验收分析、问题定位和修改方案制定。
  适用于用户反馈 UI 异常、完成前端改动后验收、或不确定该怎么调整布局/文案/状态展示时。
  不直接操作浏览器，而是调用 frontend-screenshot 获取证据后再做分析。
  特别关注 AIASys 聊天场景中“实时流式输出”与“历史恢复”两种视图的一致性问题。
---

# frontend-visual-review

## 定位

本 Skill 是前端改动后的**验收与优化方法论**，不是代码规范本身，也不是浏览器操作工具。

它解决的是一类常见问题：

- 代码看起来没问题，但用户说“交互有点怪”。
- 修改了状态/按钮/布局，但不确定真实效果。
- 想优化前端，却抓不住该改哪里。

此时最有效的办法不是继续读代码，而是：

1. **先取证**：按 `frontend-screenshot` 在真实浏览器里截图 / 录屏
2. **再分析**：基于证据逐项检查，把看到的问题转化为具体修改清单
3. **最后复验**：改完后再取证，确认问题解决

本 Skill 负责第 2、3 步；第 1 步交给 `frontend-screenshot`。

## 触发条件

以下任一情况都应先读取本 Skill：

1. 用户明确说“前端有点问题”“交互需要优化”“看看 UI”“这个布局怎么改”。
2. 完成前端改动后需要验收，尤其涉及状态、按钮、布局、滚动、空状态、中文文案。
3. 修改了后端 API 但怀疑前端展示没有同步（如新增状态、字段重命名）。
4. 已经拿到截图/录屏，需要基于证据分析 UI 问题并制定修改方案。
5. 需要把前端验证结论整理成可执行的修改清单。

## 标准流程

### 1. 明确要看什么

先确定一个最小可复现场景：

- 页面入口 URL 是什么？（如 `/workspace?session_id=xxx`）
- 需要点击哪些元素才能到达目标界面？
- 期望看到什么？实际可能看到什么？

不要试图一次验证所有页面。先聚焦一个具体交互路径。

### 2. 启动/复用 dev server

- 前端 dev server 通常跑在 `http://localhost:13000`（Vite）。
- 后端 dev server 通常跑在 `http://localhost:13001`（FastAPI）。
- 验证前检查服务是否可用：`curl http://localhost:13000/` 和 `curl http://localhost:13001/health`。
- 如果服务没启动，按项目惯例启动；如果已在运行，直接复用，不要无谓重启。

### 3. 取证（调用 `frontend-screenshot`）

本 Skill 不直接操作浏览器。获取证据的步骤交给 `frontend-screenshot`：

- 简单验证：用 `npm run playwright:cli` 做单点截图
- 多步交互：写独立 Playwright 脚本，导出截图或视频
- 动态状态：用 MutationObserver 记录快速变化
- 证据统一放到 `design-draft/archive/artifacts/`

你需要告诉 `frontend-screenshot`：

- 目标页面 URL
- 需要执行哪些交互
- 需要 capture 的关键状态（修改前、修改中、修改后）
- 输出图片 / 视频的文件名

拿到证据后，再回到本 Skill 做分析。

### 4. 观察检查清单

拿到截图/视频后，按以下维度逐项检查：

| 维度 | 检查点 | 示例 |
|------|--------|------|
| **状态一致性** | 状态标签是否和底层状态对应？是否中文？ | `closed` 应显示“已关闭”而不是 “Closed” |
| **按钮可用性** | 当前状态下该出现的按钮是否出现？不该出现的是否隐藏？ | 已关闭时应显示“恢复”，隐藏“关闭” |
| **输入控件** | placeholder/禁用状态/错误提示是否合理？ | 关闭后输入框应禁用并提示“无法继续对话” |
| **布局空间** | 主次区域分配是否合理？是否有元素被挤压或留白过多？ | 详情抽屉默认不应占满半个画布 |
| **文案语义** | 文案是否符合产品口径？是否有内部术语泄露到界面？ | 用“会话”而非旧称“Goal” |
| **空状态** | 无数据时是否有友好提示？ | 空列表不要只显示空白 |
| **滚动行为** | 长内容区域是否正确滚动？ | 聊天区域应独立滚动，不要带动整个页面 |
| **颜色/图标** | 状态颜色是否符合设计语义？图标是否容易误解？ | 关闭用灰色，不要用成功绿 |
| **流式/历史一致性** | 同一对话在实时流式 vs 重新加载历史后，结构、顺序、编号是否一致？ | 流式有 `Turn 1/2/3`，历史恢复后不应只剩 `Turn 1` |

### 5. 把观察转为修改清单

对每一个问题，写下：

- 位置：哪个文件、哪个组件。
- 现象：截图上看到了什么。
- 期望：应该变成什么样。
- 修改：最小改动方案。

优先修复**功能可用性**问题（按钮点不了、状态错、输入无效），再处理视觉细节。

### 6. 最小化修改

- 只改检查清单里列出的问题，不要“顺便重构”。
- 优先用现有组件和样式变量，不要引入新抽象。
- 如果涉及状态映射（如 `status` → 中文标签/颜色），优先复用已有的 `statusConfig` 或统一新增，不要散落在组件里。

### 7. 复验

改完后必须重新取证并分析，确认：

- 原问题已解决。
- 没有引入新的布局或交互问题。
- 构建通过（`npm run build` 或等价命令）。

复验时再次调用 `frontend-screenshot` 获取新证据，然后按本 Skill 的检查清单重新过一遍。

建议保存修改前后的对比图，方便向用户说明。

## 常见陷阱

- **只看代码不验证**：前端状态常常在浏览器里才暴露问题，尤其是条件渲染、异步更新、滚动行为。
- **证据不足就下结论**：没有截图/录屏支撑，仅凭文字描述很难定位 UI 问题。
- **一次验证太多**：路径越多，越容易漏掉关键状态。先盯一条路径。
- **过度优化**：先把“能不能用”修好，再考虑“好不好看”。
- **证据乱放**：验证截图属于临时产物，放 `design-draft/archive/artifacts/`；只有正式文档/展示图才放 `images/`。
- **改完不复验**：最小化修改后必须重新按 `frontend-screenshot` 取证，再按本 Skill 检查。
- **改完不关 dev server**：除非用户明确说“测试完就关闭”，否则前后端 dev server 保持运行，方便下一次验证。

## 流式输出与历史恢复一致性专项审计

AIASys 聊天界面同时存在两种数据来源：

1. **实时流式**：通过 SSE 接收 `turn_begin` / `content` / `tool_call` / `tool_result` 等事件，前端逐步拼接 segment。
2. **历史恢复**：页面刷新后从 `/api/sessions/history/{userId}/{sessionId}` 拉取 `messages` 数组，再映射为 segment。

同一套对话在两种路径下可能呈现不同效果，必须**同时截图对比**。

### 必查项

| 检查项 | 说明 |
|--------|------|
| 元素位置 | 是否偏移、重叠、被截断？ |
| 顺序 | 内容顺序是否符合事件/消息顺序？ |
| 分组 | 同一类元素是否被错误地堆叠或拆散？ |
| 编号 | turn/step 编号是否连续、不重复？ |
| 空状态 | 是否有空白分隔线、空工具卡片？ |
| 流式/历史一致性 | 同一数据在两种状态下呈现是否一致？ |

### 典型问题模式

#### 模式 1：同类型 segments 被排序后堆叠

**现象**：所有 `Turn 1/2/3` 分隔线被排到最前面，思考和工具调用被压到下面。  
**根因**：渲染前按类型排序，把同类型 segments 集中到一起。  
**修复**：移除类型排序，保持 segments 原始到达/恢复顺序。  
**验证**：截图确认每个 turn 标记紧接自己的内容。

#### 模式 2：多轮 turn 编号全是 1

**现象**：实时对话里每一轮都显示 `Turn 1`。  
**根因**：runtime 没有显式发出 turn 边界，后端只在第一次内容时自动补一个 `turn_begin`。  
**修复**：在 runtime ReAct 循环每轮开头 `yield` turn 开始标记。  
**验证**：流式截图中 turn 编号应递增。

#### 模式 3：流式和历史展示不一致

**现象**：实时流式有 `Turn 1/2/3`，重新加载历史后只剩 `Turn 1`。  
**根因**：历史恢复时后端把连续 assistant message 合并成一条，丢失了轮次边界。  
**修复方向**：

- 方案 A：不合并 assistant message，每轮一个 chat item。
- 方案 B：合并消息但保留 turn 边界 segment（推荐，侵入最小）。
- 方案 C：历史恢复改读 wire 事件。

**验证**：分别截图流式视图和历史视图，对比 turn 数量和内容归属。

### 构造验证场景的方法

#### 方法 A：真实场景（首选）

1. 启动前后端 dev server。
2. 进入真实 workspace/session。
3. 触发对应交互（发送消息、创建 AutoTask、调用工具等）。
4. 按 `frontend-screenshot` 截图/录屏取证。

#### 方法 B：Mock 流式场景

当缺少 LLM API key 或真实数据不可控时：

```typescript
await page.route("/api/agent/execute/stream", async (route) => {
  const body = [
    `data: ${JSON.stringify({ type: "turn_begin", turn_n: 1 })}\n\n`,
    `data: ${JSON.stringify({ type: "content", content_type: "text", text: "hello" })}\n\n`,
    `data: ${JSON.stringify({ type: "turn_begin", turn_n: 2 })}\n\n`,
    `data: ${JSON.stringify({ type: "content", content_type: "text", text: "world" })}\n\n`,
    "data: [DONE]\n\n",
  ].join("");
  await route.fulfill({
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
    body,
  });
});
```

#### 方法 C：Mock 历史场景

```typescript
await page.route(/\/api\/sessions\/history\/.+/, async (route) => {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      messages: [
        { role: "user", content: "hello" },
        { role: "assistant", content: "reply 1" },
        { role: "assistant", content: "reply 2" },
      ],
    }),
  });
});
```

#### 方法 D：临时审计页面（最快）

当路由/API 拦截复杂时，可新增临时页面：

1. 在 `apps/web/src/pages/` 创建临时审计页面（如 `TurnAuditPage.tsx`）。
2. 在 `App.tsx` 添加临时路由 `/turn-audit`。
3. 页面直接渲染目标组件，传入流式和历史两种 mock segments。
4. 截图后删除临时页面和路由。

> 注意：临时页面和路由必须在审计结束后删除，不能进入版本控制。

## 与相关 Skill 的关系

- `frontend-screenshot`
  - 负责真实浏览器取证：打开页面、执行交互、截图/录屏、保存证据
  - 本 Skill 依赖它获取证据
- `frontend-pattern`
  - 负责前端实现与改动
- `aiasys-frontend-architecture`
  - 告诉你 AIASys 前端的实际骨架，避免按通用最佳实践乱改
- `aiasys-system-design`
  - 提供产品语义（如“会话”“工作区”“协作节点”），用于文案检查
- `bug-analysis`
  - 负责分析“为什么坏了”
- `sop-workflow`
  - 通用任务流程，本 Skill 是其在前端验收场景的具体化
- `task-todo-guide`
  - 复杂审计任务可拆分为 TODO 跟踪

## 案例：子 Agent 前端交互优化

**场景**：子 Agent（专家协作节点）关闭后，前端没有“恢复”入口，状态显示英文，执行详情默认展开挤压对话区。

**做法**：

1. 按 `frontend-screenshot` 取证：进入子 Agent Tab，截图关闭前、关闭后、恢复后三种状态。
2. 基于证据观察发现：
   - 关闭后 Badge 显示 “Idle”。
   - 关闭后没有恢复按钮。
   - 执行详情默认展开，聊天区域只剩一半。
3. 修改：
   - `SubagentTabContent`：用 `statusConfig` 取中文标签，`completed/closed/cancelled` 都显示“恢复对话”。
   - `SubAgentCallCard` / `SubAgentDetailDrawer`：补全 `closed` 状态配置。
   - `SubagentTabContent`：执行详情默认折叠，增加切换条。
4. 复验：按 `frontend-screenshot` 重新截图，确认关闭状态显示“已关闭”+“恢复对话”，恢复后显示“空闲”+输入可用，展开折叠正常。

## 输出要求

使用本 Skill 时，最终回复应包含：

- 观察到的关键问题（配截图证据）。
- 修改文件清单。
- 修改前后的对比说明。
- 验证结果（构建/测试/截图）。

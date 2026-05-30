# 并行 worktree 开发手册

这份手册用于处理一类很具体的场景：

- 主工作树已经很脏，不能直接承接新任务
- 一个任务可以拆成 2 到 4 条低冲突子线
- 用户明确要求并发开发，或者明确要求使用 worktree

它不替代 `worktree-audit.md`。

- `parallel-worktree-development.md` 负责“怎么开并行开发”
- `worktree-audit.md` 负责“怎么审计和清理已有 worktree”

## 1. 什么时候该开并行 worktree

满足下面任意两条，就可以优先考虑：

1. 当前任务能拆成多个低耦合子任务
2. 主工作树已有大量无关脏改动
3. 用户明确要求并发开发
4. 后端、前端、提示词、测试可以明显分开写集
5. 同一个任务预计要跨多个回合推进

不适合开并行 worktree 的情况：

1. 任务本身很小，只改 1 到 2 个文件
2. 多条子线会改同一批核心文件
3. 契约还没冻结，拆开后只会各改各的

## 2. 开工前必须先做的事

### 2.1 先冻结边界

主控在派工前先回答清楚三件事：

1. 这次最终要交付什么
2. 哪几条子线可以并行
3. 每条子线不能碰什么

如果这三件事说不清，不要急着开 worktree。

### 2.2 先写 task session 台账

并行 worktree 一启动，当前 active task session 里必须出现一张表，至少记录：

| 子线 | worktree | 分支 | 负责人 | 当前状态 | 写集边界 |
|------|----------|------|--------|----------|----------|
| backend | `/abs/path/...` | `feat-xxx-backend` | backend 子 Agent | 运行中 | backend route / service / tests |

最低要求：

1. `worktree` 必须写绝对路径
2. `branch` 必须和 worktree 对上
3. `负责人` 要写主控还是哪个子 Agent
4. `当前状态` 至少有 `待启动 / 运行中 / 已回补 / 已完成 / 已清理`
5. `写集边界` 要写文件或模块范围，不能只写“后端”“前端”

没有这张表，后面很容易忘记哪个分支正在干什么。

## 3. 推荐目录和命名

推荐目录：

```bash
PROJECT_DIR="$(git rev-parse --show-toplevel)"
WORKTREE_DIR="$PROJECT_DIR.worktrees"
```

推荐命名：

- worktree 目录名和分支名保持一致
- 名字里带任务类型和短描述

例子：

- `feat-resource-workbench-backend`
- `feat-resource-workbench-prompt`
- `feat-resource-workbench-frontend`
- `fix-session-runtime-summary`

## 4. 创建步骤

### 4.1 检查环境

```bash
git branch --show-current
git worktree list
```

如果用户明确要求多 Agent 并发，再额外确认：

```bash
command -v codex
codex login status
command -v tmux
```

### 4.2 创建 worktree

```bash
PROJECT_DIR="$(git rev-parse --show-toplevel)"
WORKTREE_DIR="$PROJECT_DIR.worktrees"

mkdir -p "$WORKTREE_DIR"

git worktree add "$WORKTREE_DIR/feat-resource-workbench-backend" \
  -b feat-resource-workbench-backend \
  dev
```

规则：

1. 每个 worktree 必须绑定独立分支
2. 基线分支写清楚，一般是当前主分支或本轮冻结的基线分支
3. 不要把主工作树的未提交脏改动自动带进新 worktree

## 5. 主控怎么拆任务

推荐拆法：

1. 主控先做契约冻结
2. 子线按写集拆开
3. 主控保留集成权，不让子线直接互相改对方文件

常见拆分：

### 场景 A：后端 + 提示词 + 前端

| 子线 | 负责内容 | 不要碰 |
|------|----------|--------|
| backend | 表、service、route、backend tests | frontend、prompt |
| prompt | prompt、上下文格式、prompt tests | route、frontend |
| frontend | 画布对象、UI 壳层、前端 API/types | backend、prompt |
| 主控 | task session、集成、冲突处理、总验证 | 不把自己再变成第四条实现子线 |

### 场景 B：一个大前端任务

| 子线 | 负责内容 |
|------|----------|
| layout | 布局壳层与路由 |
| panel | 右栏或对话面板 |
| data | API types、hooks、状态适配 |

前提是三条线不要改同一核心组件。

## 6. 子 Agent 派工要求

主控发任务时，至少要写清：

1. worktree 绝对路径
2. 目标文件范围
3. 明确禁止修改的范围
4. 需要先读哪些设计稿或代码入口
5. 需要跑哪些最小验证
6. 最终汇报格式

推荐汇报格式：

1. 改了什么
2. 改了哪些文件
3. 跑了哪些测试
4. 还剩什么风险

## 7. 主控的日常职责

主控不能只派工然后等结果。至少要做这几件事：

1. 持续更新 task session 的 worktree 台账
2. 记录哪条子线已经开始、哪条已经回补
3. 检查子线有没有越过写集边界
4. 统一审查并回补到主工作树
5. 在主工作树做最终验证

推荐状态流：

`待启动 -> 运行中 -> 已提交补丁 -> 已回补 -> 已验证 -> 已清理`

## 8. 回补顺序

推荐顺序按依赖来：

1. 后端契约
2. prompt / 上下文协议
3. 前端接入
4. 统一测试

不要因为前端先写完，就先合前端。

## 9. 脏树场景下的额外规则

如果主工作树本身已有无关脏改动：

1. 在 task session 里显式记录这些高风险文件
2. 新 worktree 统一从干净提交基线创建
3. 回补时人工核对高风险文件，不直接整包覆盖

至少要记录：

- 哪些目标文件在主工作树已经脏了
- 这些脏改动是不是本轮任务的一部分

## 10. 验证要求

每条子线先做自己的最小验证。

主控最后再做统一验证。

子线验证示例：

- backend：定向 pytest
- prompt：prompt 相关 pytest
- frontend：`npm run build`

主控统一验证示例：

1. backend 定向 pytest
2. frontend build
3. 真实页面 smoke

## 11. 清理规则

只有在下面三个条件都满足时才建议清理：

1. 子线结果已回补主工作树
2. 主控验证已通过
3. 用户没有要求保留 worktree 继续跟进

清理前先把 task session 的状态改成：

- `已回补`
- `已完成`
- `已清理`

然后再执行：

```bash
git worktree remove "/abs/path/to/worktree"
git branch -d "<branch>"
```

如果只是想知道哪些 worktree 能清，不要在这里临时发明流程，直接回到：

- `worktree-audit.md`

## 12. 当前推荐结论

并行 worktree 开发不是“多开几个目录”这么简单。

真正关键的是三件事：

1. 派工前先冻结边界
2. task session 里必须有可追踪台账
3. 主控始终掌握回补顺序和最终验证

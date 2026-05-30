---
name: agent-test-engineer
description: 设计、管理和运行 AIASys Agent 能力测试用例。用于批量验证 Agent 工具的正确性、提示词设计质量、路径处理逻辑和整体任务执行能力。当用户要求新增测试用例、运行 Agent 能力测试、批量验证工具、或发现 Agent 行为异常需要沉淀为回归用例时使用。
---

# Agent 测试工程

AIASys Agent 系统的端到端能力测试。测试用例用接近真实用户输入的问题驱动 Agent 执行，按验收标准判断通过与否，把发现的缺陷反馈到工具设计和提示词改进中。

单靠单元测试无法覆盖"Agent 理解用户意图 → 选择正确工具 → 以正确路径执行"这条完整链路，这些测试用例补上这个缺口。

## 触发条件

- 用户要求新增测试用例
- 用户要求运行 Agent 能力测试
- 用户要求批量验证 Agent 工具
- 发现 Agent 行为异常，需要沉淀为回归用例
- 修改工具定义或提示词后，需要跑回归

## 测试合集位置

用例内容不在本 skill 中维护，统一放在 `design-draft/agent-test-cases/`：

```
design-draft/agent-test-cases/
├── README.md              # 用例索引（全部用例的状态和编号）
└── references/
    ├── test-cases.md      # 综合（跨域测试）
    ├── knowledge-base.md  # 知识库
    ├── knowledge-graph.md # 知识图谱
    ├── canvas.md          # Canvas 画布
    ├── subagent.md        # 子 Agent 调度
    ├── autotask.md        # 自动任务
    ├── python-env.md      # Python 运行时环境
    └── data-analysis.md   # 数据分析
```

**新增用例前先读 `README.md`**，确认归属的功能域和下一个可用编号。

## 用例格式

```markdown
### <编号> <标题>

**问题**：给 Agent 的完整指令

**验收标准**：
1. 可自动化验证的检查项

**常见陷阱**：
- 陷阱 N：描述 + 根因分析

**关联域**：工具/提示词/路径处理/...

**测试记录**：
- YYYY-MM-DD：测试结果和关键发现
```

字段约束：

| 字段 | 约束 |
|------|------|
| 问题 | 可直接发给 Agent 的完整指令，不能包含元指令（"你应该""请确保"） |
| 验收标准 | 每条必须可自动化验证，不接受主观判断 |
| 常见陷阱 | 记录根因（工具设计缺陷/提示词不明确/路径解析错误），用于回归锚点 |
| 测试记录 | 每次实际跑过就追加一行，标注日期和结果 |

## 编号规则

`TC-{域缩写}-{序号}`，三位数字，从 001 开始：

| 域 | 缩写 | 域 | 缩写 |
|----|------|----|------|
| 综合 | INT | Canvas | CV |
| 知识库 | KB | 子 Agent | SA |
| 知识图谱 | KG | 自动任务 | AT |
| Python 环境 | PY | 数据分析 | DA |

## 新增用例工作流

1. 读 `design-draft/agent-test-cases/README.md`，确认归属域和下一个编号
2. 在对应 `references/` 文件中按格式编写用例
3. 更新 `README.md` 索引表
4. 运行该用例，把结果写入"测试记录"
5. 如果暴露新问题，在 `design-draft/bug-discovery/` 下创建 bug 跟踪文档

## 运行测试

当前阶段手动逐条执行。后续会提供 CLI 批量脚本（`scripts/dev/agent-test/run-tests.sh`）。

手动执行步骤：
1. 确认后端服务在 13001 端口运行
2. 选择或创建测试工作区
3. 通过 workspace conversations API 创建绑定 session
4. 向 `/api/agent/execute/stream` 发送问题
5. 收集 SSE 流中的工具调用和结果
6. 按验收标准逐条检查，更新测试记录

## 边界规则

- 用例文件不超过 30 个用例，接近上限时按子域拆分
- 发现 Agent 异常时先确认是否是已知陷阱，新问题补充陷阱并关联 bug 跟踪
- 本 skill 不维护用例内容本身，只维护流程、格式、编号规则。用例内容在 `design-draft/agent-test-cases/`
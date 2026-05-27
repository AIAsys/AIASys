+++
name = "Skill 开发工作台"
description = "创建和优化 AIASys 系统内置 Skill。当用户需要从零创建新 skill、\n改进现有 skill 的 SKILL.md 或脚本、或优化 skill 的 description 触发准确率时使用。\n涵盖 skill 结构设计、编写规范、验证方法和迭代优化流程。\n提供原生开发工具（skill_dev.py、trigger_test.py、improve_desc.py 等），\n支持版本管理、触发测试和自动优化，无需外部 CLI 工具。"
+++


# Skill 开发工作台

创建和优化 AIASys 系统内置 Skill 的完整指南。

## 核心流程

1. 确定 skill 要解决什么问题
2. 写一版草稿
3. 设计测试用例并运行
4. 评估结果（定性 + 定量）
5. 根据反馈重写
6. 重复直到满意
7. 打包最终版本

使用本 skill 时，先判断用户处于流程的哪个阶段，然后帮助他们推进。

---

## 创建 Skill

### 需求确认

先理解用户意图。当前对话中可能已经包含了用户想要固化的工作流。如果是，从对话历史中提取：使用了哪些工具、步骤顺序、用户做了哪些修正、输入/输出格式。

需要明确四个问题：

1. 这个 skill 要让 Agent 做什么？
2. 什么时候应该触发？（用户的哪些表述/上下文）
3. 期望的输出格式是什么？
4. 是否需要设置测试用例？有可客观验证输出的 skill（文件转换、数据提取、代码生成、固定工作流步骤）适合测试用例。输出偏主观的 skill（写作风格、设计）通常不需要。

在这些问题明确之前，不要写 SKILL.md。

### 编写 SKILL.md

基于需求确认的结果，填写以下组件：

- **name**：Skill 标识符（kebab-case，小写字母、数字、连字符）
- **description**：何时触发、做什么。这是主要触发机制，必须同时包含功能描述和触发场景。所有"何时使用"信息都放在这里，不要放到正文。
  - 注意：模型有 undertrigger 倾向（即使场景匹配也可能不用 skill），所以 description 要写得主动一些
  - 示例："当用户提到 X、Y、Z 或需要对任何数据进行可视化时，使用本 skill。"
- **compatibility**：必需的工具、依赖项（可选，很少需要）
- **正文**：使用说明、边界、示例、相关 skill

### 目录结构

```
skill-name/
├── SKILL.md          # 必需入口
│   ├── YAML frontmatter (name, description 必需)
│   └── Markdown instructions
└── scripts/          # 可执行脚本（可选）
```

### 渐进披露

Skill 采用三级加载系统：

1. **Metadata**（name + description）— 始终加载（约 100 字）
2. **SKILL.md 正文** — skill 触发时加载（理想 < 500 行）
3. **scripts/** — 按需执行，不加载内容，只读取用法说明

关键模式：
- SKILL.md 正文控制在 500 行以内；接近上限时增加层级
- 脚本用法在正文中说明参数和示例命令，不要在正文里贴完整代码
- 大段参考文档可在 skill 目录下建 `references/` 目录，正文中指明何时读取

### 安全原则

Skill 不得包含恶意软件、漏洞利用代码或任何可能危害系统安全的内容。不要配合创建误导性 skill 或旨在促进未授权访问、数据外泄的请求。

### 写作风格

- 指令优先使用祈使语气，避免"你可以"、"建议"等弱化表达
- 解释背后的原因，让模型理解重要性，不要用强制的 ALWAYS/NEVER/MUST
- 利用模型的 theory of mind，让 skill 通用而不是只针对特定例子

### 输出格式

需要固定输出格式时，在正文中明确定义模板。例如：

```markdown
## 输出格式

返回 JSON：

```json
{
  "field1": "说明",
  "field2": "说明"
}
```
```

### 测试用例

写完 skill 草稿后，设计 2-3 个真实测试 prompt。好的测试用例覆盖：

- 典型场景（skill 应该被触发的常见情况）
- 边界场景（用户描述模糊但 skill 仍然适用）
- 负例场景（和 skill 看起来相关但实际不需要触发）

测试用例保存为 JSON：

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "用户的任务描述",
      "expected_output": "预期结果描述",
      "files": []
    }
  ]
}
```

---

## 测试与评估

### 运行测试

把测试工作区放在与 skill 目录同级的位置（如 `/workspace/skill-dev/my-skill/`）。

对每个测试用例，同时运行两组：

- **带 skill**：将 skill 安装到测试工作区，让 Agent 在该工作区中执行测试 prompt
- **不带 skill（baseline）**：在同一工作区不带任何 skill 执行相同的 prompt

### 评分

运行完成后，从两个维度评估：

**定性评估**：
- 输出是否符合预期
- 是否遵循了 skill 中的规则
- 边界情况处理是否得当

**定量评估**：
- 为每个测试用例定义可客观验证的 assertions
- 用脚本检查而不是肉眼判断

### 聚合报告

运行 `scripts/aggregate_benchmark.py` 生成汇总报告：

```bash
python3 scripts/aggregate_benchmark.py <workspace>/iteration-N --skill-name <name>
```

生成 `benchmark.json` 和 `benchmark.md`。

---

## 迭代改进

改进原则：

1. **从反馈中泛化**。Skill 会被调用成千上万次，不要只为测试用例写特殊处理
2. **保持精简**。删除没有实际作用的内容
3. **解释"为什么"**。不要用强制的 ALWAYS/NEVER，解释原因让模型理解
4. **把重复工作提取成脚本**。如果多个测试中 Agent 都独立写了相似的 helper，这个逻辑应该放入 `scripts/`

改进后：
1. 应用改进到 skill
2. 在新的迭代目录重新运行所有测试（包括 baseline）
3. 对比新旧版本，分析差异
4. 重复直到用户满意、反馈为空、或没有实质进展

---

## 开发工作台

AIASys 提供原生开发工具 `scripts/skill_dev.py`，支持版本管理、触发测试和自动优化。

### 初始化

```bash
python3 scripts/skill_dev.py init --name my-skill --workspace /workspace
```

在 `/workspace/skill-dev/my-skill/` 下创建：
- `versions/` — 版本历史
- `evals/` — 测试用例
- `iterations/` — 测试运行输出
- `benchmarks/` — 聚合报告
- `state.json` — 当前状态

### 版本管理

```bash
# 保存当前版本
python3 scripts/skill_dev.py version save \
  --name my-skill --skill-path /path/to/skill --label v1

# 列出所有版本
python3 scripts/skill_dev.py version list --name my-skill

# 检出指定版本
python3 scripts/skill_dev.py version checkout \
  --name my-skill --skill-path /path/to/skill --label v1
```

### Description 优化

SKILL.md frontmatter 的 description 字段是决定是否触发 skill 的主要机制。优化流程：

**Step 1：生成 eval queries**

创建 20 个测试 queries（should-trigger 和 should-not-trigger 混合）：

```json
[
  {"query": "用户 prompt 示例", "should_trigger": true},
  {"query": "另一个 prompt 示例", "should_trigger": false}
]
```

- should-trigger（8-10 个）：覆盖不同措辞，包含用户没有明确说出 skill 名称但明显需要的场景
- should-not-trigger（8-10 个）：最有价值的是"差一点触发"的，共享关键词但实际需要其他东西的场景

**Step 2：运行触发测试**

```bash
python3 scripts/skill_dev.py test trigger \
  --name my-skill \
  --skill-path /path/to/skill \
  --evals /workspace/skill-dev/my-skill/evals/trigger-eval.json \
  --runs-per-query 3 \
  --verbose
```

**Step 3：改进 description**

基于上一步输出的 eval 结果：

```bash
python3 scripts/improve_desc.py \
  --eval-results <eval-results-json> \
  --skill-path /path/to/skill \
  --verbose
```

底层调用 LLM 生成改进后的 description。

环境变量：
- `AIASYS_LLM_API_KEY` 或 `OPENAI_API_KEY`
- `AIASYS_LLM_BASE_URL` 或 `OPENAI_BASE_URL`（可选）
- `AIASYS_LLM_MODEL`（默认 deepseek-chat）

**Step 4：应用结果**

取最优 description 更新 SKILL.md frontmatter，展示前后对比并报告分数。

### 快速验证

```bash
python3 scripts/quick_validate.py /path/to/skill-folder
```

检查 frontmatter 完整性、description 长度、是否有"何时使用"说明等基础项。

### 打包

```bash
python3 scripts/package_skill.py /path/to/skill-folder [output-directory]
```

打包为 .zip 用于外部分享。AIASys 内部安装时直接复制目录即可。

---

## 部署说明

### 新增 builtin Skill

1. 在 `apps/backend/skills/builtin/<skill_name>/` 下创建目录
2. 至少放入 `SKILL.md`
3. 可选放入 `scripts/`、`references/`、`assets/`
4. 重启后端或等待开发环境热重载
5. Skill 市场会把它视为系统目录条目

### 验证清单

- [ ] frontmatter 的 `name` 和 `description` 完整且清晰
- [ ] description 同时说明了"做什么"和"何时用"
- [ ] 有明确的"何时使用"和"何时不使用"章节
- [ ] 核心规则有具体示例支撑
- [ ] 脚本用法有完整的参数说明和示例命令
- [ ] 输出格式已定义（如果需要固定输出）
- [ ] 相关 skills 已列出，避免职责重叠
- [ ] SKILL.md 正文 < 500 行；超过时把细节移入 references/
- [ ] 没有引用系统不存在的工具或 API
- [ ] 使用祈使语气，没有"你可以"、"建议"等弱化表达

---

## 参考文件

`agents/` 目录包含给专用子 agent 的指令：
- `agents/grader.md` — 如何评估 assertion 对输出的匹配度
- `agents/comparator.md` — 如何做 A/B 对比
- `agents/analyzer.md` — 如何分析为什么一个版本胜过另一个

`references/` 目录包含补充文档：
- `references/schemas.md` — evals.json、grading.json 等 JSON 结构定义

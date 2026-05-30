---
name: terminology-guardian
description: |
  术语规范与禁用词检查 Skill。
  在写作、改稿、内容整理、技术文档撰写、公众号文章生产等任何涉及文字输出的任务前触发。
  用于统一术语标准、避免禁用词、规范中英文混排。
---

# terminology-guardian

术语规范库与禁用词清单的统一管理入口。

---

## 定位

本 Skill 负责在 AI 生成任何中文内容前，执行术语一致性检查和禁用词拦截。
目标是让输出符合「筱可内容体系」的用词标准，减少人工返工。

---

## 触发条件

以下场景**必须**先读本 Skill：
- 撰写或修改文章、笔记、README、规范文档
- 整理转录稿、提炼概念、写项目产出
- 回复涉及专业术语的技术问题
- 任何用户明确提到"规范用词""检查术语""避免禁用词"的场景

---

## 使用流程

生成任何中文内容前，按以下顺序执行：

### 第一步：查禁用词
读 [references/banned-words.md](references/banned-words.md)，确保输出中不含：
- 商业黑话（赋能、抓手、闭环、对齐、落地、痛点、底层逻辑等）
- 学生气表达（小伙伴们、干货、种草、划重点等）
- AI 味表达（值得注意的是、首先其次最后、综上所述等）
- 模糊形容词（非常、很、特别、比较、一定程度上）

### 第二步：定术语等级
判断文中出现的术语属于哪一级，按规则处理：

| 等级 | 定义 | 处理方式 | 示例 |
|------|------|---------|------|
| T0 通用 | 直译后通顺 | 不加英文 | 概念、发展、方法 |
| T1 专业 | 专业但中文已通用 | 不加英文 | 大模型、微调、智能体、机器学习 |
| T2 小众 | 翻译不统一或需精确 | 首次可注英文，后续不用 | LoRA（Low-Rank Adaptation） |
| T3 标准 | 行业缩写，已成标准符号 | 保留英文 | API、URL、HTML、JSON、CSS、HTTP |

**判断标准**：删除英文后，如果中文句子依然完整、清晰、无歧义，则不应加英文。

### 第三步：查专业术语
遇到不确定的术语时，按领域查对应的 references 文件：
- AI 相关 → [references/ai-model-terms.md](references/ai-model-terms.md)
- 编程工程 → [references/programming-terms.md](references/programming-terms.md)
- 产品商业 → [references/product-business-terms.md](references/product-business-terms.md)
- 写作表达 → [references/writing-terms.md](references/writing-terms.md)
- 筱可专属 → [references/xiaoke-terms.md](references/xiaoke-terms.md)

### 第四步：特殊检查
如果内容涉及以下原创概念，必须使用标准表述：
- **上下文工程**（禁用：提示工程、语境设计）
- **渐进式开发**（禁用：敏捷开发、小步快跑）
- **笨代码**（禁用：傻瓜代码、简单代码）
- **认知落差**（禁用：反差、差距）
- **命名权**（禁用：命名权力、定义权）

---

## 参考文件索引

| 文件 | 内容 |
|------|------|
| [index.md](references/index.md) | 词汇库总览与快速查询 |
| [ai-model-terms.md](references/ai-model-terms.md) | 大模型、智能体、RAG、提示词等术语 |
| [programming-terms.md](references/programming-terms.md) | 渐进式开发、上下文工程、脚手架、端到端等 |
| [product-business-terms.md](references/product-business-terms.md) | PMF、用户旅程、留存、变现、网络效应等 |
| [writing-terms.md](references/writing-terms.md) | 钩子、叙事弧、信息密度、认知落差、社交货币等 |
| [xiaoke-terms.md](references/xiaoke-terms.md) | 筱可专属概念与身份定位标准 |
| [banned-words.md](references/banned-words.md) | 全场景禁用词与替代方案 |

---

## 更新流程

发现新术语不一致或禁用词漏网时：
1. 记录到对应 references 文件
2. 标注「待确认」状态
3. 用户确认后移除待确认标记
4. 重大变更需同步更新 [index.md](references/index.md)

+++
name = "AIASys Canvas 编辑"
description = "AIASys 内置 Canvas 编辑能力。操作 JSON Canvas 格式的 .canvas 文件。\n当用户需要创建或修改思维导图、流程图、白板笔记、概念图等可视化结构时使用。\n避免手动处理 JSON、UUID 生成和边一致性，并在编辑后校验 Canvas 语法。"
+++


# AIASys Canvas 编辑 Skill

操作 JSON Canvas 格式的 `.canvas` 文件。AIASys 只依赖核心字段，未知扩展字段只做透传，不把研究状态写成通用 Canvas 能力。

运行时如果已经有 Agent 工具面，优先使用 `ReadCanvas`、`WriteCanvas`、`BatchCanvasOperations` 读写和批量修改 `.canvas` 文件。这个 skill 继续提供脚本化编辑、命令行批处理和格式说明；工具面不可用时再使用下方脚本。

这是 AIASys 内置特殊 skill。使用前如果当前工作区没有启用它，先调用 `EnableSkill(skill_name="aiasys-canvas-skill")`，再读取或执行脚本。

## 何时使用此 skill

- 用户说"画一个思维导图"、"做个流程图"、"整理成概念图"
- 需要把文本内容转化为可视化的节点-边结构
- 需要读取已有的 .canvas 文件并修改内容

## 何时不应使用

- 需要复杂图形绘制（箭头、图标、自定义形状），这不是 Canvas 的强项
- 需要导出为图片或 PDF，Canvas 是 JSON 格式，需另行转换
- 只需要纯文本列表或表格，直接用 Markdown

## 核心规则

### 规则 1：始终通过脚本操作，不要手写 JSON

`.canvas` 文件的节点和边有严格的 ID 关联。直接手写 JSON 容易破坏一致性。普通增删改用 `scripts/modify.py`。

### 规则 2：编辑后必须校验

每次创建、覆盖或修改 `.canvas` 后，都必须运行 `scripts/validate.py`。校验通过才算完成。校验失败时先修 Canvas，不要继续执行依赖这个视图的后续任务。

### 规则 3：节点类型选择

| 类型 | 用途 | 示例 |
|------|------|------|
| `text` | 普通文本节点 | 概念、标题、说明 |
| `file` | 引用文件 | 链接到另一个 .md 或 .canvas |
| `link` | 外部链接 | URL 跳转 |
| `group` | 分组容器 | 把多个节点框在一起 |

默认使用 `text` 类型。只有当用户明确要求引用外部文件时才用 `file`。

file 节点可以带 `subpath`，用于记录文件内部位置，例如 Markdown 标题 `#结论`。

### 规则 4：边的 fromNode 和 toNode 必须有效

添加边时，`fromNode` 和 `toNode` 必须是已存在的节点 ID。脚本会自动处理 UUID 生成和关联，不要手动构造边对象。

### 规则 5：布局要有意义

- 相关节点在物理位置上靠近
- 从左到右或从上到下表示流程/层级
- 留出足够间距（建议节点间至少 200px），避免重叠

## JSON Canvas 格式简介

Obsidian Canvas 的核心结构：

```json
{
  "nodes": [
    {
      "id": "uuid",
      "type": "text",
      "text": "节点内容",
      "x": 100,
      "y": 200,
      "width": 250,
      "height": 60
    }
  ],
  "edges": [
    {
      "id": "uuid",
      "fromNode": "source-uuid",
      "fromSide": "right",
      "toNode": "target-uuid",
      "toSide": "left",
      "label": "关系说明"
    }
  ]
}
```

节点方向：`top`、`right`、`bottom`、`left`。

## 脚本

| 脚本 | 功能 |
|------|------|
| `read.py` | 读取 .canvas 文件，返回完整 JSON |
| `write.py` | 完整覆盖写入 .canvas 文件 |
| `modify.py` | 低层修改（add_node/update_node/remove_node/add_edge/update_edge/remove_edge） |
| `validate.py` | 校验 JSON 语法、节点结构、重复 ID、边引用和扩展字段形状 |

## 使用方式

```bash
# 读取
python3 skills/builtin/aiasys-canvas-skill/scripts/read.py --file /workspace/my-board.canvas

# 校验
python3 skills/builtin/aiasys-canvas-skill/scripts/validate.py --file /workspace/my-board.canvas

# 写入（覆盖）
python3 skills/builtin/aiasys-canvas-skill/scripts/write.py \
  --file /workspace/my-board.canvas \
  --json '{"nodes":[],"edges":[]}'

# 添加文本节点
python3 skills/builtin/aiasys-canvas-skill/scripts/modify.py \
  --file /workspace/my-board.canvas \
  --action add_node \
  --text "新节点" \
  --x 100 --y 200 \
  --width 250 --height 60

# 添加 file 节点并定位到文件内部位置
python3 skills/builtin/aiasys-canvas-skill/scripts/modify.py \
  --file /workspace/my-board.canvas \
  --action add_node \
  --node_type file \
  --file_path notes/report.md \
  --subpath "#结论" \
  --x 420 --y 200 \
  --width 300 --height 154

# 添加节点间的边
python3 skills/builtin/aiasys-canvas-skill/scripts/modify.py \
  --file /workspace/my-board.canvas \
  --action add_edge \
  --from_node <source-id> \
  --to_node <target-id> \
  --from_side right \
  --to_side left \
  --label "依赖于"

# 更新节点文本
python3 skills/builtin/aiasys-canvas-skill/scripts/modify.py \
  --file /workspace/my-board.canvas \
  --action update_node \
  --node_id <node-id> \
  --text "更新后的内容"

# 删除节点（自动清理关联的边）
python3 skills/builtin/aiasys-canvas-skill/scripts/modify.py \
  --file /workspace/my-board.canvas \
  --action remove_node \
  --node_id <node-id>
```

## 典型工作流

**创建思维导图：**
1. 先 `write.py` 创建一个空的 canvas 文件
2. 用 `modify.py add_node` 添加中心主题节点
3. 继续添加子主题节点
4. 用 `modify.py add_edge` 连接父子节点

**修改现有 canvas：**
1. `read.py` 读取当前内容
2. 分析节点和边结构
3. 低层字段修改用 `modify.py`
4. `validate.py` 校验 JSON Canvas 语法和引用一致性

## 错误处理

| 问题 | 原因 | 解决 |
|------|------|------|
| add_edge 失败 | fromNode/toNode 不存在 | 先确认节点已存在，或用 read.py 检查 |
| 节点重叠 | x/y 坐标太近 | 增大间距，建议相邻节点差 200px 以上 |
| JSON 解析错误 | 文件损坏或手动编辑过 | 用 validate.py 定位语法错误，必要时重建 |
| 边引用失效 | 删除节点后边没清理，或手写了错误 ID | 用 modify.py 删除节点或边，再 validate |

## 相关 Skills

- `pymupdf4llm-pdf-to-markdown-skill` — 如需把 Canvas 内容导出为文档

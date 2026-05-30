# AskUser 工具使用说明

## 概述

AskUser 工具让 Agent 向用户发起结构化问题，暂停执行并等待用户响应。支持单选、多选、文本输入三种模式。

## 何时使用

- 需要用户在多个选项中做出选择
- 需要用户提供额外信息
- 需要用户确认某个操作（如删除、重写等）
- 遇到歧义需要用户澄清

## 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | string | 是 | 问题标题，简洁明了 |
| `message` | string | 是 | 完整问题文本，以 ? 结尾 |
| `options` | list[QuestionOption] | 否 | 选项列表，2-4 个 |
| `multi_select` | boolean | 否 | 是否允许多选，默认 false |
| `body` | string | 否 | 选项上方展示的 Markdown 上下文 |
| `placeholder` | string | 否 | 输入框提示文字（仅无选项时） |
| `default_value` | string | 否 | 默认值 |
| `timeout` | integer | 否 | 超时秒数，默认 300，最大 600 |

## QuestionOption

```json
{
  "label": "方案 A (Recommended)",
  "description": "使用 Redis 缓存，性能最优但需要额外依赖"
}
```

- `label`：显示文本，1-5 words，推荐项加 "(Recommended)"
- `description`：选项含义和权衡说明

## 类型推断

工具根据参数自动推断类型：
- 有 `options` 且 `multi_select=false` → `select`（单选）
- 有 `options` 且 `multi_select=true` → `multi_select`（多选）
- 无 `options` → `input`（文本输入）

**不要自己传 `type` 字段。**

## 使用示例

### 单选

```json
{
  "title": "缓存方案选择",
  "message": "选择数据库查询缓存方案？",
  "options": [
    {"label": "Redis (Recommended)", "description": "内存缓存，高性能，需要 Redis 服务"},
    {"label": "内存缓存", "description": "进程内缓存，无需外部依赖但容量有限"},
    {"label": "不缓存", "description": "每次查询数据库，最简单"}
  ]
}
```

### 多选

```json
{
  "title": "需要安装的依赖",
  "message": "选择需要安装的 Python 包？",
  "options": [
    {"label": "requests", "description": "HTTP 客户端"},
    {"label": "pandas", "description": "数据处理"},
    {"label": "numpy", "description": "数值计算"}
  ],
  "multi_select": true
}
```

### 文本输入

```json
{
  "title": "文件路径",
  "message": "请提供需要读取的文件路径？",
  "placeholder": "/home/user/data.csv"
}
```

## 返回值

成功时返回：
```json
{
  "answers": {
    "选择数据库查询缓存方案？": "Redis (Recommended)"
  }
}
```

用户跳过时返回：
```json
{
  "answers": {},
  "note": "用户跳过了问题"
}
```

超时时返回：
```json
{
  "answers": {},
  "note": "等待用户响应超时（300秒）"
}
```

## 注意事项

1. 不要自己添加 "Other" 选项，系统会自动追加
2. 选项标签保持简洁（1-5 words）
3. 选项数量控制在 2-4 个，太多会降低用户体验
4. `timeout` 最大 600 秒，超时后返回空答案
5. 工具会阻塞 Agent 执行直到用户响应或超时

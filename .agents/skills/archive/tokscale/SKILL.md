---
name: tokscale
description: |
  Tokscale CLI 工具，追踪多个 AI 编码助手的 token 使用量和费用。
  支持 Claude Code、Codex CLI、Kimi CLI、Cursor、Gemini CLI、OpenCode 等 20+ 平台。
  当用户想查看 token 消耗统计、费用估算、各模型/客户端用量分布时使用。
  当前安装路径：/home/ke/projects/AIASys/.local/tokscale/node_modules/.bin/tokscale
---

# Tokscale CLI 使用指南

## 概述

Tokscale 从各 AI 编码工具的本地 session 数据目录读取 token 记录，聚合后展示按模型、客户端、时间维度的使用统计，并用 LiteLLM 定价数据估算费用。

本机支持的客户端（根据本地数据目录自动检测）：Codex CLI、Claude Code、Kimi CLI。

## 安装

```bash
mkdir -p /home/ke/projects/AIASys/.local/tokscale
cd /home/ke/projects/AIASys/.local/tokscale
npm init -y
npm install @tokscale/cli
```

可执行文件路径：`/home/ke/projects/AIASys/.local/tokscale/node_modules/.bin/tokscale`

## 常用命令

### 查看 token 使用报告（表格模式）

```bash
# 最近 7 天（默认）
tokscale --light --week

# 今天
tokscale --light --today

# 本月
tokscale --light --month

# 指定日期范围
tokscale --light --since 2026-05-01 --until 2026-05-26

# 按客户端过滤
tokscale --light --week -c claude -c kimi

# JSON 输出（便于脚本处理）
tokscale --json --week
```

### 交互式 TUI 模式

```bash
tokscale tui                 # 默认 7 天
tokscale tui --week          # 最近 7 天
tokscale tui --month         # 本月
tokscale tui -c codex         # 只看 Codex
```

TUI 有 6 个视图：Overview、Models、Daily、Hourly、Stats、Agents，支持键盘/鼠标导航。

### 查看特定维度的报告

```bash
tokscale models --week       # 按模型统计
tokscale monthly              # 月度趋势
tokscale hourly               # 小时分布
tokscale clients              # 各客户端本地数据扫描情况
```

### 费用查询

```bash
tokscale pricing claude-opus-4-5   # 查询特定模型定价
```

### 导出数据

```bash
tokscale graph --week > usage.json   # 导出贡献图数据
tokscale --json --week > stats.json  # JSON 格式统计
```

### Wrapped 年度回顾

```bash
tokscale wrapped --year 2025   # 生成年度总结 PNG
```

### 社交功能（需 GitHub 登录）

```bash
tokscale login                # 浏览器打开 GitHub OAuth
tokscale submit               # 上传数据到全球排行榜
tokscale whoami               # 查看当前登录用户
```

## 输出解读

`--light` 模式输出按模型分组的表格，只展示 Input/Output/Cost。但 JSON 模式可以拿到完整四维 token 数据，推荐用 JSON 模式做详细统计。

### Token 维度说明

| 维度 | JSON 字段 | 说明 |
|------|-----------|------|
| Input | `input` | 普通输入 token |
| Output | `output` | 输出 token |
| Cache Read | `cacheRead` | 缓存命中读取的 token（计费折扣，通常远低于 input 单价） |
| Cache Write | `cacheWrite` | 写入缓存的 token |
| Total | input+output+cacheRead+cacheWrite | 四者之和 |

### 推荐输出格式

查询 token 用量时，统一用以下格式展示（区分 input/output/cache，避免混在一起）：

```
Client | Model | Messages | Input | Output | Cache Read | Cache Write | Total | Cost
```

示例脚本：

```bash
tokscale --json --week | python3 -c "
import json, sys
data = json.load(sys.stdin)
for e in data['entries']:
    total = e['input'] + e['output'] + e['cacheRead'] + e['cacheWrite']
    print(f\"{e['client']:8s} | {e['model']:20s} | msg={e['messageCount']:>6,} | in={e['input']:>12,} | out={e['output']:>10,} | cr={e['cacheRead']:>14,} | cw={e['cacheWrite']:>10,} | total={total:>14,} | \${e['cost']:,.2f}\")
"
```

费用为估算值，基于 LiteLLM 公开定价，未对 cache_read 做折扣计算（实际费用应低于估算值）。

## 数据来源

Tokscale 从以下本地目录读取 session 数据：

| 客户端 | 数据目录 |
|--------|----------|
| Claude Code | `~/.claude/projects/` |
| Codex CLI | `~/.codex/sessions/` |
| Kimi CLI | Kimi 内部 session 目录 |
| Cursor IDE | API 同步缓存 `~/.config/tokscale/cursor-cache/` |
| Gemini CLI | `~/.gemini/tmp/*/chats/` |
| OpenCode | `~/.local/share/opencode/storage/message/` |

## 已知限制

### Kimi CLI 模型识别

Tokscale 对 Kimi CLI 的 session 数据解析有局限：Kimi CLI 下所有调用都被标为 `kimi-for-coding`、provider 为 `moonshot`。如果用户在 Kimi CLI 中配置了其他模型（如 step 系列），tokscale 无法拆分，会混在一起统计。

### Cache 计费

cache_read 的量通常很大（可能占总 token 的 90%+），但 tokscale 的费用估算未对 cache_read 做折扣（如 Anthropic cache read 仅为 input 价格的 10%），实际费用应低于估算值。

## 注意事项

- 首次运行可能需要较长时间扫描本地数据目录，建议用 `--week` 等时间过滤缩小范围
- `--light` 模式输出 ANSI 颜色码，在非终端环境显示为转义序列，用 `--json` 替代
- 费用为估算值，基于 LiteLLM 公开定价，不含折扣、免费额度等
- 定价缓存 1 小时后过期，自动刷新
- 输出时统一用 JSON 模式解析，按 Input/Output/Cache Read/Cache Write/Total 分列展示
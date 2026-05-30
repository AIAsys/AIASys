---
name: mcp-testing
description: |
  Compatibility alias for MCP validation requests inside the AIASys repo.
  Use when the user explicitly asks to test an MCP server, debug MCP connections,
  or verify MCP tool availability; immediately load `aiasys-resource-verification`
  as the canonical resource-validation skill and, if needed, read
  `aiasys-resource-verification/references/mcp-server-testing.md` for Layer 1 / Layer 2 MCP checks.
---

# mcp-testing

`aiasys-resource-verification` is now the canonical MCP/resource validation skill in this repo.

This alias remains for prompts like:

- “测一下这个 MCP server”
- “排查 MCP 连不通”
- “验证 MCP 工具调用”

## 加载顺序

1. 先读取 `../aiasys-resource-verification/SKILL.md`
2. 如果任务是 MCP 专项验证，再读取：
   - `../aiasys-resource-verification/references/mcp-server-testing.md`
3. 若任务实际是 AIASys 工作区资源验活，则继续走 canonical skill 的统一资源验证流程

## alias 规则

- 不要在这里继续维护第二份 MCP 测试主流程
- 在 AIASys 里，“MCP 可用”默认仍要回到 `已挂载 + 可连接 + 可执行`
- 新的 MCP 验证规则优先补到 canonical skill 或其 references

**注意**: 这是 compatibility alias，不再单独演化。

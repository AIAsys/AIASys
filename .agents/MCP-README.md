# 仓库内 MCP 说明

仓库内如果需要保留 MCP 相关文件，统一放到 `.agents/`，不再把它们放在仓库根目录。

## 当前文件约定

- `.agents/mcp.local.json`
  - 本机私有 MCP 配置
  - 已加入 `.gitignore`
  - 适合临时保存当前机器要用的 server / token

- `.agents/mcp.example.json`
  - 可提交的脱敏模板
  - 作为共享示例和复制起点

## 为什么不放根目录

- 根目录 `.mcp.json` / `.mcp.example.json` 很容易被误认为是 AIASys 主线运行时入口。
- 当前 AIASys 前后端主线并不会直接消费这两份仓库文件。
- 把仓库共享层收进 `.agents/`，能把“项目内约定”与“本机客户端真实生效配置”分开。

## 作用边界

- 这里只规范 AIASys 仓库内的落位。
- 不会自动改动你本机 `~/.codex/config.toml`、`~/.kimi/mcp.json` 之类的全局配置。
- 如果某个外部客户端必须读取根目录 `.mcp.json`，那属于客户端兼容问题，需要单独做软链或同步，不把根目录重新当成仓库正式入口。

## 浏览器自动化补充

仓库内原先的浏览器 MCP 模板已经退役，浏览器自动化统一改走 Playwright CLI：

```bash
cd apps/web
npm run playwright:cli -- --help
```

对应配置文件仍然是：

- `.playwright/cli.config.json`

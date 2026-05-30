---
name: browser-control
description: |
  浏览器控制与前端验证。用于 AIASys 项目的页面验证、截图取证、交互验收和 UI 回归排查。
  触发场景：用户说"打开前端看看效果""帮我测一下这个弹窗""做一次真实浏览器验证""截图看看""验证一下 UI"等。
---

# Browser Control

通过当前运行时提供的浏览器控制能力（如 Kimi WebBridge、Playwright 等），操作真实浏览器进行前端验证。

## 前置条件

1. 确认浏览器控制 daemon/工具已安装且运行正常
2. 确认 AIASys 前端服务可访问（默认 `http://127.0.0.1:13000`）

```bash
curl -fsSL http://127.0.0.1:13000/health 2>/dev/null || echo "前端未启动"
```

## AIASys 关键路由

| 路由 | 说明 |
|---|---|
| `http://127.0.0.1:13000/workspace` | 数据分析主页面（工作区 + 对话） |
| `http://127.0.0.1:13000/health` | 健康检查 |

## 核心工作流

```
health check → navigate → 读取页面结构 → (交互) → screenshot → 复查
```

1. **导航页面**：打开目标路由，优先用新标签页避免状态污染
2. **读取页面结构**：获取可交互元素引用（如无障碍树、CSS 选择器），用于后续点击/输入
3. **页面交互**：点击元素、输入文本、执行 JS、上传文件等
4. **截图**：全屏或特定元素截图，指定输出路径
5. **复查**：对照检查清单验证截图内容

## 截图分类与存放

| 类型 | 存放路径 | 用途 |
|---|---|---|
| 临时调试 / 评审证据 | `design-draft/archive/artifacts/<name>.png` | 本地过程产物，不提交 |
| 正式展示图 | `images/<scope>/<name>.png` | 需要提交到仓库 |

## 验证检查清单

截图后必须复查：

- [ ] 是否裁切（关键按钮/文字是否完整）
- [ ] 字体是否发虚
- [ ] 卡片/面板是否被遮挡
- [ ] 间距是否异常
- [ ] 是否截到滚动条或过多空白
- [ ] 文案是否停在加载中间态

如果不合格，修正后重截。

## AIASys 专项验证场景

### 场景 1：右侧栏布局验证

1. 打开 `http://127.0.0.1:13000/workspace`
2. 等待工作区加载完成（确认 TopBar 和右侧 Dock 出现）
3. 截图到 `design-draft/archive/artifacts/dock-layout.png`
4. 检查要点：
   - TopBar 右上角应有环境按钮（Python/Docker 模式标签）
   - DockHeader 应有压缩、工具配置、新建对话、关闭按钮
   - InputArea 底部工具栏应有：附件按钮、模型选择器、停止按钮、发送按钮
   - 无重叠、无错位

### 场景 2：工作区文件树 + 画布

1. 打开 `http://127.0.0.1:13000/workspace`
2. 展开文件树，点击一个文件
3. 截图到 `design-draft/archive/artifacts/workspace-canvas.png`

### 场景 3：模型选择器下拉

1. 打开右侧栏输入区
2. 点击模型选择器
3. 截图下拉菜单，检查下拉是否正常渲染

## 已知限制

- 严格检查 `event.isTrusted` 的站点（银行、验证码）会拒绝自动化操作
- 跨域 iframe 内的元素无法直接操作，需导航到 iframe URL
- 文本输入可能是 clear-and-insert 模式，追加文本需先读再写
- 截图可能有大小上限，超过需降低分辨率或分页

## 关联文档

- `testing-strategy`：Playwright E2E 测试的正式规范，本 skill 侧重快速截图验证
- `bug-discovery`：验证发现 UI 异常后的 bug 提报和修复流程
- `frontend-pattern`：前端开发规范，理解页面结构时参考
- `DESIGN.md`：视觉设计基线，判断 UI 是否正确的参照标准
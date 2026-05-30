---
name: testing-strategy
description: |
  AIASys 的测试策略与编写规范。覆盖后端 pytest 异步测试模式、测试隔离、前端 Playwright E2E、
  以及测试编写的最佳实践。用于编写新测试、修复测试失败、或扩展测试覆盖时。
---

# 测试策略

AIASys 使用 pytest + pytest-asyncio 作为后端测试框架，Playwright 作为前端 E2E 测试工具。

---

## 后端测试

### 测试框架

- **pytest** + **pytest-asyncio**（`asyncio_mode = "auto"`）
- 配置在 `apps/backend/pyproject.toml`
- 153 个测试文件覆盖几乎所有核心模块

### 测试隔离

`apps/backend/tests/conftest.py` 自动配置隔离环境：

- 每个测试使用独立的 SQLite 数据库（临时目录下的 `aiasys-pytest-*.db`）
- 测试结束后自动清理临时文件
- 不依赖外部 PostgreSQL 或其他服务

### 测试命名规范

- 文件命名：`test_{module}.py`，与源模块一一对应
- 函数命名：`test_{功能描述}`
- 异步测试用 `@pytest.mark.asyncio` 标记

### 测试模式

```python
# 异步 API 测试
@pytest.mark.asyncio
async def test_create_workspace(client):
    response = await client.post("/api/workspaces", json={"name": "test"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test"

# 服务层单元测试
@pytest.mark.asyncio
async def test_mcp_config_merge():
    manager = MCPManager()
    result = await manager.merge_configs(system, user, workspace)
    assert len(result.servers) == 3
```

### 关键测试原则

- **隔离**：每个测试独立，不依赖其他测试的状态
- **不依赖外部服务**：数据库用 SQLite 替代，不连接真实 MCP server
- **覆盖核心路径**：正常流程 + 错误处理 + 边界条件
- **测试文件与源文件一一对应**：便于定位和维护

---

## 前端 E2E 测试

### Playwright 配置

`apps/web/e2e/` 目录：

- 使用 Playwright 进行浏览器自动化测试
- 当前 28 个 spec 文件，覆盖 terminal tab、workspace 操作、文件预览、流式渲染、AutoTask 等关键流程
- `lifecycle/` 子目录存放生命周期相关测试

### E2E 测试模式

```typescript
// 页面加载验证
test('terminal tab renders correctly', async ({ page }) => {
  await page.goto('http://127.0.0.1:13000/workspace');
  await page.click('[data-testid="terminal-tab"]');
  await expect(page.locator('.terminal-container')).toBeVisible();
});
```

---

## 测试运行命令

```bash
# 后端全部测试（Linux/macOS）
cd apps/backend
.venv/bin/python -m pytest

# 后端全部测试（Windows CMD）
cd apps/backend
.venv\Scripts\python -m pytest

# 后端全部测试（全平台通用，推荐）
cd apps/backend
uv run pytest

# 后端单个模块测试 [Lin/Mac]
.venv/bin/python -m pytest tests/test_mcp.py -v

# 后端单个模块测试 [Win]
.venv\Scripts\python -m pytest tests/test_mcp.py -v

# 后端单个测试函数 [Lin/Mac]
.venv/bin/python -m pytest tests/test_mcp.py::test_config_merge -v

# 后端单个测试函数 [Win]
.venv\Scripts\python -m pytest tests/test_mcp.py::test_config_merge -v

# 前端 E2E（需要先运行 npx playwright install 安装浏览器驱动）
cd apps/web
npx playwright test
```

---

## 编写新测试的检查清单

- [ ] 测试文件放在正确的 `tests/` 子目录中
- [ ] 测试函数命名清晰表达测试意图
- [ ] 异步测试标记 `@pytest.mark.asyncio`
- [ ] 不依赖外部服务（数据库用 SQLite，不连真实 API）
- [ ] 覆盖正常路径和至少一个错误路径
- [ ] 测试可以独立运行，不依赖执行顺序
- [ ] 使用 `conftest.py` 的 fixture 而非自己创建基础设施

---

## 遗留测试判断标准

当测试因 `AttributeError`（模块缺少某属性/类）失败时，按以下流程判断是**修复**还是**删除**：

### 决策步骤

1. **定位被引用对象的当前位置**
   - 用 `grep` 搜索该函数/类在项目中的定义位置
   - 确认它是否被移动到了子模块（如 `sessions.py` → `sessions_models.py`）

2. **确认对应功能是否仍然存活**
   - 检查该函数/类是否仍被路由挂载（`include_router`）、被服务层调用、或被前端引用
   - 查看 git log 确认是「功能删除」还是「模块拆分重构」

3. **判断修复还是删除**

| 情况 | 动作 |
|------|------|
| 功能已删除，且代码中无替代实现 | **删除测试** |
| 功能还在，只是因模块拆分导致导入路径失效 | **修复导入路径** |
| 聚合模块（如 `notebooks.py`）的 docstring 承诺 re-export 但未实现 | **优先修复聚合模块的 re-export**，让统一命名空间生效 |
| 函数签名已完全改变，测试调用方式不匹配 | **删除测试**（或视为需要重写的新测试） |
| 无法确认功能是否仍在使用 | 检查前端路由、API 文档、git 最近修改记录后再决定 |

### 核心原则

- **不要仅因导入报错就删除测试**——先确认被测试的功能是否还活着
- **不要向聚合模块随意添加 re-export**——先确认该模块的 docstring 或设计意图是否承诺了统一命名空间
- **优先修复聚合模块的 re-export** 而非逐个修改所有测试文件的导入路径，尤其是当多个测试/消费者都依赖统一命名空间时

### 示例

```python
# 测试失败：sessions_module.RewriteMessageRequest 不存在
# 排查后发现 RewriteMessageRequest 被移动到了 sessions_models.py
# 且 rewrite_session_from_message API 仍然存活
# → 修复测试导入路径（或修复 sessions.py 的 re-export）

# 测试失败：notebook_route.get_notebook_document 不存在
# 排查后发现函数在 notebooks_core.py 中，notebooks.py 的 docstring 承诺 re-export 但未实现
# → 修复 notebooks.py 的 re-export，让统一命名空间生效
```

---

## 执行边界

### 本 Skill 覆盖

- 后端 pytest 异步测试（单元测试 + API 测试）
- 前端 Playwright E2E 测试
- 测试编写模式和最佳实践

### 不覆盖

- 性能测试/压力测试（参考 `performance-optimization`）
- 安全扫描（参考 `security-hardening`）
- 浏览器截图验证（参考 `browser-control`）
- CI 配置和 pre-commit hook（已在 AGENTS.md 中定义）

### 测试选择决策

| 场景 | 用什么 |
|------|--------|
| 后端函数/类逻辑 | pytest 单元测试 |
| 后端 API 端点 | pytest + httpx AsyncClient |
| Agent Tool 功能 | pytest（参考 `agent-dev` 的测试模板） |
| 前端页面交互流程 | Playwright E2E |
| 前端 UI 布局/视觉 | `browser-control` 截图验证 |
| 数据库模型 | pytest + SQLite（参考 `database-model`） |

---

## 关联文档

- `agent-dev`：Agent Tool 的测试要求和模板
- `api-dev`：API 端点的测试模式
- `database-model`：数据库模型测试的隔离策略
- `browser-control`：前端 UI 的截图验证
- `bug-discovery`：发现 bug 后的测试复现流程
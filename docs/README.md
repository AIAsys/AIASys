# AIASys 文档中心

> 当前版本: v0.3.9

`docs/` 只放新协作者启动、运行和排障时需要先读的文档。产品设计、前端布局、后端对象模型、测试验收基线统一放在 `design-draft/design/`。

如果你只想跑起来，先看 [guides/QUICKSTART.md](./guides/QUICKSTART.md)。如果你要讨论产品和实现设计，先看 [../design-draft/design/README.md](../design-draft/design/README.md)。

## 当前入口

| 位置 | 职责 |
|---|---|
| [guides/QUICKSTART.md](./guides/QUICKSTART.md) | 新协作者快速启动，带界面预览 |
| [guides/SYSTEM_USAGE.md](./guides/SYSTEM_USAGE.md) | 系统使用教程，覆盖全部功能的操作指南 |
| [deployment.md](./deployment.md) | 部署与运行说明 |
| [getting-started.md](./getting-started.md) | 跑起来后怎么使用 `/analysis`，带完整界面截图 |
| [guides/docker-network-configuration.md](./guides/docker-network-configuration.md) | Docker 运行时访问后端 broker 的网络排障 |
| [changelog/](./changelog/) | 历史版本记录 |

`docs/` 内文档如果和 `design-draft/design/` 冲突，先按 `design-draft/design/` 和当前代码判断，再回头修 `docs/`。

## 推荐阅读路径

### 第一次启动

1. [guides/QUICKSTART.md](./guides/QUICKSTART.md)
2. [deployment.md](./deployment.md)
3. [guides/SYSTEM_USAGE.md](./guides/SYSTEM_USAGE.md)

### 启动后出问题

1. 先用 `./dev.sh status` 看前后端是否已经启动
2. 再看 [deployment.md](./deployment.md) 的端口、配置和健康检查
3. Docker 运行时访问数据库 broker 异常时，看 [guides/docker-network-configuration.md](./guides/docker-network-configuration.md)

### 想看设计

1. [../design-draft/design/README.md](../design-draft/design/README.md)
2. [../design-draft/design/frontend/README.md](../design-draft/design/frontend/README.md)
3. [../design-draft/design/backend/README.md](../design-draft/design/backend/README.md)
4. [../DESIGN.md](../DESIGN.md)

## 当前产品口径

AIASys 当前按单机单用户产品设计。核心对象是长期任务工作区，会话是工作区内的一条任务推进线。

`/analysis` 当前主壳按三栏组织：

```text
左侧工作区导航 | 中间主画布 | 右侧当前会话侧栏
```

中间主画布承接工作区对象、资源、能力、资产、数据库查询和各种文件预览。右侧侧栏承接当前会话对话、会话列表和输入区。

## 历史追溯

从 2026-04-12 起，旧 `docs/product/` 和 `docs/implementation-status/` 已整体下沉归档，不再作为当前文档入口。

## 维护约束

1. 当前设计入口统一指向 `design/`。
2. `docs/` 只保留启动、运行、快速上手和必要排障文档。
3. 阶段总结、迁移报告、一次性研究优先下沉到 `design-draft/archive/`。
4. 会影响 Agent 执行的约束应写入 `.agents/skills/` 或 `AGENTS.md`。
5. `.agents/task-sessions/` 是过程记忆，对外主文档层仍在 `docs/` 与 `design/`。

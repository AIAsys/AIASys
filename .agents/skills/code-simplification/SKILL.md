---
name: code-simplification
description: |
  简化代码以提升可读性和可维护性，同时保持行为完全一致。
  在功能已验证通过、但代码过于复杂时使用。适用于深度嵌套、过长函数、命名不清、重复逻辑等场景。
---

# 代码简化

在保持行为完全一致的前提下，通过减少复杂度让代码更易读、易维护、易扩展。

**目标不是减少行数，而是提升理解速度。**

---

## 使用场景

- 功能已验证，但实现显得过于笨重
- 代码审查中遇到可读性或复杂度问题
- 遇到深层嵌套逻辑、过长函数或含义不清的命名
- 需要重构时间压力下写出的代码
- 合并改动后引入了重复或不一致

**不应使用的情况：**

- 代码已经清晰可读
- 尚未理解代码意图
- 性能关键路径，简化版本可能明显更慢
- 模块即将被整体重写

---

## 五大原则

### 1. 精确保持行为

只改变表达方式，不改变行为。所有输入、输出、副作用、错误路径和边界条件必须完全一致。

**每次修改前自问：**

- 对所有输入，输出是否相同？
- 错误行为是否一致？
- 副作用和调用顺序是否保持不变？
- 现有测试是否能原样通过？

### 2. 遵循项目惯例

简化是让代码与项目风格更一致，而非强加个人偏好。修改前先阅读 `AGENTS.md`、邻近代码和现有规范。

### 3. 清晰优于巧妙

显式代码优于需要停顿思考的紧凑代码。

```typescript
// 不清晰：嵌套三元表达式
const label = isNew ? "New" : isUpdated ? "Updated" : isArchived ? "Archived" : "Active";

// 清晰：顺序判断
function getStatusLabel(item: Item): string {
  if (item.isNew) return "New";
  if (item.isUpdated) return "Updated";
  if (item.isArchived) return "Archived";
  return "Active";
}
```

### 4. 保持平衡

警惕过度简化：

- 内联过激进，移除了给概念命名的辅助函数
- 把无关逻辑硬凑到一个函数里
- 为了行数牺牲可读性
- 移除用于扩展性或测试性的合理抽象

### 5. 限定在变更范围

默认只简化最近修改的代码。避免顺手重构无关代码，这会产生噪音和回归风险。

---

## 简化流程

### 步骤 1：先理解再动手（Chesterton's Fence）

看到你不理解的代码时，先弄清它为什么存在，再决定是否有必要移除。

**动手前确认：**

- 这段代码的职责是什么？
- 谁调用它？它调用了谁？
- 边界情况和错误路径有哪些？
- 测试如何定义预期行为？
- 当初为什么这样写？（性能？兼容性？历史原因？）
- 查看 git blame，了解原始上下文

### 步骤 2：识别简化机会

**结构复杂度信号：**

| 模式 | 信号 | 简化方向 |
|------|------|----------|
| 深层嵌套（3+ 层） | 控制流难跟踪 | 提取卫语句或辅助函数 |
| 过长函数（50+ 行） | 职责过多 | 按职责拆分为聚焦函数 |
| 嵌套三元表达式 | 需要心智栈解析 | 改为 if/else 或查找表 |
| 布尔参数标志 | `doThing(true, false, true)` | 改为选项对象或独立函数 |
| 重复条件判断 | 相同 `if` 分散多处 | 提取为命名清晰的谓词函数 |

**命名与可读性信号：**

| 模式 | 信号 | 简化方向 |
|------|------|----------|
| 泛化命名 | `data`, `result`, `temp` | 改为描述内容：`userProfile`, `validationErrors` |
| 缩写命名 | `usr`, `cfg`, `btn` | 使用完整单词（`id`, `url`, `api` 除外） |
| 误导性命名 | `get` 函数却修改状态 | 改为反映实际行为的名字 |
| 注释解释"是什么" | `// increment counter` | 删除注释，让代码自解释 |
| 注释解释"为什么" | `// Retry because API is flaky` | 保留，承载意图 |

**冗余信号：**

| 模式 | 信号 | 简化方向 |
|------|------|----------|
| 重复逻辑 | 相同 5+ 行出现在多处 | 提取为共享函数 |
| 死代码 | 不可达分支、未使用变量 | 确认后移除 |
| 不必要抽象 | 没有增值的包装层 | 直接调用底层函数 |
| 过度设计 | 单策略的策略模式 | 用直接方式替代 |
| 冗余类型断言 | 对已知类型再断言 | 移除 |

### 步骤 3：增量修改

每次只做一处简化，修改后运行测试。

```
1. 做出修改
2. 运行测试套件
3. 通过 -> 提交或继续
4. 失败 -> 撤销并重新考虑
```

**Rule of 500：** 如果重构涉及超过 500 行，优先使用自动化工具（codemod、sed、AST 转换），不要手工修改。

### 步骤 4：验证结果

改完后整体评估：

- 简化版本真的更容易理解吗？
- 是否引入了与项目不一致的新模式？
- diff 是否干净、可审查？
- 同事或审查 agent 会认可这是改进吗？

如果答案是"不"，撤销。

---

## 语言特定示例

### TypeScript / JavaScript

```typescript
// 简化：不必要的 async 包装
// 之前
async function getUser(id: string): Promise<User> {
  return await userService.findById(id);
}
// 之后
function getUser(id: string): Promise<User> {
  return userService.findById(id);
}

// 简化：冗长的条件赋值
// 之前
let displayName: string;
if (user.nickname) {
  displayName = user.nickname;
} else {
  displayName = user.fullName;
}
// 之后
const displayName = user.nickname || user.fullName;

// 简化：手动数组构建
// 之前
const activeUsers: User[] = [];
for (const user of users) {
  if (user.isActive) {
    activeUsers.push(user);
  }
}
// 之后
const activeUsers = users.filter((user) => user.isActive);
```

### Python

```python
# 简化：冗长的字典构建
# 之前
result = {}
for item in items:
    result[item.id] = item.name
# 之后
result = {item.id: item.name for item in items}

# 简化：嵌套条件改为卫语句
# 之前
def process(data):
    if data is not None:
        if data.is_valid():
            if data.has_permission():
                return do_work(data)
            else:
                raise PermissionError("No permission")
        else:
            raise ValueError("Invalid data")
    else:
        raise TypeError("Data is None")

# 之后
def process(data):
    if data is None:
        raise TypeError("Data is None")
    if not data.is_valid():
        raise ValueError("Invalid data")
    if not data.has_permission():
        raise PermissionError("No permission")
    return do_work(data)
```

### React / JSX

```tsx
// 简化：冗长的条件渲染
// 之前
function UserBadge({ user }: Props) {
  if (user.isAdmin) {
    return <Badge variant="admin">Admin</Badge>;
  } else {
    return <Badge variant="default">User</Badge>;
  }
}

// 之后
function UserBadge({ user }: Props) {
  const variant = user.isAdmin ? "admin" : "default";
  const label = user.isAdmin ? "Admin" : "User";
  return <Badge variant={variant}>{label}</Badge>;
}
```

---

## 常见借口与反驳

| 借口 | 反驳 |
|------|------|
| "能跑就行，没必要动" | 难读的代码在出问题时更难修，现在简化是为未来节省时间 |
| "行数越少越简单" | 一行的嵌套三元并不比五行的 if/else 简单，理解速度才是关键 |
| "顺手把旁边的也重构了" | 范围外重构产生噪音 diff 和回归风险，保持专注 |
| "类型已经自解释了" | 类型解释结构，命名解释意图，两者互补 |
| "这个抽象以后可能有用" | 没有当下价值的抽象就是复杂度，需要时再添加 |
| "原作者肯定有原因" | 检查 git blame 和应用 Chesterton's Fence，但历史累积的复杂度往往没有原因 |
| "我边加功能边重构" | 功能改动和重构分开放，混合改动更难审查、回滚和理解 |

---

## 红旗信号

以下情况说明简化出了问题：

- 需要修改测试才能让测试通过（很可能改了行为）
- 简化后的代码比原来更长更难懂
- 按个人偏好重命名，而非项目惯例
- 以"更干净"为由移除错误处理
- 对不理解的代码进行简化
- 把多处简化打包成一大笔难以审查的提交
- 未经要求重构范围外的代码

---

## 验证清单

完成一次简化后检查：

- [ ] 所有现有测试原样通过
- [ ] 构建成功，无新增警告
- [ ] Linter / 格式化通过
- [ ] 每次简化都是可审查的增量改动
- [ ] diff 干净，无无关混合
- [ ] 代码遵循项目惯例
- [ ] 未移除或削弱错误处理
- [ ] 未遗留死代码
- [ ] 审查者会认可这是净改进

---

注意: 本 Skill 自给自足，不强制依赖 .ai-rules/ 入口。

---

## 文件大小例外

以下文件即使超过 500 行也不应机械拆分（行数为 2026-05 快照，仅作参考）：

| 文件 | 例外原因 |
|------|----------|
| `apps/backend/app/services/capability_registry.py` | 内聚的服务类，所有方法围绕统一能力注册表，拆分会导致循环引用或暴露内部数据结构 |
| `apps/backend/app/models/session.py` | Pydantic 模型定义集，字段和配置高度耦合，拆分会破坏模型间引用关系 |
| `apps/backend/app/api/routes/sessions.py` | Session CRUD route handler 集合，monitor 路由已抽出为 sessions_monitor.py，剩余为核心路由 |
| `apps/web/src/components/layout/WorkspaceSidebar/WorkspaceContextPanel.tsx` | 布局编排组件，核心职责是视图路由和布局骨架，已从 1410 行拆到极限 |

---
name: performance-optimization
description: |
  基于测量的性能优化，避免过早优化和盲目猜测。
  在有性能指标要求、用户反馈卡顿、监控告警、或怀疑引入回归时使用。
---

# 性能优化

**先测量，再优化。**

没有测量数据的优化是猜测，猜测往往导致过早优化——增加了复杂度，却没有改善真正重要的指标。

---

## 使用场景

- 需求文档中有性能指标（加载预算、响应时间 SLA）
- 用户或监控反馈系统变慢
- Core Web Vitals 分数未达标
- 怀疑某次改动引入了性能回归
- 构建处理大数据量或高流量的功能

**不应使用的情况：** 没有证据表明存在性能问题。过早优化增加的复杂度往往比收益更高。

---

## Core Web Vitals 目标

| 指标 | 良好 | 需改进 | 差 |
|------|------|--------|-----|
| **LCP**（最大内容绘制） | <= 2.5s | <= 4.0s | > 4.0s |
| **INP**（交互到下次绘制） | <= 200ms | <= 500ms | > 500ms |
| **CLS**（累积布局偏移） | <= 0.1 | <= 0.25 | > 0.25 |

---

## 优化工作流

```
1. 测量  -> 用真实数据建立基线
2. 定位  -> 找到真正的瓶颈（不是假设的）
3. 修复  -> 针对具体瓶颈采取措施
4. 验证  -> 再次测量，确认改进
5. 防护  -> 添加监控或测试防止回归
```

### 步骤 1：测量

**前端测量：**

```bash
# Chrome DevTools Performance 面板录制
# Lighthouse（CI 或 DevTools）
# Chrome DevTools MCP 性能追踪
```

```typescript
// web-vitals 库
import { onLCP, onINP, onCLS } from "web-vitals";
onLCP(console.log);
onINP(console.log);
onCLS(console.log);
```

**后端测量：**

```python
import time

start = time.perf_counter()
result = await db.execute(query)
elapsed = (time.perf_counter() - start) * 1000
logger.info(f"Query took {elapsed:.2f}ms")
```

**根据症状决定测量什么：**

| 症状 | 测量方向 |
|------|----------|
| 首屏加载慢 | bundle 大小、TTFB、渲染阻塞资源 |
| 交互卡顿 | 主线程长任务、re-render、布局抖动 |
| 页面切换慢 | API 响应、客户端渲染、瀑布请求 |
| 后端 API 慢 | 数据库查询、连接池、外部依赖 |

### 步骤 2：定位瓶颈

**前端常见瓶颈：**

| 症状 | 可能原因 | 调查方法 |
|------|----------|----------|
| LCP 慢 | 大图、渲染阻塞资源、慢服务端 | 网络瀑布、图片大小 |
| CLS 高 | 无尺寸图片、延迟加载内容、字体切换 | Layout Shift Attribution |
| INP 差 | 主线程 JS 繁重、大 DOM 更新 | Performance trace 长任务 |
| 首载慢 | bundle 大、请求多 | bundle 分析、code splitting |

**后端常见瓶颈：**

| 症状 | 可能原因 | 调查方法 |
|------|----------|----------|
| API 响应慢 | N+1 查询、缺索引、慢 SQL | 数据库查询日志 |
| 内存增长 | 泄漏引用、无界缓存、大 payload | 堆快照分析 |
| CPU 峰值 | 同步重计算、正则回溯 | CPU profiling |
| 延迟高 | 缺缓存、冗余计算、网络跳转 | 请求链路追踪 |

### 步骤 3：修复常见反模式

#### N+1 查询（后端）

```python
# 错误：每个任务查一次 owner
tasks = await db.execute(select(Task))
for task in tasks.scalars():
    task.owner = await db.get(User, task.owner_id)

# 正确：单次 join 查询
result = await db.execute(
    select(Task).options(selectinload(Task.owner))
)
tasks = result.scalars().all()
```

#### 无界数据获取

```python
# 错误：拉取全部记录
all_tasks = await db.execute(select(Task))

# 正确：分页
result = await db.execute(
    select(Task)
    .order_by(Task.created_at.desc())
    .limit(20)
    .offset((page - 1) * 20)
)
```

#### 图片未优化（前端）

```html
<!-- 错误：无尺寸、无懒加载 -->
<img src="/hero.jpg" />

<!-- 正确：响应式、懒加载、有尺寸 -->
<img
  src="/hero.jpg"
  srcset="/hero-400.webp 400w, /hero-800.webp 800w"
  sizes="(max-width: 768px) 100vw, 50vw"
  width="800"
  height="400"
  loading="lazy"
  alt="Hero"
/>
```

#### 不必要的重渲染（React）

```tsx
// 错误：每次渲染创建新对象，导致子组件重渲染
function TaskList() {
  return <TaskFilters options={{ sortBy: "date", order: "desc" }} />;
}

// 正确：稳定引用
const DEFAULT_OPTIONS = { sortBy: "date", order: "desc" } as const;
function TaskList() {
  return <TaskFilters options={DEFAULT_OPTIONS} />;
}

// 昂贵组件使用 React.memo
const TaskItem = React.memo(function TaskItem({ task }: Props) {
  return <div>{/* expensive render */}</div>;
});

// 昂贵计算使用 useMemo
function TaskStats({ tasks }: Props) {
  const stats = useMemo(() => calculateStats(tasks), [tasks]);
  return <div>{stats.completed} / {stats.total}</div>;
}
```

#### 缺少缓存（后端）

```python
# 对读取频繁、变更少的数据加缓存
from functools import lru_cache
import asyncio

_cache = {}
_cache_ttl = {}
CACHE_TTL = 5 * 60  # 5 minutes

async def get_app_config() -> AppConfig:
    now = asyncio.get_event_loop().time()
    if "config" in _cache and now < _cache_ttl.get("config", 0):
        return _cache["config"]
    config = await db.config.find_first()
    _cache["config"] = config
    _cache_ttl["config"] = now + CACHE_TTL
    return config
```

---

## 性能预算

设定预算并在 CI 中强制执行：

| 指标 | 预算 |
|------|------|
| JS bundle（首载） | < 200KB gzip |
| CSS | < 50KB gzip |
| 单张图片（首屏） | < 200KB |
| 字体总计 | < 100KB |
| API p95 响应 | < 200ms |
| Lighthouse Performance | >= 90 |

```bash
# Bundle 大小检查
npx bundlesize --config bundlesize.config.json

# Lighthouse CI
npx lhci autorun
```

---

## 常见借口与反驳

| 借口 | 反驳 |
|------|------|
| "以后再说优化" | 性能债务会累积，明显的反模式现在就要修，微优化可以延后 |
| "我电脑上很快" | 你的机器不是用户的，要在代表性硬件和网络上测试 |
| "这个优化显而易见" | 没有测量就不算知道，先 profile |
| "用户不会在意 100ms" | 研究显示 100ms 延迟会影响转化率，用户比你想象的更敏感 |
| "框架已经处理了性能" | 框架无法修复 N+1 查询或过大的 bundle |

---

## 红旗信号

- 没有测量数据就开始优化
- 后端存在 N+1 查询模式
- 列表接口无分页
- 图片无尺寸、无懒加载、无响应式处理
- bundle 持续增长却无审查
- 生产环境无性能监控
- `React.memo` 和 `useMemo` 到处滥用

---

## 验证清单

任何性能相关改动后检查：

- [ ] 有优化前后的具体测量数据
- [ ] 瓶颈已被确认并针对性处理
- [ ] Core Web Vitals 达到"良好"阈值
- [ ] bundle 大小没有显著增加
- [ ] 新的数据获取代码无 N+1 查询
- [ ] CI 中的性能预算通过（如已配置）
- [ ] 现有测试全部通过（优化未破坏行为）

---

注意: 本 Skill 自给自足，不强制依赖 .ai-rules/ 入口。

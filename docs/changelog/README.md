# Changelog 编写规范

`docs/changelog/` 只回答一个问题：这次版本里，真正交付了哪些代码行为变化。

它不替代：

- `DESIGN.md` 的视觉设计基线
- `archive/docs-legacy-2026-04-12/docs/` 下保留的历史产品 / 实现状态材料

## 记录范围

### 不记录的内容

| 类型 | 说明 |
|---|---|
| 版本号更新 | 如 `package.json`、`config.py` 中仅版本号变化 |
| Docker / 运维操作 | 镜像构建、容器重启、缓存清理等部署动作 |
| 纯文档更新 | `README`、`AGENTS.md`、治理说明等 docs-only 变更 |
| 纯配置调整 | 不改变用户可感知行为的配置项修改 |
| 纯格式整理 | 缩进、换行、注释补充等无行为变化的修改 |
| 仅文件移动/重命名 | 路径变化但内容与行为不变 |

### 需要记录的内容

1. 功能新增
   - 新增 API、页面、组件、模块、工具或运行行为
2. Bug 修复
   - 功能缺陷、接口错误、状态流问题、数据处理错误、安全问题
3. 重构改动
   - 核心逻辑重写、架构调整、接口不兼容修改
4. 性能优化
   - 响应速度、资源占用、并发处理能力的实际改进

## 格式规范

```markdown
# Changelog vX.X.X - YYYY-MM-DD

## 贡献者GitHub用户名

### 功能标题（简短描述）
```

**注意：** 贡献者名称使用当前提交者的 GitHub 用户名，可通过 `git config user.name` 查看。

#### 问题描述（Bug 修复类需要）
- 现象：
- 原因：

#### 改动内容
- 具体修改点 1
- 具体修改点 2

#### 文件变更
- `path/to/file`: 变更说明
```

## 编写要求

1. 标题要能说明用户实际获得了什么变化。
2. Bug 修复类条目要写清楚现象和原因。
3. 文件变更部分只列关键文件，不写流水账。
4. docs-only 改动默认不写进 changelog；如果某份文档更新伴随真实功能修复，应记录功能修复本身，避免只写“更新了文档”。

## 示例

### 好的示例

```markdown
### 修复 Host Final Answer 图片无法显示

#### 问题描述
Host 返回的 final_answer 中 Markdown 图片无法显示。

#### 改动内容
- 在 AiMessageContent 组件中添加 token 获取逻辑
- 将 token 传入 AiMessageMeta

#### 文件变更
- `apps/web/src/components/chat/AiMessageContent/index.tsx`: 添加 token 获取
```

### 不好的示例

```markdown
### 版本更新
- 前端版本：v0.1.3 → v0.1.4
- 后端版本：v0.1.2 → v0.1.3

### Docker 部署
- 重新构建前端和后端镜像
- 更新沙箱镜像配置
- 清理 Vite 缓存
```

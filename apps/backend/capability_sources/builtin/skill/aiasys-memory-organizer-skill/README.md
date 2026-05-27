# Memory 整理器

整理 AIASys Markdown memory 文件。用于压缩 MEMORY.md、刷新 memory_summary.md、合并重复偏好、清理过期工作区记忆。

## 适用场景

- 用户明确要求"整理 memory""压缩 memory"
- MEMORY.md 过长，需要合并重复段落
- memory_summary.md 已过期，需要重新生成
- 工作区 workspace_memory.md 有明显重复或过时内容

## 注意事项

- 只处理文件化 memory，不管理结构化 entry
- 不参与普通 memory 自动写入链路
- 普通写入链路只追加内容，重复内容可以存在

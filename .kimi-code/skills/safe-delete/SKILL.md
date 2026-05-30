---
name: safe-delete
description: |
  安全删除 Skill。用于把文件或文件夹移动到 Windows 回收站，而不是永久删除。
  当用户提到删除、移到回收站、安全删除、可恢复删除、清理临时文件时触发。
  适用于需要保留恢复可能性的删除场景，不适用于归档替代或明确要求永久删除的场景。
---

# Safe Delete

## 定位

把“删除”从危险的永久删除，改成可恢复的回收站删除。

默认判断顺序：

1. 如果是长期材料整理，先判断是否应该归档，而不是删除
2. 如果用户明确要删，但仍希望可恢复，走本 skill
3. 只有用户明确要求永久删除时，才考虑不用回收站

## 核心能力

1. 把文件移到回收站
2. 把文件夹移到回收站
3. 支持通配符批量删除
4. 在 PowerShell 下替代 `Remove-Item` 这类永久删除命令

## 正式入口

- 正式能力包：`.agents/skills/safe-delete/`
- 正式脚本：`.agents/skills/safe-delete/scripts/safe-delete.ps1`
- 开发事实源：`resources/xiaoke-skill-development/safe-delete/scripts/safe-delete.ps1`

## 使用方法

### 场景 1：删除单个文件

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents/skills/safe-delete/scripts/safe-delete.ps1 "old-file.md"
```

### 场景 2：删除文件夹

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents/skills/safe-delete/scripts/safe-delete.ps1 "old-folder"
```

### 场景 3：批量删除临时文件

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents/skills/safe-delete/scripts/safe-delete.ps1 "*.tmp" -Force
```

## 决策边界

### 优先归档，不直接删

下面这些情况，优先移动到 `Archives/` 或其他长期目录：

- 历史笔记
- 旧项目资料
- 仍可能复用的研究文档
- 用户只是说“整理掉”“先收掉”但没有明确说删除

### 适合安全删除

- 临时文件
- 重复导出文件
- 明确废弃的中间产物
- 用户明确说“删掉”，但没有要求永久删除

### 不适合本 skill

- 用户明确要求永久删除
- 非 Windows 环境
- 需要做跨目录归档或搬运，而不是删除

## 输出要求

执行前应说明：

- 将使用回收站删除，而不是永久删除
- 如果是归档更合适，要先指出这一点

执行后应说明：

- 实际删除了哪些路径
- 是否有失败项
- 结果可从回收站恢复

## 注意事项

- 这是 Windows 专用能力
- 默认不要用 `Remove-Item` 代替它
- 如果路径有歧义，先核对路径再执行

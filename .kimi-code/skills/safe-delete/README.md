# `safe-delete`

这个 skill 是安全删除的正式入口。

## 作用

- 把文件移动到回收站
- 把文件夹移动到回收站
- 避免把本应可恢复的删除动作写成永久删除

## 正式入口

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .agents/skills/safe-delete/scripts/safe-delete.ps1 "old-file.md"
```

## 开发事实源

- `resources/xiaoke-skill-development/safe-delete/`

## 正式能力包

- `.agents/skills/safe-delete/`

# Skill 管理模块

当前 `app/skills/` 是 AIASys 后端里的运行时 Skill 包管理层。

它负责三件事：

- 枚举系统目录中的 builtin Skill 包
- 管理当前工作区已经安装/导入的 Skill 包
- 为运行时和 API 提供统一的 Skill 包发现结果

## 当前真实目录

```text
apps/backend/
├── skills/builtin/                              # 运行时 builtin Skill 目录
│   └── <skill_name>/
│       └── SKILL.md
├── app/skills/                                  # Skill 管理模块
│   ├── __init__.py
│   ├── manager.py
│   ├── models.py
│   └── README.md
└── data/workspaces/{user_id}/{workspace_id}/
    └── .aiasys/skills/                          # 当前工作区实际启用的 Skill 包副本
        └── <skill_name>/
            └── SKILL.md
```

需要特别区分：

- `apps/backend/skills/builtin/` 是用户运行时可安装的 builtin Skill 目录

## 当前运行时语义

- Skill 市场展示的是全局仓库条目和当前工作区已启用的 Skill 包
- 启用 builtin Skill 的结果是把目录包复制到当前工作区的 `.aiasys/skills/`
- zip 导入先进入全局用户仓库，再按工作区启用语义复制到 `.aiasys/skills/`
- 运行时读取当前工作区和全局工作区的 `.aiasys/skills/` 目录
- Skill 变更采用 next-run-only 语义：保存后对下一次执行或手动重置运行态生效

## 核心接口

### 发现系统目录

```python
from app.skills import get_skill_manager

skill_mgr = get_skill_manager()
store_skills = skill_mgr.list_store_skills()
```

### 列出当前工作区 Skill

```python
from pathlib import Path

workspace_path = Path("/path/to/data/workspaces/<user_id>/<workspace_id>")
workspace_skills = skill_mgr.list_workspace_skills(workspace_path)
```

### 启用系统目录 Skill 到工作区

```python
result = skill_mgr.enable_skill(
    "demo-skill",
    workspace_path,
    force=False,
)
```

### 导入 zip Skill 包到工作区

```python
result = skill_mgr.import_skill_archive(
    workspace_path=workspace_path,
    filename="demo-skill.zip",
    content=zip_bytes,
    force=False,
)
```

### 删除工作区 Skill

```python
result = skill_mgr.remove_workspace_skill("demo-skill", workspace_path)
```

### 读取工作区 Skill 入口

```python
result = skill_mgr.get_workspace_skill_entry_content(
    workspace_path=workspace_path,
    skill_name="demo-skill",
)
```

## 目录包要求

每个 Skill 包至少需要有一个可识别的 `SKILL.md` 入口文件。

```text
skill-name/
├── SKILL.md
├── scripts/
├── references/
├── templates/
└── assets/
```

其中：

- `SKILL.md` 是必需入口
- 其他目录都是可选扩展
- 包内部不要求固定模板，只要求能识别入口

## API 概览

当前主线工作区 Skill API 在：

- `GET /api/skills/store`
- `POST /api/skills/store/import`
- `DELETE /api/skills/store/{skill_name}`
- `GET /api/skills/global`
- `POST /api/skills/global/enable`
- `POST /api/skills/global/disable`
- `GET /api/skills/workspaces/{workspace_id}`
- `POST /api/skills/workspaces/{workspace_id}/enable`
- `POST /api/skills/workspaces/{workspace_id}/disable`
- `GET /api/skills/workspaces/{workspace_id}/{skill_name}/entry`
- `DELETE /api/skills/workspaces/{workspace_id}/{skill_name}`

对应实现见：

- [skills.py](./../api/routes/skills.py)
- [manager.py](./manager.py)

## 新增 builtin Skill

如果要新增一个可在 Skill 市场中安装的 runtime builtin Skill：

1. 在 `apps/backend/skills/builtin/<skill_name>/` 下创建目录
2. 至少放入一个 `SKILL.md`
3. 重启后端或等待开发环境热重载
4. Skill 市场会把它视为系统目录条目

示例：

```bash
mkdir -p apps/backend/skills/builtin/my-skill
cat > apps/backend/skills/builtin/my-skill/SKILL.md <<'EOF'
---
name: my-skill
description: 面向工作区运行时的 builtin Skill 示例
---

# My Skill
EOF
```

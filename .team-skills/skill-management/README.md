# Skill 体系管理规范

本文件描述 pkm-hub 和项目仓库的 Skill 体系管理策略。面向规则维护者和开发者。

## 总体架构

采用**四层分区 + 项目联邦**架构。

### 四层分区

| 层级 | 路径 | 角色 |
|---|---|---|
| 通用开发区 | `resources/xiaoke-skill-development/` | 通用 Skill 唯一迭代区 |
| 项目开发区 | `resources/xiaoke-project-skill/<project>/skill-development/` | 项目专属 Skill 迭代区 |
| 正式区 | `resources/xiaoke-skill-development/skills/` | AI 正式读取入口 |
| 活跃区 | `.kimi/skills/` | AI 活跃读取镜像 |

### 项目联邦

有独立仓库的项目（如 AIASys），运行时区 `resources/xiaoke-skill-development/skills/` 从 pkm-hub 单向同步。

## 目录结构

### 通用 Skill

```
resources/xiaoke-skill-development/
├── _templates/
├── <通用-skill>/
│   ├── SKILL.md
│   ├── README.md
│   ├── release.manifest.json
│   ├── scripts/
│   └── references/
└── xiaoke-skills/          # 第三方收集库
```

### 项目专属 Skill

```
resources/xiaoke-project-skill/
├── README.md
└── <project>/
    ├── AGENTS.md
    ├── skill-development/
    └── skills/
```

## 边界决策

| 通用 Skill | 项目专属 Skill |
|---|---|
| 跨项目复用 | 仅特定项目 |
| 无技术栈依赖 | 强技术栈依赖 |
| 不加前缀 | 建议加项目前缀 |

## 已归档 Skill

归档 Skill 保留在开发区做历史记录，但从正式区删除防止 AI 误触。

当前已归档：directory-standards、domain-learning、ebook-manager、entry-manager、inbox-triage、knowledge-cards、media-capture、para-manager、playwright-cli、resource-curator、rule-evolution、task-persistence。

## 漂移检测

三区域不一致时的处理优先级：
1. 正式区超前 → 回同步到开发区
2. 开发区孤儿 → 评估后发布或归档
3. 正式区幽灵 → 回同步到开发区
4. 活跃区漂移 → 从正式区重新同步

## 维护责任

- AGENTS.md 导航表由规则维护者统一管理
- 新增/变更 Skill 必须同步更新导航
- 每季度至少做一次三区域一致性检查

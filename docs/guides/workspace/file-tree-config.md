# 文件树配置

工作区的文件树可以通过 `.aiasys/file-tree-config.json` 配置文件定制。该文件在创建工作区时自动生成，包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `hidden_patterns` | `string[]` | 文件树中隐藏的文件/目录匹配规则，支持 glob 通配符 |
| `internal_root_files` | `string[]` | 工作区根目录下的内部文件，不在文件树中显示 |
| `internal_session_dirs` | `string[]` | 会话目录中被视为内部结构的子目录名 |
| `internal_session_files` | `string[]` | 会话目录中被视为内部结构的文件名 |
| `blocked_subdirs` | `string[]` | 禁止 Agent 进入的子目录路径 |
| `editable_extensions` | `string[]` | 允许在线编辑的文件扩展名列表 |

## hidden_patterns 匹配规则

每条规则使用 glob 语法，按工作区相对路径匹配：

- `.aiasys/session` — 精确匹配该路径
- `.aiasys/session/**` — 匹配该目录下所有内容
- `**/__aiasys_folder__.md` — 匹配任意深度的标记文件
- `*-shm` / `*-wal` — 匹配根目录下的 SQLite 临时文件

匹配任一规则的文件或目录会在文件树中隐藏，不会展示给用户和 Agent。

## internal_root_files

工作区根目录下的文件名列表（如 `metadata.json`、`file_snapshots.json`），这些文件不在文件树中展示。

## internal_session_dirs 与 internal_session_files

控制会话目录（`session/`）下哪些内容被视为内部结构，不在文件列表中显示给用户。

## blocked_subdirs

禁止 Agent 进入的子目录路径列表。Agent 的文件操作工具不会访问这些路径下的内容。

## editable_extensions

控制文件树中哪些文件可以双击打开在线编辑。默认覆盖常见文本格式（`.md`、`.json`、`.yaml`、`.py`、`.js`、`.html` 等）。如需支持其他格式，在此列表中添加对应扩展名。

## 配置示例

```json
{
  "_schema_version": 1,
  "hidden_patterns": [
    ".aiasys/session",
    ".aiasys/session/**",
    ".aiasys/file-history/**",
    "**/__aiasys_folder__.md",
    "*-shm",
    "*-wal"
  ],
  "internal_root_files": [
    ".cleanup_marker",
    "metadata.json"
  ],
  "internal_session_dirs": [
    ".aiasys",
    ".env"
  ],
  "internal_session_files": [
    ".cleanup_marker",
    "metadata.json"
  ],
  "blocked_subdirs": [
    ".aiasys/session",
    ".aiasys/.memory"
  ],
  "editable_extensions": [
    ".md",
    ".json",
    ".yaml",
    ".py",
    ".js",
    ".html",
    ".css"
  ]
}
```

修改配置后，刷新文件树即可看到效果。删除该文件后，系统使用内置默认值运行，不会报错。
# 文件实时监听与前端联动设计文档

Agent 执行过程中实时推送文件变化到前端，并实现前端预览自动刷新。

---

## 概述

在 Agent 执行任务时（如生成图表、写入报告），前端需要实时看到文件变化。本方案通过 SSE 在工具调用后检测并推送文件变更，前端根据变更类型自动或手动刷新预览。

```
Agent 执行工具
    ↓
工具完成
    ↓
扫描工作目录
    ↓
对比文件快照
    ↓
SSE 推送变更
    ↓
前端更新文件树/预览
```

---

## 核心机制

### 1. 文件变化检测（后端）

**触发时机**：每次工具调用完成后检测

**对比方式**：文件路径 + 修改时间 (mtime)

**代码实现**：`app/utils/file_utils.py`

```python
async def scan_directory(workspace: Path) -> Dict[str, FileSnapshot]:
    """扫描目录生成文件快照"""

async def compare_files(before, after, workspace) -> List[dict]:
    """对比快照检测新增/修改/删除"""
```

### 2. SSE 推送（后端）

**实现位置**：`app/services/agent_service.py:352-359`

```python
# 工具调用完成后检测文件变化
if isinstance(msg, ToolResult) and files_before is not None:
    files_after = await scan_directory(workspace_path)
    changes = compare_files(files_before, files_after, workspace_path)
    if changes:
        yield {"type": "file_changes", "changes": changes}
```

**事件格式**：

```json
{
  "type": "file_changes",
  "changes": [
    {
      "path": "report.md",
      "event": "modified",
      "size": 1024,
      "modified": 1707830400.0,
      "is_text": true,
      "has_content": true,
      "content": "# 报告内容..."
    },
    {
      "path": "chart.png",
      "event": "created",
      "size": 15432,
      "modified": 1707830400.0,
      "is_text": false,
      "has_content": false
    }
  ]
}
```

### 3. 文件事件类型

| event | 说明 | 前端行为 |
|-------|------|---------|
| `created` | 新文件创建 | 添加到文件树，如果是小文本直接显示 |
| `modified` | 文件修改 | 更新内容或显示"已修改"标记 |
| `deleted` | 文件删除 | 从文件树移除，关闭预览 |

---

## 前端联动机制

### 1. 增量更新文件树

前端收到 `file_changes` 事件后，**只更新变化的文件**，不重新请求整个文件列表：

```typescript
function handleFileChange(event: FileChangeEvent) {
  // 乐观更新：直接修改本地状态
  updateFileInTree(event);
  
  // 如果当前正在预览的文件被修改
  if (selectedFile?.path === event.path) {
    handlePreviewRefresh(event);
  }
}
```

### 2. 预览刷新策略

| 文件类型 | 刷新策略 | 原因 |
|---------|---------|------|
| **图片** (png/jpg/svg) | **自动刷新** | 加时间戳强制重载，即时可见 |
| **代码/文本** | **自动刷新** (小文件) | 直接推送内容，无缝更新 |
| **CSV** | **提示刷新** | 可能正在查看，避免打断 |
| **Excel** | **提示刷新** | 数据量大，避免卡顿 |
| **Notebook** | **提示刷新** | 可能正在编辑 |

### 3. 图片自动刷新实现

```typescript
function ImagePreview({ file }: { file: PreviewFile }) {
  const [timestamp, setTimestamp] = useState(Date.now());
  
  // 监听文件变化
  useFileChange(file.path, () => {
    setTimestamp(Date.now());  // 加时间戳强制刷新
  });
  
  return <img src={`${file.url}?t=${timestamp}`} />;
}
```

### 4. 手动刷新提示实现

```typescript
function CodePreview({ file, onReadContent }) {
  const [content, setContent] = useState('');
  const [hasUpdate, setHasUpdate] = useState(false);
  
  useFileChange(file.path, (event) => {
    if (event.type === 'modified') {
      setHasUpdate(true);  // 显示"文件已更新，点击刷新"提示
    }
  });
  
  const handleRefresh = async () => {
    const newContent = await onReadContent(file.path);
    setContent(newContent);
    setHasUpdate(false);
  };
  
  return (
    <div>
      {hasUpdate && (
        <button onClick={handleRefresh}>
          文件已更新，点击刷新
        </button>
      )}
      <pre>{content}</pre>
    </div>
  );
}
```

---

## 推送策略

### 内容推送规则

| 文件类型 | 大小 | 行为 |
|---------|------|------|
| 文本文件 | < 100KB | SSE 直接推送内容 |
| 文本文件 | ≥ 100KB | 只推送元数据，前端按需加载 |
| 二进制文件 | 任意 | 只推送元数据，前端通过 URL 访问 |

### 文本文件判断

```python
TEXT_EXTENSIONS = {
    '.txt', '.md', '.py', '.js', '.ts', '.jsx', '.tsx',
    '.json', '.yaml', '.yml', '.csv', '.html', '.css',
    '.scss', '.less', '.xml', '.ini', '.conf', '.sh',
    '.bash', '.zsh', '.sql', '.log'
}

def is_text_file(path: str) -> bool:
    return Path(path).suffix.lower() in TEXT_EXTENSIONS
```

---

## 历史回顾时的文件状态

### 问题

历史回顾时需要看到当时的文件树状态，但文件可能已经变化或被删除。

### 方案：视图快照（已实现）

**视图快照** - 只记录文件名列表（不保存内容），依附于消息流：

```
workspaces/{user_id}/{session_id}/
├── file_snapshots.json          # 工具调用前后的文件快照
├── history.json                 # 消息历史
└── workspace/                   # 实际文件
```

**快照格式**：

```json
[
  {
    "timestamp": "2024-01-15T10:30:00",
    "files": ["data.csv"],
    "context": "before_tool:call_123"
  },
  {
    "timestamp": "2024-01-15T10:30:05", 
    "files": ["data.csv", "chart.png"],
    "context": "after_tool:call_123"
  }
]
```

**特点**：
-  零存储成本（文件内容仍在 workspace）
-  实现简单（每次工具调用前后自动保存）
-  足够满足"当时有哪些文件"的需求

**优点**：
- 空间占用小（只存元数据）
- 可回溯任意时间点的文件树
- 前端可以对比展示（如：执行步骤3后新增了哪些文件）

---

## 性能考虑

1. **扫描频率**：仅在工具调用后扫描，非持续轮询
2. **内容大小限制**：超过 100KB 的文本文件不推送内容
3. **批量推送**：一次工具调用可能有多个文件变化，合并为一个 SSE 事件
4. **增量更新**：前端只更新变更的文件，不刷新整个文件树

---

## 安全考虑

1. **路径校验**：确保文件在工作目录内，防止路径遍历
2. **权限检查**：只推送当前用户有权限访问的文件
3. **大小限制**：防止超大文件导致内存问题

---

## 实现状态

- [x] `app/utils/file_utils.py` - 文件扫描和对比工具
- [x] `app/services/agent_service.py` - Agent 执行流中插入文件检测
- [x] `app/api/routes/files.py` - 文件读取 API
- [x] 前端 `FilePreviewPanel` - 文件预览面板（支持图片/CSV/Excel/Notebook/代码）
- [x] 前端 `WorkspaceArtifacts` - 工作区文件树
- [x] `app/services/session_manager.py` - 视图快照保存/查询
- [x] `GET /api/sessions/{user_id}/{session_id}/file-snapshots` - 文件快照 API
- [ ] 前端增量更新优化
- [ ] 前端历史回顾时显示文件快照

---

## 参考实现

### 后端 API

```
GET /api/files/{user_id}/{session_id}/list
获取文件列表（用于初始化或手动刷新）

GET /api/files/{user_id}/{session_id}/content?path=xxx
获取文件内容（用于预览加载）

POST /api/agent/execute/stream
SSE 流，包含 file_changes 事件

GET /api/sessions/{user_id}/{session_id}/file-snapshots
获取文件快照历史（视图快照）

Response:
{
  "snapshots": [
    {
      "timestamp": "2024-01-15T10:30:00",
      "files": ["data.csv"],
      "context": "before_tool:call_123"
    },
    {
      "timestamp": "2024-01-15T10:30:05",
      "files": ["data.csv", "chart.png"],
      "context": "after_tool:call_123"
    }
  ]
}
```

### 前端 Hook

```typescript
// useWorkspaceFiles.ts
export function useWorkspaceFiles(userId: string, sessionId: string) {
  const [files, setFiles] = useState<FileState[]>([]);
  
  // 初始加载
  useEffect(() => {
    fetchFiles().then(setFiles);
  }, []);
  
  // 监听 SSE 增量更新
  useSSE('file_changes', (event) => {
    setFiles(prev => updateFilesIncrementally(prev, event.changes));
  });
  
  return files;
}
```

---

## 测试

启动服务后，执行 Agent 任务时会自动推送文件变更事件：

```bash
curl -X POST http://localhost:13001/api/agent/execute/stream \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a file named hello.txt with content Hello World",
    "session_id": "test-session"
  }'
```

预期输出包含：
```
data: {"type": "file_changes", "changes": [{"path": "hello.txt", "event": "created", ...}]}
```

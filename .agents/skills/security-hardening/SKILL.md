---
name: security-hardening
description: |
  在开发中建立安全优先意识，对涉及用户输入、认证授权、数据存储、外部集成的代码进行安全加固。
  适用于构建 API、前端表单、文件上传、第三方对接等任何接触不可信数据的场景。
---

# 安全加固

安全不是独立阶段，而是每一行涉及用户数据、认证、外部系统的代码都必须遵守的约束。

**默认立场：所有外部输入都是敌意的，所有密钥都是神圣的，所有权限检查都是强制的。**

---

## 使用场景

- 构建接受用户输入的功能
- 实现认证或授权逻辑
- 存储或传输敏感数据
- 集成外部 API 或服务
- 添加文件上传、Webhook、回调处理
- 处理支付信息或个人身份信息（PII）

---

## 三层边界系统

### 必须做（无例外）

- 在系统边界验证所有外部输入（API 路由、表单处理器）
- 对所有数据库查询使用参数化，禁止拼接用户输入到 SQL
- 对输出进行编码以防止 XSS（使用框架自动转义，不要绕过）
- 所有外部通信使用 HTTPS
- 密码使用 bcrypt / scrypt / argon2 哈希，禁止明文存储
- 配置安全响应头（CSP、HSTS、X-Frame-Options、X-Content-Type-Options）
- 会话 Cookie 使用 httpOnly、secure、sameSite
- 发布前运行依赖安全审计（`npm audit` 或等效工具）

### 必须先询问（需要人类确认）

- 新增或修改认证流程
- 存储新的敏感数据类别（PII、支付信息）
- 新增外部服务集成
- 修改 CORS 配置
- 添加文件上传处理
- 修改限流或节流策略
- 授予提升权限或角色

### 禁止做

- 禁止将密钥提交到版本控制（API key、密码、token）
- 禁止在日志中记录敏感数据（密码、token、完整信用卡号）
- 禁止将客户端校验作为唯一安全边界
- 禁止为图方便禁用安全响应头
- 禁止对用户提供的数据使用 `eval()` 或 `innerHTML`
- 禁止将认证 token 存储在客户端可访问位置（如 localStorage）
- 禁止向用户暴露堆栈跟踪或内部错误细节

---

## OWASP Top 10 防护

### 1. 注入攻击（SQL、NoSQL、命令）

```python
# 错误：字符串拼接导致 SQL 注入
query = f"SELECT * FROM users WHERE id = '{user_id}'"

# 正确：参数化查询
user = await db.execute(text("SELECT * FROM users WHERE id = :id"), {"id": user_id})

# 正确：使用 ORM
user = await db.get(User, user_id)
```

### 2. 失效认证

```python
# 密码哈希
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hashed = pwd_context.hash(plaintext)
is_valid = pwd_context.verify(plaintext, hashed)

# FastAPI 会话安全设置
response.set_cookie(
    key="session_id",
    value=session_token,
    httponly=True,
    secure=True,
    samesite="lax",
    max_age=24 * 60 * 60,
)
```

### 3. 跨站脚本（XSS）

```tsx
// 错误：直接渲染用户输入为 HTML
element.innerHTML = userInput;

// 正确：React 默认转义
return <div>{userInput}</div>;

// 如果必须渲染 HTML，先消毒
import DOMPurify from "dompurify";
const clean = DOMPurify.sanitize(userInput);
```

### 4. 失效访问控制

```python
# 每次操作都检查资源归属
@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: UUID, req: TaskUpdate, current_user: User = Depends(get_current_user)):
    task = await task_service.get(task_id)
    if task.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改此任务")
    return await task_service.update(task_id, req)
```

### 5. 安全配置错误

```python
# FastAPI + python-multipart 的安全响应头配置
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # 禁止 *
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

### 6. 敏感数据泄露

```python
# API 响应中排除敏感字段
def to_public_user(user: User) -> dict:
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        # 明确不包含：password_hash, reset_token, internal_notes
    }
```

---

## 输入验证模式

### 边界模式验证（FastAPI / Pydantic）

```python
from pydantic import BaseModel, Field, field_validator

class CreateTaskRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    priority: Literal["low", "medium", "high"] = "medium"

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        return v.strip()

@app.post("/api/tasks")
async def create_task(req: CreateTaskRequest):
    # 到达这里的数据已经过验证和类型转换
    return await task_service.create(req)
```

### 文件上传安全

```python
ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"]
MAX_SIZE = 5 * 1024 * 1024  # 5MB

def validate_upload(file: UploadFile) -> None:
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "不支持的文件类型")
    # 不要信任文件扩展名，必要时检查 magic bytes
```

---

## 密钥管理

```
.env 文件策略：
  .env.example   -> 提交（占位模板）
  .env           -> 不提交（真实密钥）
  .env.local     -> 不提交（本地覆盖）

.gitignore 必须包含：
  .env
  .env.local
  .env.*.local
  *.pem
  *.key
```

**提交前检查：**

```bash
git diff --cached | grep -iE "(password|secret|key|token|api_key)"
```

---

## 依赖漏洞处理

`npm audit` 或 `pip-audit` 结果决策树：

```
发现漏洞
  ├── 严重 / 高危
  │   ├── 代码路径可达？ -> 立即修复
  │   └── 仅开发依赖？   -> 尽快修复，不阻塞发布
  ├── 中等
  │   ├── 生产可达？     -> 下个迭代修复
  │   └── 仅开发？       -> 方便时修复，跟踪在 backlog
  └── 低危
      └── 常规依赖更新时处理
```

延迟修复时必须记录原因和复查日期。

---

## 限流配置

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# 通用 API 限流
@app.get("/api/data")
@limiter.limit("100/minute")
async def get_data():
    ...

# 认证端点更严格
@app.post("/api/auth/login")
@limiter.limit("10/minute")
async def login():
    ...
```

---

## 安全审查清单

### 认证

- [ ] 密码使用 bcrypt / scrypt / argon2 哈希（salt rounds >= 12）
- [ ] 会话 token 使用 httpOnly、secure、sameSite
- [ ] 登录接口有限流
- [ ] 密码重置 token 有过期时间

### 授权

- [ ] 每个受保护端点都校验用户权限
- [ ] 用户只能访问自己的资源
- [ ] 管理员操作需要额外角色校验

### 输入

- [ ] 所有外部输入在边界处验证
- [ ] SQL 查询参数化
- [ ] HTML 输出经过转义或消毒

### 数据

- [ ] 源代码和 git 历史中无密钥
- [ ] 敏感字段不暴露在 API 响应中
- [ ] 如需存储 PII，考虑加密

### 基础设施

- [ ] 配置了安全响应头
- [ ] CORS 限制为已知来源
- [ ] 依赖无严重 / 高危漏洞
- [ ] 错误响应不暴露内部细节

---

## 常见借口与反驳

| 借口 | 反驳 |
|------|------|
| "这是内部工具，安全不重要" | 内部工具同样会被攻破，攻击者会找最弱环节 |
| "以后再加安全" | 事后补安全比构建时嵌入难 10 倍，现在就做 |
| "没人会专门攻击这个" | 自动化扫描器会找到它，安全不靠隐藏 |
| "框架已经处理了安全" | 框架提供工具，但不保证正确使用 |
| "这只是原型" | 原型往往直接变成生产，安全习惯从第一天养成 |

---

## 红旗信号

- 用户输入直接拼接到 SQL、命令或 HTML 中
- 源代码或提交历史中出现密钥
- API 端点缺少认证或授权检查
- CORS 配置为通配符 `*`
- 认证端点无限流
- 向用户暴露堆栈跟踪或内部错误
- 依赖存在已知严重漏洞却未处理

---

## 验证清单

实现涉及安全的代码后检查：

- [ ] 依赖审计无严重 / 高危漏洞
- [ ] 源代码和 git 历史中无密钥
- [ ] 所有用户输入在边界处验证
- [ ] 每个受保护端点都有认证和授权检查
- [ ] 安全响应头已配置（可用浏览器 DevTools 检查）
- [ ] 错误响应不暴露内部细节
- [ ] 认证端点已启用限流

---

注意: 本 Skill 自给自足，不强制依赖 .ai-rules/ 入口。

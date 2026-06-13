# 认证与授权现状

本文档描述当前 `apps/backend` 已实现的认证模型。旧的 `simple + oauth2-proxy + X-User-ID` 组合不再是本仓库默认现实。

## 当前模式

认证配置来自 `apps/backend/config.toml -> auth.mode`，当前代码支持三种模式：

| 模式 | 说明 | 适用场景 |
| --- | --- | --- |
| `local` | 本地用户表 + JWT `access_token` Cookie | 当前默认模式，前后端联调、本地部署 |
| `sso` | 转发 Cookie 给外部 SSO 校验接口 | 外部统一身份系统接入 |
| `none` | 直接注入虚拟开发身份 | 本地测试、无登录联调 |

源码入口：

- `app/core/config.py`
- `app/core/auth.py`
- `app/api/routes/auth.py`

## `local` 模式

`local` 是当前默认认证模式，认证流程如下：

1. 用户通过 `/api/auth/register` 创建本地账号，或通过 `/api/auth/login` 登录。
2. 后端签发 JWT，并写入 `access_token` Cookie。
3. 后续请求通过 `require_auth()` 读取 Cookie，必要时也接受 `Authorization: Bearer <token>`。
4. 后端会优先从数据库读取最新用户资料，避免 JWT 中的旧昵称、手机号等信息长期漂移。

当前本地用户数据默认存放在：

- `apps/backend/data/app.db`

Cookie 现状：

- 名称: `access_token`
- `HttpOnly`: `true`
- `SameSite`: `lax`
- `Secure`: 当前代码仍是 `false`，便于本地开发
- 有效期: 30 天

## `sso` 模式

`sso` 模式不是要求前端自己构造用户 Header，而是由后端读取请求 Cookie 并把它们转发给外部 SSO 校验服务。

当前实现特征：

1. 识别 `authjs.session-token` 或 `next-auth.session-token` 一类 Cookie。
2. 优先尝试解析自定义 session token。
3. 解析失败后，调用 `auth.sso_url` 指向的外部接口做会话校验。
4. 成功时生成 `UserInfo`，失败时返回 401。

默认 SSO 校验地址来自：

- `apps/backend/config.toml -> auth.sso_url`
- 默认值: `http://localhost:3001/api/auth/session`

## `none` 模式

`none` 模式用于开发和测试，不做真实身份校验，会返回一个固定的开发身份：

- `user_id = test_anonymous_dev`
- `role = admin`
- `auth_provider = none`

这意味着：

1. 适合本地跑接口测试和无登录联调。
2. 不适合用于任何生产环境描述。
3. 文档或测试如果写“本地默认无需登录”，必须明确前提是 `auth.mode=none`。

## 当前前端契约

前端与浏览器调用时，应遵循下面这套现行契约：

1. 优先使用 Cookie，会话请求带 `credentials: include`。
2. 不要把 `X-User-ID`、`X-User-Role` 当作正式前端契约继续扩散。
3. 用 `/api/auth/session` 或 `/api/auth/me` 检查登录态。
4. 在 `local` 模式下，资料更新后会刷新 JWT，前端无需自己同步 token 内容。

## 当前可用的认证相关接口

| 路径 | 说明 |
| --- | --- |
| `POST /api/auth/login` | 本地登录并设置 Cookie |
| `POST /api/auth/register` | 本地注册并自动登录 |
| `POST /api/auth/logout` | 清除 Cookie |
| `GET /api/auth/session` | 获取当前会话用户信息 |
| `POST /api/auth/forgot-password` | 本地认证下直接重置密码 |
| `GET /api/auth/me` | 获取当前用户信息 |
| `PUT /api/auth/me` | 更新昵称和手机号，并刷新 JWT |
| `GET /health/auth` | 返回当前认证模式与 CORS 配置 |

`forgot-password` 当前只在 `local` 或 `none` 模式下可用；`sso` 模式会直接拒绝。

## 授权边界

当前权限模型不复杂，但边界已经落地：

1. `require_auth()` 负责认证。
2. `require_role()` 负责角色校验，`admin` 拥有越权访问能力。
3. 资源级越权主要通过 `UserInfo.can_access_user_data()` 控制。
4. 大多数带 `{user_id}` 的路由都要求“本人或管理员”。

这意味着：

- 即使前端传了别人的 `user_id`，后端也会做资源级校验。
- 文档里不应再暗示“只要前端 Header 正确就能代表某个用户”。

## 推荐验证

```bash
cd apps/backend
uv run uvicorn app.main:app --reload --port 13001
```

```bash
curl http://localhost:13001/health/auth
```

```bash
curl -X POST http://localhost:13001/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"secret123","name":"Demo"}'
```

## 需要优先回源码时

以下问题不要只看本文档，要直接回源码确认：

- 为什么某个请求明明带了 Cookie 还是 401
- `sso` 模式到底读取哪些 Cookie
- `none` 模式下测试身份是否会影响权限判断
- `/api/auth/me` 更新后 JWT 为什么刷新

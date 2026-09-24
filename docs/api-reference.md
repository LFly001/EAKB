# EAKB API 参考文档

> 企业知识库智能助手（EAKB）后端接口文档，覆盖 Phase 1–8 已实现并实测通过的全部接口。
> 本文档以 `backend/app/api/v1/` 路由定义与 `backend/app/schemas/` 出入参模型的实际代码为准，
> 所有字段、枚举、错误码均与源码一一对应，未实现的接口一律不收录。

---

## 目录

1. [总览](#1-总览)
2. [系统端点](#2-系统端点)
3. [认证模块 `/api/v1/auth`](#3-认证模块-apiv1auth)
4. [用户管理 `/api/v1/users`（管理员）](#4-用户管理-apiv1users管理员)
5. [知识库分类 `/api/v1/categories`（登录）](#5-知识库分类-apiv1categories登录)
6. [文档管理 `/api/v1/documents`（登录）](#6-文档管理-apiv1documents登录)
7. [提示词模板 `/api/v1/templates`（登录）](#7-提示词模板-apiv1templates登录)
8. [RAG 问答 `/api/v1/rag`（登录）](#8-rag-问答-apiv1rag登录)
9. [SSE 流式问答协议（完整契约）](#9-sse-流式问答协议完整契约)
10. [知识图谱 `/api/v1/graph`](#10-知识图谱-apiv1graph)
11. [管理后台 `/api/v1/admin`（管理员）](#11-管理后台-apiv1admin管理员)
12. [错误码总表](#12-错误码总表)
13. [与 DESIGN.md 的差异说明](#13-与-designmd-的差异说明)

---

## 1. 总览

### 1.1 基础约定

| 项目 | 约定 |
|---|---|
| 基础路径 | `/api/v1`（由环境变量 `API_V1_PREFIX` 配置，默认 `/api/v1`） |
| 数据格式 | 请求/响应均为 JSON（UTF-8）；文件上传为 `multipart/form-data`；流式问答为 SSE（`text/event-stream`） |
| 鉴权方式 | `Authorization: Bearer {access_token}`（JWT），详见 [1.3 鉴权](#13-鉴权) |
| 接口文档 | 调试环境（`DEBUG=true`）下自动开启 Swagger：`/docs`、`/redoc` |
| HTTP 语义 | GET 查询、POST 新增/异步任务/批量操作、PUT 全量更新、DELETE 删除（业务以软删为主） |

### 1.2 统一响应格式

除少数系统端点（见 [第 2 章](#2-系统端点)）外，**所有接口**返回统一结构 `{code, msg, data}`：

**成功示例**

```json
{
  "code": 200,
  "msg": "success",
  "data": { }
}
```

- `code=200` 表示成功；`msg` 为提示文案（多数接口返回具体文案如「登录成功」，缺省为 `success`）。
- 业务失败时 `code` 为五位错误码（如 `40400`），HTTP 状态码与业务码的关系为 `http_status = code / 100`
  （例如业务码 `40400` → HTTP 404）。错误响应体：

```json
{
  "code": 40400,
  "msg": "资源不存在",
  "data": null
}
```

- `data` 在失败时通常为 `null`；`AppException` 携带的 `detail`（如限流的 `retry_after`）会放入 `data`。

### 1.3 鉴权

- **Token 类型**：登录/刷新返回 `access_token`（短期，用于接口鉴权）与 `refresh_token`（长期，默认 7 天，用于续期）。
- **鉴权方式**：请求头 `Authorization: Bearer {access_token}`。
- **豁免端点**（无需 Token）：`POST /api/v1/auth/register`、`POST /api/v1/auth/login`、`POST /api/v1/auth/refresh`、
  `GET /api/v1/ping`、`GET /health`、`GET /`。**其余全部接口必须携带 Token**。
- **角色体系**：`admin`（管理员）/ `employee`（普通员工）。`/api/v1/users/*` 与 `/api/v1/admin/*`、`POST /api/v1/graph/build`
  额外要求 `admin` 角色，普通员工访问返回 `40300`。
- **401 场景**（均返回业务码 `40100`）：未提供凭证、Token 无效或过期、Token 缺少用户标识、用户不存在、账号已被禁用。
- 密码仅存储 bcrypt 哈希，任何接口的响应均不含密码字段。

### 1.4 分页

所有分页列表接口统一使用查询参数 `page` + `page_size`，返回统一的 `PageResponse` 结构：

| 查询参数 | 类型 | 默认 | 约束 | 说明 |
|---|---|---|---|---|
| `page` | int | 1 | `>= 1` | 当前页码（从 1 开始） |
| `page_size` | int | 20 | `1 <= page_size <= 100` | 每页条数 |

分页响应体（嵌套在 `data` 内）：

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "total": 150,
    "page": 1,
    "page_size": 20,
    "pages": 8,
    "items": []
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `total` | int | 总记录数 |
| `page` | int | 当前页码 |
| `page_size` | int | 每页条数 |
| `pages` | int | 总页数（总数为 0 时为 0） |
| `items` | array | 当前页数据列表 |

### 1.5 SSE 流式问答概述

`POST /api/v1/rag/chat-stream` 是唯一的问答接口，以 SSE（Server-Sent Events）流式返回生成结果。
事件序列固定为 `meta → sources → delta* → done`，失败发 `error` 事件；每个事件的 `data` 为 JSON 字符串。
完整协议（事件字段、关键行为、示例）见 [第 9 章](#9-sse-流式问答协议完整契约)。

### 1.6 模块索引

| 模块 | 路径前缀 | 权限 | 章节 |
|---|---|---|---|
| 系统 | `/api/v1/ping`、`/health`、`/` | 公开 | [2](#2-系统端点) |
| 认证 | `/api/v1/auth` | 部分公开 | [3](#3-认证模块-apiv1auth) |
| 用户管理 | `/api/v1/users` | 管理员 | [4](#4-用户管理-apiv1users管理员) |
| 知识库分类 | `/api/v1/categories` | 登录 | [5](#5-知识库分类-apiv1categories登录) |
| 文档管理 | `/api/v1/documents` | 登录 | [6](#6-文档管理-apiv1documents登录) |
| 提示词模板 | `/api/v1/templates` | 登录 | [7](#7-提示词模板-apiv1templates登录) |
| RAG 问答 | `/api/v1/rag` | 登录 | [8](#8-rag-问答-apiv1rag登录) |
| 知识图谱 | `/api/v1/graph` | 登录（构建需管理员） | [10](#10-知识图谱-apiv1graph) |
| 管理后台 | `/api/v1/admin` | 管理员 | [11](#11-管理后台-apiv1admin管理员) |

---

## 2. 系统端点

以下三个端点返回**裸 JSON**（不走 `{code, msg, data}` 包装），且均无需鉴权。

### GET /api/v1/ping — API 连通性测试

| 项目 | 说明 |
|---|---|
| 权限 | 公开 |

**成功响应** `200`

```json
{ "ping": "pong", "version": "v1", "status": "ok" }
```

### GET /health — 健康检查

| 项目 | 说明 |
|---|---|
| 权限 | 公开 |
| 用途 | Kubernetes / Docker 健康检查探针 |

**成功响应** `200`

```json
{ "status": "ok", "app": "EAKB", "env": "development" }
```

`env` 取 `APP_ENV`（development / production）。

### GET / — API 根路径

| 项目 | 说明 |
|---|---|
| 权限 | 公开 |

**成功响应** `200`

```json
{ "app": "EAKB", "version": "1.0.0", "docs": "/docs" }
```

`docs` 字段在生产环境（`DEBUG=false`）为 `"disabled"`。

---

## 3. 认证模块 `/api/v1/auth`

### 3.1 POST /api/v1/auth/register — 用户注册

| 项目 | 说明 |
|---|---|
| 权限 | 公开 |
| Content-Type | `application/json` |
| 说明 | 注册用户默认为 `employee` 角色；注册成功写入操作日志（module=auth, action=register） |

**请求参数**（JSON body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `username` | string | 是 | 用户名（工号），3–50 位，仅允许字母、数字、下划线（`^[a-zA-Z0-9_]+$`） |
| `password` | string | 是 | 密码，6–128 位 |
| `confirm_password` | string | 是 | 确认密码，必须与 `password` 一致 |
| `email` | string | 否 | 邮箱，最长 100 |
| `phone` | string | 否 | 手机号，最长 20 |
| `real_name` | string | 否 | 真实姓名，最长 50 |

```json
{
  "username": "zhangsan",
  "password": "Abc123456",
  "confirm_password": "Abc123456",
  "email": "zhangsan@example.com",
  "phone": "13800000000",
  "real_name": "张三"
}
```

**成功响应** `200`（`data` 为 [UserInfo](#38-用户信息结构-userinfo)）

```json
{
  "code": 200,
  "msg": "注册成功",
  "data": {
    "id": 3,
    "username": "zhangsan",
    "email": "zhangsan@example.com",
    "phone": "13800000000",
    "real_name": "张三",
    "department": null,
    "position": null,
    "avatar_url": null,
    "role": "employee",
    "status": 1,
    "last_login_at": null,
    "created_at": "2026-08-24T10:00:00",
    "updated_at": "2026-08-24T10:00:00"
  }
}
```

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40900 | 409 | 用户名已存在 |
| 42200 | 422 | 参数校验失败：用户名格式/长度不合法、密码长度不足、两次密码不一致、缺少必填字段等 |

### 3.2 POST /api/v1/auth/login — 登录

| 项目 | 说明 |
|---|---|
| 权限 | 公开 |
| Content-Type | `application/json` |
| 说明 | 登录成功更新 `last_login_at`，写入操作日志（action=login） |

**请求参数**（JSON body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `username` | string | 是 | 用户名，最少 1 位 |
| `password` | string | 是 | 密码，最少 1 位 |

```json
{ "username": "admin", "password": "Admin@123456" }
```

**成功响应** `200`

```json
{
  "code": 200,
  "msg": "登录成功",
  "data": {
    "access_token": "eyJhbGciOi...",
    "refresh_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "user": { }
  }
}
```

`data.user` 为 [UserInfo](#38-用户信息结构-userinfo) 结构。后续请求使用
`Authorization: Bearer {access_token}`。

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40100 | 401 | 用户名或密码错误（用户不存在与密码错误提示相同，避免撞库枚举） |
| 40100 | 401 | 账号已被禁用（「账号已被禁用，请联系管理员」） |
| 42200 | 422 | 缺少用户名/密码 |

### 3.3 POST /api/v1/auth/refresh — 刷新 Token

| 项目 | 说明 |
|---|---|
| 权限 | 公开 |
| Content-Type | `application/json` |
| 说明 | 用 refresh_token 换取**新的** access_token + refresh_token（旧 refresh token 随之作废） |

**请求参数**（JSON body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `refresh_token` | string | 是 | 登录时下发的 refresh token，最少 1 位 |

```json
{ "refresh_token": "eyJhbGciOi..." }
```

**成功响应** `200`

```json
{
  "code": 200,
  "msg": "Token 刷新成功",
  "data": {
    "access_token": "eyJhbGciOi...",
    "refresh_token": "eyJhbGciOi...",
    "token_type": "bearer"
  }
}
```

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40100 | 401 | Refresh Token 无效或已过期、缺少用户标识、用户不存在或已禁用 |
| 42200 | 422 | 缺少 `refresh_token` 字段 |

### 3.4 GET /api/v1/auth/me — 获取当前用户信息

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |

无请求参数。**成功响应** `200`：`data` 为 [UserInfo](#38-用户信息结构-userinfo)。

**错误码**：`40100`（未登录 / Token 无效 / 账号被禁用）。

### 3.5 PUT /api/v1/auth/me — 更新个人信息

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `application/json` |
| 说明 | 仅更新邮箱、手机、姓名三个字段；写入操作日志（action=update_profile） |

**请求参数**（JSON body，全部选填，传 `null` 同样视为未更新）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `email` | string | 否 | 邮箱，最长 100 |
| `phone` | string | 否 | 手机号，最长 20 |
| `real_name` | string | 否 | 真实姓名，最长 50 |

**成功响应** `200`：`data` 为更新后的 [UserInfo](#38-用户信息结构-userinfo)，`msg="个人信息更新成功"`。

**错误码**：`40100`（未登录）、`42200`（字段超长）。

### 3.6 PUT /api/v1/auth/password — 修改密码

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `application/json` |
| 说明 | 需校验旧密码；修改后旧 access token 不主动失效，前端应引导重新登录；写入操作日志（action=change_password） |

**请求参数**（JSON body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `old_password` | string | 是 | 旧密码，最少 1 位 |
| `new_password` | string | 是 | 新密码，6–128 位 |
| `confirm_password` | string | 是 | 确认新密码，必须与 `new_password` 一致 |

**成功响应** `200`（无 data）

```json
{ "code": 200, "msg": "密码修改成功", "data": null }
```

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40000 | 400 | 旧密码错误 |
| 42200 | 422 | 新密码长度不足、两次新密码不一致 |

### 3.7 POST /api/v1/auth/logout — 注销

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |

无请求体。**后端无状态**：仅记录操作日志（action=logout），不做服务端 Token 失效；
前端本地清除 Token 即可。**成功响应** `200`：`{ "code": 200, "msg": "注销成功", "data": null }`。

### 3.8 用户信息结构 UserInfo

所有返回用户信息的接口统一使用该结构（不含任何密码字段）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 用户 ID |
| `username` | string | 用户名 |
| `email` | string\|null | 邮箱 |
| `phone` | string\|null | 手机号 |
| `real_name` | string\|null | 真实姓名 |
| `department` | string\|null | 部门 |
| `position` | string\|null | 职位 |
| `avatar_url` | string\|null | 头像地址 |
| `role` | string | 角色：`admin` / `employee` |
| `status` | int | 状态：1=启用 0=禁用 |
| `last_login_at` | datetime\|null | 最后登录时间 |
| `created_at` | datetime\|null | 创建时间 |
| `updated_at` | datetime\|null | 更新时间 |

---

## 4. 用户管理 `/api/v1/users`（管理员）

> 本模块全部接口要求 `admin` 角色（`40300`），且 `DELETE` 为**物理删除**（慎用）。
> 删除/禁用自己账号的行为被禁止（`40000`）。

### 4.1 POST /api/v1/users/batch — 批量启用/禁用/删除

| 项目 | 说明 |
|---|---|
| 权限 | 管理员 |
| Content-Type | `application/json` |
| 说明 | 一次查询 + 一次提交；不存在的 ID 跳过并在 `skipped_ids` 返回；写入操作日志（action=batch_enable_user / batch_disable_user / batch_delete_user） |

**请求参数**（JSON body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `user_ids` | int[] | 是 | 目标用户 ID 列表，1–100 个（自动去重） |
| `action` | string | 是 | 操作类型：`enable`（启用）/ `disable`（禁用）/ `delete`（删除） |

```json
{ "user_ids": [3, 5, 7], "action": "disable" }
```

**成功响应** `200`

```json
{
  "code": 200,
  "msg": "批量禁用完成: 2 个用户，1 个用户不存在已跳过",
  "data": {
    "count": 2,
    "users": [3, 5],
    "skipped_ids": [7]
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `count` | int | 实际处理的用户数 |
| `users` | int[] | 成功处理的用户 ID 列表 |
| `skipped_ids` | int[] | 不存在的用户 ID 列表 |

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40000 | 400 | `action` 不是 enable/disable/delete；`user_ids` 包含自己的账号 |
| 40300 | 403 | 非管理员访问 |
| 42200 | 422 | `user_ids` 为空或超过 100 个 |

### 4.2 GET /api/v1/users/ — 用户列表

| 项目 | 说明 |
|---|---|
| 权限 | 管理员 |

**查询参数**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20，最大 100 |
| `keyword` | string | 否 | 搜索关键词（匹配用户名/姓名/部门） |
| `role` | string | 否 | 角色过滤：`admin` / `employee` |
| `status` | int | 否 | 状态过滤：1=启用 0=禁用 |

**成功响应** `200`：`data` 为 [PageResponse](#14-分页)，`items` 为 [UserInfo](#38-用户信息结构-userinfo) 列表。

### 4.3 GET /api/v1/users/{user_id} — 用户详情

| 项目 | 说明 |
|---|---|
| 权限 | 管理员 |

**路径参数**：`user_id`（int）。**成功响应** `200`：`data` 为 [UserInfo](#38-用户信息结构-userinfo)。

**错误码**：`40300`（非管理员）、`40400`（用户不存在）。

### 4.4 POST /api/v1/users/ — 创建用户

| 项目 | 说明 |
|---|---|
| 权限 | 管理员 |
| Content-Type | `application/json` |
| 说明 | 写入操作日志（action=create_user） |

**请求参数**（JSON body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `username` | string | 是 | 用户名，3–50 位 |
| `password` | string | 是 | 密码，6–128 位 |
| `email` | string | 否 | 邮箱，最长 100 |
| `phone` | string | 否 | 手机号，最长 20 |
| `real_name` | string | 否 | 真实姓名，最长 50 |
| `department` | string | 否 | 部门，最长 100 |
| `position` | string | 否 | 职位，最长 100 |
| `role` | string | 否 | 角色：`admin` / `employee`，默认 `employee` |
| `status` | int | 否 | 状态：1=启用 0=禁用，默认 1 |

**成功响应** `200`：`data` 为 [UserInfo](#38-用户信息结构-userinfo)，`msg="用户创建成功"`。

**错误码**：`40300`、`40900`（用户名已存在）、`42200`。

### 4.5 PUT /api/v1/users/{user_id} — 更新用户信息

| 项目 | 说明 |
|---|---|
| 权限 | 管理员 |
| Content-Type | `application/json` |
| 说明 | 仅更新传入字段；写入操作日志（action=update_user） |

**请求参数**（JSON body，全部选填）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `email` | string | 否 | 邮箱，最长 100 |
| `phone` | string | 否 | 手机号，最长 20 |
| `real_name` | string | 否 | 真实姓名，最长 50 |
| `department` | string | 否 | 部门，最长 100 |
| `position` | string | 否 | 职位，最长 100 |
| `role` | string | 否 | 角色：`admin` / `employee` |
| `status` | int | 否 | 状态：1=启用 0=禁用 |

**成功响应** `200`：`data` 为更新后的 [UserInfo](#38-用户信息结构-userinfo)，`msg="用户信息更新成功"`。

**错误码**：`40300`、`40400`（用户不存在）、`42200`。

### 4.6 PUT /api/v1/users/{user_id}/status — 启用/禁用用户

| 项目 | 说明 |
|---|---|
| 权限 | 管理员 |
| Content-Type | `application/json` |
| 说明 | 禁用后该用户现有 Token 立即失效（鉴权时校验 status）；写入操作日志（action=toggle_user_status） |

**请求参数**（JSON body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `status` | int | 是 | 1=启用 0=禁用 |

**成功响应** `200`：`data` 为更新后的 [UserInfo](#38-用户信息结构-userinfo)，`msg="用户已启用"` / `"用户已禁用"`。

**错误码**：`40300`、`40000`（状态值非法）、`40400`、`42200`（status 超出 0/1）。

### 4.7 DELETE /api/v1/users/{user_id} — 删除用户

| 项目 | 说明 |
|---|---|
| 权限 | 管理员 |
| 说明 | **物理删除**，请慎用；写入操作日志（action=delete_user） |

**路径参数**：`user_id`（int）。**成功响应** `200`：`{ "code": 200, "msg": "用户 'zhangsan' 已删除", "data": null }`。

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40000 | 400 | 不能删除自己的账号 |
| 40300 | 403 | 非管理员 |
| 40400 | 404 | 用户不存在 |

---

## 5. 知识库分类 `/api/v1/categories`（登录）

> 分类为树形结构，支持父子级递归查询与拖拽排序；全操作埋点操作日志（module=knowledge）。
> 删除为**物理删除**，存在子分类或未删除文档时拒绝。

### 5.1 GET /api/v1/categories/ — 分类树

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | 返回全量分类树（递归 children），`document_count` 为该分类下文档数（不含子分类） |

**成功响应** `200`：`data` 为 `CategoryTreeNode[]`。

```json
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "id": 1,
      "name": "人事制度",
      "parent_id": null,
      "description": "公司人事相关制度",
      "icon": "User",
      "sort_order": 0,
      "status": 1,
      "created_by": 1,
      "created_at": "2026-08-20T09:00:00",
      "updated_at": "2026-08-20T09:00:00",
      "document_count": 12,
      "children": [
        {
          "id": 2,
          "name": "考勤休假",
          "parent_id": 1,
          "document_count": 5,
          "children": []
        }
      ]
    }
  ]
}
```

`CategoryTreeNode` = `CategoryInfo` 字段 + `document_count`（int，默认 0）+ `children`（`CategoryTreeNode[]`，默认 `[]`）。

`CategoryInfo` 字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 分类 ID |
| `name` | string | 分类名称 |
| `parent_id` | int\|null | 父分类 ID（null=一级分类） |
| `description` | string\|null | 分类描述 |
| `icon` | string\|null | 图标（Element Plus 图标名） |
| `sort_order` | int | 同级排序值，默认 0 |
| `status` | int | 状态：1=启用 0=禁用 |
| `created_by` | int\|null | 创建人用户 ID |
| `created_at` | datetime\|null | 创建时间 |
| `updated_at` | datetime\|null | 更新时间 |

### 5.2 POST /api/v1/categories/ — 创建分类

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `application/json` |
| 说明 | 支持指定父分类；写入操作日志（action=create_category） |

**请求参数**（JSON body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | 分类名称，1–100 位 |
| `parent_id` | int | 否 | 父分类 ID（null/缺省=一级分类） |
| `description` | string | 否 | 分类描述，最长 2000 |
| `icon` | string | 否 | 图标（Element Plus 图标名），最长 255 |
| `sort_order` | int | 否 | 同级排序值，`>=0`，默认 0 |

**成功响应** `200`：`data` 为 `CategoryInfo`，`msg="分类创建成功"`。

**错误码**：`40100`、`40400`（父分类不存在）、`42200`（名称为空/超长）。

### 5.3 PUT /api/v1/categories/{category_id} — 更新分类

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `application/json` |
| 说明 | 仅更新传入字段；父级不能是自身/子孙；写入操作日志（action=update_category） |

**请求参数**（JSON body，全部选填）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 否 | 分类名称，1–100 位 |
| `parent_id` | int | 否 | 父分类 ID |
| `description` | string | 否 | 分类描述，最长 2000 |
| `icon` | string | 否 | 图标，最长 255 |
| `sort_order` | int | 否 | 排序值，`>=0` |
| `status` | int | 否 | 状态：1=启用 0=禁用 |

**成功响应** `200`：`data` 为更新后的 `CategoryInfo`，`msg="分类更新成功"`。

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40000 | 400 | 父分类不能是分类自身 |
| 40400 | 404 | 分类不存在 / 父分类不存在 |
| 42200 | 422 | 字段长度/取值越界 |

### 5.4 PUT /api/v1/categories/{category_id}/move — 拖拽排序

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `application/json` |
| 说明 | 变更父分类 / 同级排序值（前端树拖拽调用）；写入操作日志（action=move_category） |

**请求参数**（JSON body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `parent_id` | int | 否 | 新父分类 ID（null/缺省=移动到一级分类） |
| `sort_order` | int | 否 | 新排序值，`>=0` |

**成功响应** `200`：`data` 为移动后的 `CategoryInfo`，`msg="分类排序已更新"`。

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40000 | 400 | 父分类不能是分类自身 |
| 40000 | 400 | 不能将分类移动到自己的子分类下 |
| 40400 | 404 | 分类不存在 / 父分类不存在 |

### 5.5 DELETE /api/v1/categories/{category_id} — 删除分类

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | **物理删除**，带守卫；写入操作日志（action=delete_category） |

**成功响应** `200`：`{ "code": 200, "msg": "分类 '考勤休假' 已删除", "data": null }`。

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40000 | 400 | 该分类存在子分类（需先删除子分类） |
| 40000 | 400 | 该分类下存在未删除文档（需先删除或移动文档） |
| 40400 | 404 | 分类不存在 |

---

## 6. 文档管理 `/api/v1/documents`（登录）

> 文档上传流程：校验后缀 + 大小 → MinIO 持久化 → MySQL 记录元数据 → **后台异步**向量化任务。
> 同步接口仅做任务下发，实际解析、分块、向量化、实体抽取在后台执行，前端通过列表接口轮询 `vector_status`。

向量化状态四状态流转：`pending`（待处理）→ `processing`（处理中）→ `completed`（完成）/ `failed`（失败），
失败原因写入 `error_message`，支持重新触发向量化。

### 6.1 GET /api/v1/documents/ — 文档分页列表

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |

**查询参数**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20，最大 100 |
| `keyword` | string | 否 | 搜索关键词（匹配标题/文件名/标签） |
| `category_id` | int | 否 | 分类过滤（**含子分类**） |
| `vector_status` | string | 否 | 向量化状态过滤：`pending` / `processing` / `completed` / `failed`（非法值返回 `40000`） |
| `file_type` | string | 否 | 文件类型过滤（如 `pdf`） |
| `status` | int | 否 | 状态过滤：0=草稿 1=正常（列表默认排除已删除 `-1`） |

**成功响应** `200`：`data` 为 [PageResponse](#14-分页)，`items` 为 [DocumentInfo](#69-文档信息结构-documentinfo) 列表。

### 6.2 POST /api/v1/documents/upload — 上传文档（多文件）

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `multipart/form-data` |
| 说明 | 支持一次上传多个文件（最多 20 个）；接口立即返回，每文档下发一个后台向量化任务；写入操作日志（action=upload_document） |

**请求参数**（multipart 表单字段）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `files` | file[] | 是 | 文档文件，可多个（单次最多 20 个） |
| `category_id` | int | 是 | 所属分类 ID |
| `title` | string | 否 | 文档标题（**仅单文件上传时生效**；多文件时取文件名去后缀） |
| `description` | string | 否 | 文档描述 |
| `tags` | string | 否 | 标签（逗号分隔） |

上传校验规则（顺序执行）：

1. 后缀白名单（默认 `pdf, docx, txt, md, xlsx`，由环境变量 `UPLOAD_ALLOWED_EXTENSIONS` 配置）→ 不满足 `41500`
2. 文件大小上限（默认 50MB，可被 sys_config 键 `upload_max_size_mb` 实时覆盖）→ 超限 `41300`
3. SHA256 去重（与库内未删除文档或本批次其他文件内容相同）→ 重复 `40900`

**成功响应** `200`：`data` 为 [DocumentInfo](#69-文档信息结构-documentinfo) 列表。

```json
{
  "code": 200,
  "msg": "上传成功 2 个文档，向量化任务已下发",
  "data": [
    {
      "id": 11,
      "title": "员工手册",
      "category_id": 1,
      "category_name": "人事制度",
      "file_name": "employee-handbook.pdf",
      "file_type": "pdf",
      "file_size": 1048576,
      "file_path": "documents/2026/08/ab12cd34.pdf",
      "file_hash": "sha256...",
      "vector_status": "pending",
      "chunk_count": 0,
      "description": null,
      "tags": null,
      "view_count": 0,
      "download_count": 0,
      "status": 1,
      "uploaded_by": 1,
      "uploader_name": "admin",
      "vectorized_at": null,
      "error_message": null,
      "created_at": "2026-08-24T11:00:00",
      "updated_at": "2026-08-24T11:00:00"
    }
  ]
}
```

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40000 | 400 | 未选择上传文件；单次超过 20 个文件；文件内容为空 |
| 40900 | 409 | 文件内容 SHA256 重复（库内已存在或本批次重复）；`category_id` 不存在触发外键约束冲突 |
| 41300 | 413 | 文件超过大小限制 |
| 41500 | 415 | 文件后缀不在白名单 |
| 42200 | 422 | 缺少 `files` 或 `category_id` |

### 6.3 POST /api/v1/documents/batch-vectorize — 批量向量化

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `application/json` |
| 说明 | 多选文档一键触发（重建）向量；逐文档下发后台任务；写入操作日志（action=batch_vectorize） |

**请求参数**（JSON body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `document_ids` | int[] | 是 | 文档 ID 列表，至少 1 个 |

```json
{ "document_ids": [1, 2, 3] }
```

**成功响应** `200`：`data` 为 `VectorizeResult[]`，`msg` 携带实际下发数量。

```json
{
  "code": 200,
  "msg": "已下发 2 个向量化任务",
  "data": [
    { "document_id": 1, "triggered": true, "message": "" },
    { "document_id": 2, "triggered": true, "message": "" },
    { "document_id": 3, "triggered": false, "message": "文档不存在或已删除" }
  ]
}
```

`VectorizeResult` 字段：`document_id`（int）、`triggered`（bool，是否成功下发）、`message`（string，未触发时的跳过原因，已触发时为空串）。

**错误码**：`40100`、`42200`（`document_ids` 为空）。

### 6.4 GET /api/v1/documents/{document_id} — 文档详情

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | 每次调用浏览数 `view_count` +1 |

**成功响应** `200`：`data` 为 [DocumentInfo](#69-文档信息结构-documentinfo)。

**错误码**：`40100`、`40400`（文档不存在或已删除）。

### 6.5 GET /api/v1/documents/{document_id}/download — 下载文档

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | 返回 MinIO **预签名下载 URL**，前端直接打开链接下载；每次调用下载数 `download_count` +1 |

**成功响应** `200`

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "document_id": 11,
    "file_name": "employee-handbook.pdf",
    "download_url": "http://minio:9000/eakb/documents/...?X-Amz-Signature=...",
    "expires_in": 3600
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `document_id` | int | 文档 ID |
| `file_name` | string | 原始文件名 |
| `download_url` | string | 预签名下载地址 |
| `expires_in` | int | 链接有效期（秒），固定 3600 |

**错误码**：`40100`、`40400`（文档不存在或已删除）、`50303`（MinIO 异常）。

### 6.6 DELETE /api/v1/documents/{document_id} — 删除文档（软删）

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | **软删除**（status=-1），同步清理 Chroma 中该文档的全部向量；分块记录保留审计；写入操作日志（action=delete_document） |

**成功响应** `200`：`{ "code": 200, "msg": "文档 '员工手册' 已删除", "data": null }`。

**错误码**：`40100`、`40400`（文档不存在或已删除）、`50302`（Chroma 清理失败）。

### 6.7 POST /api/v1/documents/{document_id}/vectorize — 触发/重试向量化

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | 手动触发或失败重试；任务后台异步执行，立即返回；写入操作日志（action=vectorize_document） |

无请求体。**成功响应** `200`：`data` 为该文档的 [DocumentInfo](#69-文档信息结构-documentinfo)，`msg="向量化任务已下发"`。

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40400 | 404 | 文档不存在或已删除 |
| 40900 | 409 | 文档正在向量化处理中（processing） |
| 40900 | 409 | 向量化任务已在队列中（pending） |

### 6.8 GET /api/v1/documents/{document_id}/chunks — 查看分块列表

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | 文档分块记录列表（按 `chunk_index` 升序），分页返回 |

**查询参数**：`page`（默认 1）、`page_size`（默认 20，最大 100）。

**成功响应** `200`：`data` 为 [PageResponse](#14-分页)，`items` 为 `DocumentChunkInfo[]`。

`DocumentChunkInfo` 字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 分块记录 ID |
| `document_id` | int | 所属文档 ID |
| `chunk_index` | int | 分块下标（从 0 开始） |
| `chunk_text` | string | 分块文本 |
| `chunk_hash` | string\|null | 分块文本哈希（向量化去重用） |
| `chroma_chunk_id` | string\|null | Chroma 中对应向量的 ID |
| `token_count` | int\|null | 分块 token 数 |
| `created_at` | datetime\|null | 创建时间 |

**错误码**：`40100`、`40400`（文档不存在或已删除）。

### 6.9 文档信息结构 DocumentInfo

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 文档 ID |
| `title` | string | 文档标题 |
| `category_id` | int | 所属分类 ID |
| `category_name` | string\|null | 分类名称（冗余，方便前端展示） |
| `file_name` | string | 原始文件名 |
| `file_type` | string | 文件类型（后缀，小写） |
| `file_size` | int | 文件大小（字节） |
| `file_path` | string | MinIO 对象路径 |
| `file_hash` | string\|null | 文件 SHA256 |
| `vector_status` | string | 向量化状态：`pending` / `processing` / `completed` / `failed` |
| `chunk_count` | int | 分块数量，默认 0 |
| `description` | string\|null | 文档描述 |
| `tags` | string\|null | 标签（逗号分隔） |
| `view_count` | int | 浏览次数 |
| `download_count` | int | 下载次数 |
| `status` | int | 状态：1=正常 0=草稿 -1=已删除 |
| `uploaded_by` | int\|null | 上传人用户 ID |
| `uploader_name` | string\|null | 上传人用户名（冗余） |
| `vectorized_at` | datetime\|null | 向量化完成时间 |
| `error_message` | string\|null | 向量化失败原因 |
| `created_at` | datetime\|null | 创建时间 |
| `updated_at` | datetime\|null | 更新时间 |

---

## 7. 提示词模板 `/api/v1/templates`（登录）

> - 模板变量**仅支持** `{{question}}` 与 `{{context}}` 两个占位符，内容中出现其他变量返回 `40000`。
> - 系统预置模板（`is_system=1`）**禁止删除**（`40300`），可编辑内容。
> - 模板多对多绑定知识库分类，问答时按分类自动匹配（见 [9.5 模板自动匹配](#95-关键行为)）。
> - 全操作埋点操作日志（module=template）。

### 7.1 GET /api/v1/templates/ — 模板分页列表

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |

**查询参数**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20，最大 100 |
| `keyword` | string | 否 | 搜索关键词（匹配名称/描述/标签） |
| `category_id` | int | 否 | 分类过滤（模板绑定该分类，或默认分类为该分类） |
| `is_system` | int | 否 | 类型过滤：1=系统预置 0=用户自定义 |
| `tag` | string | 否 | 标签过滤 |
| `status` | int | 否 | 状态过滤：1=启用 0=禁用 |

**成功响应** `200`：`data` 为 [PageResponse](#14-分页)，`items` 为 [TemplateListItem](#712-模板结构) 列表（**不含** `template_content`）。

### 7.2 GET /api/v1/templates/popular — 热门模板

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | 按使用次数（`usage_count`）倒序，仅返回启用状态的模板 |

**查询参数**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `limit` | int | 否 | 返回条数，1–50，默认 10 |
| `is_system` | int | 否 | 类型过滤：1=系统预置 0=用户自定义 |

**成功响应** `200`：`data` 为 [TemplateListItem](#712-模板结构) 列表（非分页）。

### 7.3 GET /api/v1/templates/by-category/{category_id} — 按分类获取可用模板

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | 绑定该分类的模板优先，仅返回启用状态；RAG 问答的模板自动匹配复用此逻辑 |

**路径参数**：`category_id`（int）。**成功响应** `200`：`data` 为 [TemplateListItem](#712-模板结构) 列表（非分页）。

### 7.4 GET /api/v1/templates/{template_id} — 模板详情

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |

**成功响应** `200`：`data` 为 [TemplateInfo](#712-模板结构)（含 `template_content`、`variables` 与绑定分类）。

**错误码**：`40100`、`40400`（模板不存在）。

### 7.5 POST /api/v1/templates/ — 创建模板

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `application/json` |
| 说明 | 创建的是用户自定义模板（`is_system=0`）；写入操作日志（action=create_template） |

**请求参数**（JSON body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | 模板名称，1–200 位 |
| `description` | string | 否 | 模板描述，最长 2000 |
| `category_id` | int | 否 | 默认关联知识库分类 ID |
| `template_content` | string | 是 | 模板内容，至少 1 位；占位符仅允许 `{{question}}` / `{{context}}` |
| `variables` | object | 否 | 变量定义（见 [7.12](#712-模板结构)），缺省使用标准结构 |
| `tags` | string | 否 | 标签（逗号分隔），最长 500 |
| `status` | int | 否 | 状态：1=启用 0=禁用，默认 1 |

```json
{
  "name": "客服答疑模板",
  "description": "面向客服场景的通用答疑模板",
  "category_id": 3,
  "template_content": "你是企业客服助手。请仅根据以下知识库内容回答：\n{{context}}\n\n用户问题：{{question}}",
  "tags": "客服,通用"
}
```

**成功响应** `200`：`data` 为 [TemplateInfo](#712-模板结构)，`msg="模板创建成功"`。

**错误码**：`40100`、`40000`（模板内容包含不支持的占位变量）、`42200`（名称/内容为空等）。

### 7.6 PUT /api/v1/templates/{template_id} — 更新模板

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `application/json` |
| 说明 | 仅更新传入字段；系统模板可编辑内容但不可删除；写入操作日志（action=update_template） |

**请求参数**（JSON body，全部选填）：与 [7.5](#75-post-apiv1templates--创建模板) 相同的字段（`name`、`description`、`category_id`、`template_content`、`variables`、`tags`、`status`）。

**成功响应** `200`：`data` 为更新后的 [TemplateInfo](#712-模板结构)，`msg="模板更新成功"`。

**错误码**：`40100`、`40000`（非法占位变量）、`40400`（模板不存在）、`42200`。

### 7.7 DELETE /api/v1/templates/{template_id} — 删除模板

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | 系统预置模板（`is_system=1`）禁止删除；写入操作日志（action=delete_template） |

**成功响应** `200`：`{ "code": 200, "msg": "模板 '客服答疑模板' 已删除", "data": null }`。

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40300 | 403 | 系统预置模板不可删除 |
| 40400 | 404 | 模板不存在 |

### 7.8 POST /api/v1/templates/{template_id}/categories — 批量绑定分类（追加）

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `application/json` |
| 说明 | 追加语义，重复绑定自动忽略；写入操作日志（action=bind_template_categories） |

**请求参数**（JSON body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `category_ids` | int[] | 是 | 分类 ID 列表（空列表=无操作） |

```json
{ "category_ids": [1, 2, 3] }
```

**成功响应** `200`

```json
{
  "code": 200,
  "msg": "分类绑定成功",
  "data": { "template_id": 5, "category_ids": [1, 2, 3] }
}
```

`data.category_ids` 为绑定操作后该模板已绑定的**全部**分类 ID。

**错误码**：`40100`、`40400`（模板不存在）、`42200`。

### 7.9 PUT /api/v1/templates/{template_id}/categories — 设置分类（整体替换）

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `application/json` |
| 说明 | 整体替换语义，**空列表=清空全部绑定**；写入操作日志（action=set_template_categories） |

**请求参数**（JSON body）：同 [7.8](#78-post-apiv1templatestemplate_idcategories--批量绑定分类追加)。

**成功响应** `200`

```json
{
  "code": 200,
  "msg": "分类绑定已更新",
  "data": { "template_id": 5, "category_ids": [1, 2] }
}
```

### 7.10 DELETE /api/v1/templates/{template_id}/categories/{category_id} — 解绑单个分类

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | 幂等：未绑定时不报错；写入操作日志（action=unbind_template_category） |

**路径参数**：`template_id`（int）、`category_id`（int）。

**成功响应** `200`：`{ "code": 200, "msg": "分类已解绑", "data": null }`。

**错误码**：`40100`、`40400`（模板不存在）。

### 7.11 POST /api/v1/templates/{template_id}/render — 模板渲染（预览/测试）

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `application/json` |
| 说明 | 填充 `{{question}}`/`{{context}}` 生成完整 Prompt，仅本地渲染、**不调用 LLM**，供预览测试与问答复用 |

**请求参数**（JSON body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `question` | string | 是 | 用户问题，至少 1 位 |
| `context` | string | 否 | 检索上下文，默认空串（可留空测试渲染） |

```json
{ "question": "年假怎么申请？", "context": "[文档] 考勤休假制度\n员工年假为 5 天……" }
```

**成功响应** `200`

```json
{
  "code": 200,
  "msg": "渲染成功",
  "data": {
    "template_id": 1,
    "template_name": "默认答疑模板",
    "variables": { "question": "年假怎么申请？", "context": "[文档] 考勤休假制度\n……" },
    "rendered": "你是一名企业知识库智能助手……\n\n知识库内容：\n[文档] 考勤休假制度\n……\n\n用户问题：年假怎么申请？"
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `template_id` | int | 模板 ID |
| `template_name` | string | 模板名称 |
| `variables` | object | 实际使用的变量值 |
| `rendered` | string | 渲染后的完整 Prompt |

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40000 | 400 | 模板已禁用，无法使用 |
| 40400 | 404 | 模板不存在 |

### 7.12 模板结构

**TemplateListItem**（列表项，不含 `template_content`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 模板 ID |
| `name` | string | 模板名称 |
| `description` | string\|null | 模板描述 |
| `category_id` | int\|null | 默认关联分类 ID |
| `category_name` | string\|null | 默认分类名称（冗余） |
| `tags` | string\|null | 标签 |
| `usage_count` | int | 使用次数，默认 0 |
| `is_system` | int | 1=系统预置 0=用户自定义 |
| `status` | int | 1=启用 0=禁用 |
| `created_by` | int\|null | 创建人用户 ID |
| `creator_name` | string\|null | 创建人用户名（冗余） |
| `category_ids` | int[] | 已绑定的分类 ID 列表 |
| `category_names` | string[] | 已绑定的分类名称列表 |
| `created_at` | datetime\|null | 创建时间 |
| `updated_at` | datetime\|null | 更新时间 |

**TemplateInfo**（详情）= TemplateListItem 字段 + `template_content`（string，模板内容）+ `variables`（变量定义，默认标准结构）。

**variables 结构**（固定 `question` / `context` 两项，禁止额外字段）：

```json
{
  "question": { "type": "string", "description": "用户问题", "required": true, "default": "" },
  "context": { "type": "string", "description": "检索到的知识库上下文", "required": true, "default": "" }
}
```

单项字段：`type`（string，默认 `"string"`）、`description`（string，最长 200）、`required`（bool，默认 true）、`default`（string，默认空串）。

---

## 8. RAG 问答 `/api/v1/rag`（登录）

> 模块包含三组接口：流式问答（`POST /chat-stream`）、对话会话（`/conversations/*`）、消息反馈（`/messages/*`）。
> 会话接口仅能操作**本人**的对话（越权访问返回 `40400`，不暴露存在性）。

### 8.1 POST /api/v1/rag/chat-stream — SSE 流式问答

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `application/json`（请求） / `text/event-stream`（响应） |
| 说明 | 唯一的问答接口（不存在非流式 `/chat` 接口，见 [第 13 章](#13-与-designmd-的差异说明)）；完整 SSE 协议见 [第 9 章](#9-sse-流式问答协议完整契约) |

**请求参数**（JSON body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `question` | string | 是 | 用户问题，1–4000 字 |
| `conversation_id` | int | 否 | 会话 ID；不传自动新建（标题取问题前 20 字，换行替换为空格） |
| `template_id` | int | 否 | 模板 ID；优先于会话绑定与分类自动匹配 |
| `category_ids` | int[] | 否 | 本次提问限定分类；显式传入时覆盖会话范围并回写；空列表=不限 |

```json
{
  "question": "年假怎么申请？",
  "conversation_id": 12,
  "template_id": 1,
  "category_ids": [1, 2]
}
```

**成功响应**：`200`，`Content-Type: text/event-stream`，事件序列 `meta → sources → delta* → done`（详见 [第 9 章](#9-sse-流式问答协议完整契约)）。

**流建立前的错误**（返回标准 JSON 错误，**不会建立 SSE 流**）：

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40000 | 400 | `category_ids` 中存在不存在的分类 |
| 40100 | 401 | 未登录 / Token 无效 |
| 40400 | 404 | `conversation_id` 指定的会话不存在或无权访问 |
| 42200 | 422 | 请求体校验失败（如 question 为空或超过 4000 字） |
| 42900 | 429 | 触发接口限流（中间件在进入路由前拦截，见 [12 章](#12-错误码总表)） |

**流建立后的错误**：走 SSE `error` 事件（如模板无效、LLM 调用失败等），见 [9.5](#95-关键行为)。

### 8.2 GET /api/v1/rag/conversations/ — 我的对话列表

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | 仅本人会话，按更新时间倒序，`keyword` 匹配标题 |

**查询参数**：`page`（默认 1）、`page_size`（默认 20，最大 100）、`keyword`（string，标题关键词）。

**成功响应** `200`：`data` 为 [PageResponse](#14-分页)，`items` 为 [ConversationInfo](#88-会话与消息结构) 列表。

### 8.3 POST /api/v1/rag/conversations/ — 新建对话

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `application/json` |
| 说明 | 标题缺省为「新对话」；写入操作日志（action=create_conversation） |

**请求参数**（JSON body，禁止多余字段）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | 否 | 对话标题，1–100 位，默认「新对话」 |
| `template_id` | int | 否 | 使用的提示词模板 ID |
| `category_ids` | int[] | 否 | 限定知识库分类 ID 列表（默认不限） |

```json
{ "title": "年假咨询", "template_id": 1, "category_ids": [1, 2] }
```

**成功响应** `200`：`data` 为 [ConversationInfo](#88-会话与消息结构)，`msg="对话创建成功"`。

**错误码**：`40100`、`42200`（字段超长/多余字段）。

### 8.4 GET /api/v1/rag/conversations/{conversation_id} — 对话详情（含消息）

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | 会话信息 + 全部消息（按时间正序） |

**成功响应** `200`：`data` 为 [ConversationDetail](#88-会话与消息结构)（`ConversationInfo` 字段 + `messages` 数组）。

**错误码**：`40100`、`40400`（对话不存在或无权访问）。

### 8.5 DELETE /api/v1/rag/conversations/{conversation_id} — 删除对话

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | **物理删除**，消息随外键级联清理；仅限本人对话；写入操作日志（action=delete_conversation） |

**成功响应** `200`：`{ "code": 200, "msg": "对话 '年假咨询' 已删除", "data": null }`。

**错误码**：`40100`、`40400`（对话不存在或无权访问）。

### 8.6 PUT /api/v1/rag/conversations/{conversation_id}/title — 修改对话标题

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `application/json` |
| 说明 | 仅限本人对话；写入操作日志（action=rename_conversation） |

**请求参数**（JSON body，禁止多余字段）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | 是 | 新标题，1–100 位 |

**成功响应** `200`：`data` 为更新后的 [ConversationInfo](#88-会话与消息结构)，`msg="标题已更新"`。

**错误码**：`40100`、`40400`（对话不存在或无权访问）、`42200`（标题为空/超长）。

### 8.7 POST /api/v1/rag/messages/{message_id}/feedback — 回答点赞/点踩反馈

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| Content-Type | `application/json` |
| 说明 | 仅可对**本人会话中**的**助手回答**提交反馈，可重复提交覆盖；写入操作日志（action=message_feedback） |

**请求参数**（JSON body，禁止多余字段）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `feedback` | string | 是 | `positive`=点赞 / `negative`=点踩 |
| `comment` | string | 否 | 反馈备注，最长 1000 |

```json
{ "feedback": "positive", "comment": "回答很准确" }
```

**成功响应** `200`：`data` 为更新后的 [MessageInfo](#88-会话与消息结构)，`msg="反馈已提交"`。

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40000 | 400 | 仅可对助手回答提交反馈（对 user 消息反馈） |
| 40400 | 404 | 消息不存在或无权访问 |
| 42200 | 422 | feedback 不是 positive/negative |

### 8.8 会话与消息结构

**ConversationInfo**（会话摘要）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 会话 ID |
| `title` | string | 会话标题 |
| `template_id` | int\|null | 绑定的模板 ID |
| `category_ids` | int[] | 限定分类 ID 列表（DB 存逗号分隔字符串，接口层统一暴露为数组） |
| `message_count` | int | 消息总数，默认 0 |
| `status` | string | 状态，默认 `"active"` |
| `created_at` | datetime\|null | 创建时间 |
| `updated_at` | datetime\|null | 更新时间 |
| `ended_at` | datetime\|null | 结束时间 |

**ConversationDetail**（详情）= ConversationInfo 字段 + `messages`（`MessageInfo[]`，按时间正序）。

**MessageInfo**（对话消息）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 消息 ID |
| `conversation_id` | int | 所属会话 ID |
| `role` | string | `user` / `assistant` |
| `question` | string\|null | 用户问题（assistant 消息记录所回答的问题） |
| `answer` | string\|null | 助手回答（生成失败时为 null 或部分回答） |
| `prompt_full` | string\|null | 实际发送给 LLM 的完整 Prompt（含 system + 历史 + 当前问题） |
| `retrieved_chunks` | object[] | 检索到的分块（JSON 数组，DB 为 NULL 时序列化为 `[]`） |
| `sources` | object[] | 来源文档（同上） |
| `model_name` | string\|null | 使用的 LLM 模型名 |
| `token_usage` | object\|null | token 统计（结构见 [9.4](#94-sources--retrieved_chunks--token_usage-结构)） |
| `response_time_ms` | int\|null | 响应耗时（毫秒） |
| `feedback` | string\|null | 反馈：`positive` / `negative` / null |
| `feedback_comment` | string\|null | 反馈备注 |
| `error_message` | string\|null | 生成失败原因（如「客户端连接中断，生成未完成」） |
| `created_at` | datetime\|null | 创建时间 |

### 8.9 POST /api/v1/rag/search — 内部检索（ESD 集成，内部密钥鉴权）

无状态向量检索端点，供 **ESD（企业智能服务台）知识 agent** 服务端调用。复用问答链路的检索环节（分类校验 → 检索参数 → Chroma 向量检索 → 分块/来源组装），**无 LLM 调用、无消息落库、无操作日志**，由调用方自行组织回答。

**鉴权**：不走 JWT，请求头 `X-Internal-Key` 与 `sys_config.internal_api_key`（迁移时随机生成）比对，`hmac.compare_digest` 防时序攻击；缺头 / 密钥未配置 / 不匹配 → `40100`（fail-closed）。本端点豁免 IP 限流（ESD 同 IP 集中调用会触顶，密钥自身即保护）。

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `question` | string | 是 | 检索查询（1-4000 字符） |
| `category_ids` | int[] | 否 | 限定分类 ID 列表（空列表/缺省 = 不限；任一不存在 → 40000） |

```bash
curl -X POST http://localhost:8000/api/v1/rag/search \
  -H "Content-Type: application/json" \
  -H "X-Internal-Key: <internal_api_key>" \
  -d '{"question": "年假怎么申请", "category_ids": [3]}'
```

**响应**（`data` 字段）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `chunks` | object[] | 检索分块：`{chunk_id, document_id, title, text, score}`（与 `retrieved_chunks` 同构，见 [9.4](#94-sources--retrieved_chunks--token_usage-结构)） |
| `sources` | object[] | 按文档聚合去重的来源引用（`relevance_score` 取该文档命中分块最高分） |
| `top_k` | int | 本次检索返回条数（sys_config 实时值） |
| `similarity_threshold` | float | 本次相似度阈值（sys_config 实时值） |

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "chunks": [
      {
        "chunk_id": "doc11-0",
        "document_id": 11,
        "title": "年假制度",
        "text": "员工年假为每年 5 天。",
        "score": 0.92
      }
    ],
    "sources": [
      {
        "document_id": 11,
        "title": "年假制度",
        "file_name": "leave.pdf",
        "relevance_score": 0.92
      }
    ],
    "top_k": 5,
    "similarity_threshold": 0.75
  }
}
```

---

## 9. SSE 流式问答协议（完整契约）

本章是 `POST /api/v1/rag/chat-stream` 的前后端流式契约，实现位于
`backend/app/services/rag_service.py`，事件负载 Schema 位于 `backend/app/schemas/rag.py`
（`ChatMetaEvent` / `ChatSourcesEvent` / `ChatDoneEvent`）。

### 9.1 传输格式

- 请求：普通 `POST` + `application/json` + `Authorization: Bearer {access_token}`。
- 响应：`200`，`Content-Type: text/event-stream`。
- 每个 SSE 帧由 `event: <事件名>` 与 `data: <JSON 字符串>` 组成（data 为 `ensure_ascii=False` 的 JSON）。

**注意**：浏览器原生 `EventSource` 不支持自定义请求头，前端必须使用
`fetch` + `ReadableStream` 手动解析 SSE（项目实现见 `frontend/src/composables/useSSE.ts`）。

### 9.2 事件序列

| 事件 | 触发时机 | data 结构 |
|---|---|---|
| `meta` | 流开始（模板解析完成后第一个事件） | `{conversation_id, user_message_id, template_id, template_name}` |
| `sources` | 检索完成后（delta 之前） | `{sources: [...], retrieved_chunks: [...]}` |
| `delta` | 生成中（多次，含无匹配固定回复的分片） | `{content: "文本增量"}` |
| `done` | 生成完成 | `{conversation_id, message_id, token_usage, response_time_ms}` |
| `error` | 生成失败（流建立后） | `{message: "错误提示"}` |

正常序列固定为 `meta → sources → delta* → done`；`sources` 事件始终存在（即使检索结果为 0，`sources`/`retrieved_chunks` 为空数组）。失败发 `error` 事件后流结束，**不发** `done`。

### 9.3 各事件 data 字段

**meta**（`ChatMetaEvent`）

| 字段 | 类型 | 说明 |
|---|---|---|
| `conversation_id` | int | 会话 ID |
| `user_message_id` | int | 用户消息 ID（流开始前已落库） |
| `template_id` | int\|null | 命中的模板 ID（全部缺失时为 null） |
| `template_name` | string\|null | 命中的模板名称 |

**sources**（`ChatSourcesEvent`）

| 字段 | 类型 | 说明 |
|---|---|---|
| `sources` | object[] | 按文档聚合去重的来源引用列表（结构见 [9.4](#94-sources--retrieved_chunks--token_usage-结构)） |
| `retrieved_chunks` | object[] | 检索命中的分块列表（结构见 [9.4](#94-sources--retrieved_chunks--token_usage-结构)） |

**delta**：`{content}` — `content` 为本次增量文本片段。无匹配知识库时的固定回复也以 delta 分片（每片约 80 字符）模拟流式输出。

**done**（`ChatDoneEvent`）

| 字段 | 类型 | 说明 |
|---|---|---|
| `conversation_id` | int | 会话 ID |
| `message_id` | int | 助手消息 ID（已落库，可用于反馈接口） |
| `token_usage` | object\|null | token 统计（无匹配固定回复时为 `null`） |
| `response_time_ms` | int | 响应耗时（毫秒） |

**error**：`{message}` — 业务异常透传友好文案（如「提示词模板不存在或已禁用」）；系统异常统一为「生成失败，请稍后重试」，细节仅记录日志。失败时后台会尽力落库一条 `error_message` 的助手消息（见 [9.5 第 8 条](#95-关键行为)）。

### 9.4 sources / retrieved_chunks / token_usage 结构

**sources**（按文档聚合去重，`relevance_score` 取该文档命中分块的最高分）：

```json
[
  { "document_id": 11, "title": "员工手册", "file_name": "employee-handbook.pdf", "relevance_score": 0.9123 }
]
```

**retrieved_chunks**：

```json
[
  { "chunk_id": "doc11-chunk3", "document_id": 11, "title": "员工手册", "text": "年假：……", "score": 0.9123 }
]
```

| 字段 | 说明 |
|---|---|
| `chunk_id` | Chroma 中分块向量 ID |
| `document_id` | 来源文档 ID |
| `title` | 文档标题 |
| `text` | 分块文本 |
| `score` | 向量相似度分数 |

**token_usage**（LLM 返回，DeepSeek 流式最终块取不到时按 prompt/answer 文本长度估算兜底）：

```json
{ "prompt_tokens": 1250, "completion_tokens": 380, "total_tokens": 1630 }
```

### 9.5 关键行为

1. **无匹配知识库内容 → 不调用 LLM**：相似度低于阈值（sys_config `similarity_threshold`，默认 0.7）导致检索 0 命中时，
   不调用 LLM，将固定提示按约 80 字符分片以 `delta` 事件流式返回后直接 `done`，杜绝编造答案。固定提示原文：

   > 抱歉，知识库中未找到与您问题相关的资料，我无法给出可靠回答。
   >
   > 建议尝试：
   > 1. 换一种表述方式重新提问；
   > 2. 检查或调整知识库分类筛选范围；
   > 3. 联系管理员补充相关文档。

   此场景 `done` 事件中 `token_usage` 为 `null`，`sources`/`retrieved_chunks` 为空数组。

2. **多轮上下文**：自动携带最近 N 轮历史（N 取 sys_config `chat_history_rounds`，缺省 5），
   叠加模板渲染后的系统 Prompt 发送给 LLM。历史过滤规则：生成失败（answer 为空）与无匹配固定回复
   （retrieved_chunks 为空）的轮次跳过；单条消息截断至 2000 字符。

3. **多轮追问检索兜底**：裸问题（如「那怎么申请呢？」）检索 0 命中时，自动用
   「最近一轮完整问答的用户问题 + 当前问题」拼接重新检索；仍无命中则直接用该用户问题检索。
   用于解决追问省略主语导致的相似度不足。

4. **模板自动匹配优先级**：显式 `template_id`（必须存在且启用，否则流内 `error` 事件
   「提示词模板不存在或已禁用」）> 会话已绑定且仍启用的模板 > 首个限定分类的 by-category 匹配
   （绑定该分类的模板优先）> 系统默认模板（`is_system=1` 且启用、ID 最小的种子模板）。
   命中模板与会话绑定不一致时会写回会话 `template_id`。

5. **分类范围**：`category_ids` 显式传入时逐项校验存在性（任一不存在 → 流建立前 JSON `40000`），
   覆盖会话的限定范围并回写；空列表=不限范围。检索按 `category_id` 元数据过滤 Top-K
   （`top_k` 默认 5，可 sys_config 覆盖），上下文按 `max_context_tokens`（默认 4096）整块截断。

6. **图谱增强（可选）**：仅当检索命中且 sys_config `graph_enhance_enabled`（默认 false）开启时，
   补充实体关联上下文；Neo4j 异常或超过 5 秒超时静默降级为纯向量检索，不影响问答。

7. **断线处理**：客户端中断（CancelledError/GeneratorExit）时**不自动重连重发**（避免 LLM 重复计费），
   尽力把已生成的部分回答落库，`error_message="客户端连接中断，生成未完成"`，前端提示手动重试。

8. **流内错误**：流建立后的任何异常（模板无效、Embedding 未初始化、LLM 失败等）发 SSE `error` 事件，
   同时尽力落库一条 `role=assistant`、`error_message=<原因>` 的失败消息（`answer` 为已生成的部分内容）。
   与流建立前的 JSON 错误不同：流建立前（鉴权/限流/分类校验/会话解析/请求体校验）失败时
   **用户消息与流均不产生**，返回标准 `{code, msg, data}` JSON。

9. **消息落库**：流开始前用户消息已落库；生成完成后助手消息落库并携带 `retrieved_chunks`、
   `sources`、`token_usage`、`response_time_ms`、`prompt_full`，随后会话 `message_count` +1，
   并写入操作日志（module=rag, action=chat）。

10. **接口限流 429**：限流由纯 ASGI 中间件在路由前按客户端 IP 拦截，命中时返回标准 429 JSON
    （`42900`），**SSE 流不会建立**；因此对 chat-stream 而言，429 必然是普通 JSON 响应而非 error 事件。

### 9.6 完整事件流示例

**请求**（fetch + Bearer）：

```http
POST /api/v1/rag/chat-stream HTTP/1.1
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{"question":"年假怎么申请？","conversation_id":12}
```

**响应流**：

```text
event: meta
data: {"conversation_id": 12, "user_message_id": 34, "template_id": 1, "template_name": "默认答疑模板"}

event: sources
data: {"sources": [{"document_id": 11, "title": "员工手册", "file_name": "employee-handbook.pdf", "relevance_score": 0.9123}], "retrieved_chunks": [{"chunk_id": "doc11-chunk3", "document_id": 11, "title": "员工手册", "text": "年假：……", "score": 0.9123}]}

event: delta
data: {"content": "根据《员工手册》"}

event: delta
data: {"content": "，年假申请流程如下：……"}

event: done
data: {"conversation_id": 12, "message_id": 35, "token_usage": {"prompt_tokens": 1250, "completion_tokens": 380, "total_tokens": 1630}, "response_time_ms": 2341}
```

**失败示例**（流建立后 LLM 异常）：

```text
event: meta
data: {"conversation_id": 12, "user_message_id": 36, "template_id": 1, "template_name": "默认答疑模板"}

event: sources
data: {"sources": [...], "retrieved_chunks": [...]}

event: error
data: {"message": "大模型服务暂时不可用，请稍后重试"}
```

---

## 10. 知识图谱 `/api/v1/graph`

> 固定三类节点（Entity 实体 / Document 文档 / Category 分类）与四类关系
> （BELONGS_TO / MENTIONS / RELATED_TO / SIMILAR_TO）。实体抽取在文档向量化完成后异步执行，
> 支持手动触发重建。查询接口登录即可，`POST /build` 仅管理员。

### 10.1 GET /api/v1/graph/entities/ — 实体分页列表

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | 按提及次数（`mention_count`）降序 |

**查询参数**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20，最大 100 |
| `keyword` | string | 否 | 实体名/别名关键词 |
| `type` | string | 否 | 实体类型过滤（查询参数名为 `type`，如 `Person`、`Org`、`Term`、`Product`、`Policy`、`Event`、`Location`） |

**成功响应** `200`：`data` 为 [PageResponse](#14-分页)，`items` 为 `EntityListItem[]`。

`EntityListItem` 字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | string | 实体名称 |
| `type` | string | 实体类型（Person/Org/Term/Product/Policy/Event/Location） |
| `description` | string | 实体描述，默认空串 |
| `aliases` | string[] | 别名列表 |
| `mention_count` | int | 被文档提及次数 |

### 10.2 GET /api/v1/graph/entities/{name} — 实体详情

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | 实体属性 + RELATED_TO 一跳关联实体 + 提及文档 |

**路径参数**：`name`（string，实体名称）。

**成功响应** `200`：`data` 为 `EntityDetailResponse`（= `EntityListItem` 字段 + `neighbors` + `documents`）：

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "name": "张伟",
    "type": "Person",
    "description": "技术部经理",
    "aliases": ["张经理"],
    "mention_count": 8,
    "neighbors": [
      { "name": "技术部", "type": "Org", "description": "", "aliases": [], "relation_type": "领导", "weight": 0.8 }
    ],
    "documents": [
      { "document_id": 11, "title": "员工手册", "file_name": "employee-handbook.pdf", "count": 3, "positions": [1, 5, 9] }
    ]
  }
}
```

| 子结构 | 字段 | 说明 |
|---|---|---|
| `neighbors[]` | `name` / `type` / `description` / `aliases` | 邻居实体信息 |
| | `relation_type` | 关系类型 |
| | `weight` | 关系权重 0–1 |
| `documents[]` | `document_id` / `title` / `file_name` | 提及文档信息（document_id 对应 MySQL `kb_document.id`） |
| | `count` | 提及次数 |
| | `positions` | 命中分块下标列表 |

**错误码**：`40100`、`40400`（实体不存在）。

### 10.3 GET /api/v1/graph/search — 图谱搜索 / 画布全景

| 项目 | 说明 |
|---|---|
| 权限 | 登录 |
| 说明 | 返回 nodes/edges/stats，前端可视化与搜索共用此接口；`keyword` 为空返回画布全景，非空返回匹配实体的子图 |

**查询参数**：`keyword`（string，选填；空=画布全景，非空=匹配实体子图）。

**成功响应** `200`：`data` 为 `GraphSearchResponse`：

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "nodes": [
      { "id": "张伟", "node_type": "Entity", "label": "张伟", "type": "Person", "description": "", "aliases": [], "mention_count": 8 },
      { "id": "doc_11", "node_type": "Document", "label": "员工手册", "title": "员工手册", "file_name": "employee-handbook.pdf", "category_id": 1, "category_name": "人事制度" },
      { "id": "cat_1", "node_type": "Category", "label": "人事制度", "category_id": 1, "category_name": "人事制度" }
    ],
    "edges": [
      { "source": "doc_11", "target": "张伟", "edge_type": "MENTIONS", "count": 3 },
      { "source": "张伟", "target": "技术部", "edge_type": "RELATED_TO", "relation_type": "领导", "weight": 0.8 },
      { "source": "doc_11", "target": "cat_1", "edge_type": "BELONGS_TO" }
    ],
    "stats": {
      "entity_count": 120, "document_count": 35, "category_count": 8,
      "related_to_count": 210, "mentions_count": 480, "similar_to_count": 60
    },
    "truncated": false
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `nodes[]` | object | 图节点（`GraphNode`） |
| `edges[]` | object | 图边（`GraphEdge`） |
| `stats` | object | 图谱统计（按响应内实际数据计数） |
| `truncated` | bool | 节点数达到上限被截断 |

`GraphNode` 要点：`id` 为画布内唯一 ID（Entity 用实体名，Document 为 `doc_{id}`，Category 为 `cat_{id}`）；
`node_type` 为 `Entity|Document|Category`；`label` 为显示名称；其余字段按节点类型选择性出现
（Entity 携带 `type/description/aliases/mention_count`，Document 携带 `document_id/title/file_name/category_id/category_name`，
Category 携带 `category_id/category_name`）。

`GraphEdge` 要点：`source`/`target` 为节点 ID；`edge_type` 为 `RELATED_TO|MENTIONS|BELONGS_TO|SIMILAR_TO`；
`relation_type`/`weight` 仅 RELATED_TO、`count` 仅 MENTIONS、`score` 仅 SIMILAR_TO。

### 10.4 POST /api/v1/graph/build — 触发图谱构建（重建）

| 项目 | 说明 |
|---|---|
| 权限 | **管理员** |
| Content-Type | `application/json` |
| 说明 | 请求体缺省（或不含 document_id）为**全量重建**；传 document_id 为单文档重建；任务后台异步执行，立即返回；写入操作日志（action=build_graph） |

**请求参数**（JSON body，可选，禁止多余字段）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `document_id` | int | 否 | 单文档重建的文档 ID（`>=1`）；缺省=全量重建 |

```json
{ "document_id": 11 }
```

**成功响应** `200`

```json
{ "code": 200, "msg": "图谱重建任务已下发 (文档 11)", "data": null }
```

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40000 | 400 | 文档尚未完成向量化，无法构建图谱 |
| 40300 | 403 | 非管理员 |
| 40400 | 404 | 文档不存在或已删除 |

---

## 11. 管理后台 `/api/v1/admin`（管理员）

> 本模块全部接口要求 `admin` 角色。操作日志仅查询、不提供删除接口（审计保留）。

### 11.1 GET /api/v1/admin/dashboard — 数据看板统计

| 项目 | 说明 |
|---|---|
| 权限 | 管理员 |
| 说明 | 聚合统计：用户/文档/会话/今日问答/向量化/今日操作 |

**成功响应** `200`：`data` 为 `DashboardStats`：

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "user_count": 45,
    "document_count": 120,
    "conversation_count": 300,
    "today_question_count": 23,
    "vectorized_document_count": 110,
    "today_operation_count": 87
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `user_count` | int | 用户总数（含禁用） |
| `document_count` | int | 文档总量（不含软删） |
| `conversation_count` | int | 问答会话总量 |
| `today_question_count` | int | 今日问答量（用户提问消息数） |
| `vectorized_document_count` | int | 向量化完成文档数 |
| `today_operation_count` | int | 今日操作日志数 |

**错误码**：`40100`、`40300`。

### 11.2 GET /api/v1/admin/logs — 操作日志分页查询

| 项目 | 说明 |
|---|---|
| 权限 | 管理员 |
| 说明 | 全模块操作日志，多条件筛选；仅查询（审计保留，无删除接口） |

**查询参数**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20，最大 100 |
| `username` | string | 否 | 操作人用户名（模糊匹配） |
| `module` | string | 否 | 操作模块（`auth`/`user`/`knowledge`/`template`/`rag`/`graph`/`system`） |
| `action` | string | 否 | 操作类型（如 `login`、`upload_document`、`chat`） |
| `status` | string | 否 | 执行结果：`success` / `failed` |
| `start_time` | datetime | 否 | 操作时间起（ISO8601，如 `2026-08-01T00:00:00`） |
| `end_time` | datetime | 否 | 操作时间止（ISO8601） |

**成功响应** `200`：`data` 为 [PageResponse](#14-分页)，`items` 为 `OperationLogInfo[]`。

`OperationLogInfo` 字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 日志 ID |
| `user_id` | int\|null | 操作人用户 ID |
| `username` | string\|null | 操作人用户名 |
| `action` | string | 操作类型 |
| `module` | string\|null | 操作模块 |
| `target_type` | string\|null | 目标类型（user/document/category/conversation 等） |
| `target_id` | string\|null | 目标 ID |
| `detail` | object\|null | 操作明细（JSON） |
| `ip_address` | string\|null | 操作人 IP |
| `user_agent` | string\|null | 客户端 UA |
| `status` | string | 执行结果：`success` / `failed` |
| `error_info` | string\|null | 失败原因 |
| `created_at` | datetime\|null | 操作时间 |

**错误码**：`40100`、`40300`。

### 11.3 GET /api/v1/admin/configs — 系统配置列表

| 项目 | 说明 |
|---|---|
| 权限 | 管理员 |
| 说明 | 全量配置项列表（管理页面可视化表单数据源） |

**成功响应** `200`：`data` 为 `ConfigItem[]`（非分页）。

`ConfigItem` 字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 配置项 ID |
| `config_key` | string | 配置键（如 `chunk_size`、`chat_history_rounds`、`rate_limit_enabled`） |
| `config_value` | string\|null | 配置值（字符串形式） |
| `config_type` | string | 值类型（默认 `string`，另有 int/float/bool/json 等） |
| `description` | string\|null | 配置说明 |
| `updated_by` | int\|null | 最后更新人用户 ID |
| `updated_at` | datetime\|null | 最后更新时间 |
| `created_at` | datetime\|null | 创建时间 |

### 11.4 PUT /api/v1/admin/configs/{key} — 更新系统配置

| 项目 | 说明 |
|---|---|
| 权限 | 管理员 |
| Content-Type | `application/json` |
| 说明 | 更新后**实时生效**（业务读取方每次从 DB 读取，无需重启服务）；限流等进程内缓存同步失效；写入操作日志（action=update_config） |

**路径参数**：`key`（string，配置键）。

**请求参数**（JSON body）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `config_value` | string | 是 | 新配置值（字符串形式，按 `config_type` 做类型校验） |

```json
{ "config_value": "8" }
```

**成功响应** `200`：`data` 为更新后的 `ConfigItem`，`msg="配置 'chat_history_rounds' 已更新, 实时生效"`。

**错误码**

| 业务码 | HTTP | 场景 |
|---|---|---|
| 40000 | 400 | 配置值不符合 `config_type` 类型约束 |
| 40300 | 403 | 非管理员 |
| 40400 | 404 | 配置项不存在 |

---

## 12. 错误码总表

业务码（`code`）与 HTTP 状态码的关系：`http_status = code / 100`。
`AppException` 的 `detail`（若有）会放入响应 `data`；生产环境系统异常不返回堆栈细节。

| 业务码 | HTTP | 触发场景 |
|---|---|---|
| 200 | 200 | 成功（统一响应固定值） |
| 40000 | 400 | 请求参数错误：批量用户操作 action 非法/含自己、删除自己账号、旧密码错误、上传未选文件/空文件/超数量、非法 vector_status、分类删除时存在子分类或文档、父分类为自身/子孙、模板内容含非法占位符、模板已禁用无法渲染、对非助手消息反馈、图谱构建时文档未向量化、chat-stream 分类不存在、配置值类型校验失败等 |
| 40100 | 401 | 未认证：未携带 Token、Token 无效/过期/缺 sub、用户不存在或已禁用；登录失败（用户名或密码错误、账号被禁用）；Refresh Token 无效或过期 |
| 40300 | 403 | 无权限：非 admin 访问 `/users`、`/admin`、`POST /graph/build`；删除系统预置模板 |
| 40400 | 404 | 资源不存在：用户/分类/文档/模板/会话/消息/实体/配置项不存在；会话/消息跨用户访问（统一返回 404 不暴露存在性）；路由不存在（HTTP 404 兜底） |
| 40900 | 409 | 资源冲突：用户名已存在、文件 SHA256 重复、文档向量化已在队列/处理中、上传 category_id 不存在触发外键约束；全局兜底捕获数据库唯一/外键冲突（IntegrityError） |
| 41300 | 413 | 文件大小超过限制（默认 50MB，sys_config `upload_max_size_mb` 实时覆盖） |
| 41500 | 415 | 文件后缀不在白名单（默认 `pdf,docx,txt,md,xlsx`） |
| 42200 | 422 | 请求参数校验失败（Pydantic）：字段缺失/超长/取值越界/多余字段/两次密码不一致/feedback 枚举非法等；处理器取第一条错误组装友好文案 |
| 42900 | 429 | 接口限流：单 IP 滑动窗口超限（仅作用于 `/api/v1/*`；开关 `rate_limit_enabled` 默认关闭，阈值 `rate_limit_requests`=60 次 / `rate_limit_window_seconds`=60 秒，sys_config 实时可调）；对 chat-stream 在路由前拦截，SSE 流不会建立 |
| 500 | 500 | 未捕获系统异常（全局兜底）；生产环境 msg 为「服务器内部错误」，开发环境透出异常信息 |
| 50300 | 503 | 服务不可用（通用外部依赖异常）：Embedding 模型未初始化等 |
| 50301 | 503 | 关系数据库异常：MySQL 不可用/执行失败（SQLAlchemyError 全局兜底） |
| 50302 | 503 | 向量库异常：Chroma 检索/写入/删除失败 |
| 50303 | 503 | 对象存储异常：MinIO 上传/下载失败 |
| 50304 | 503 | 大模型服务异常：LLM 调用失败/超时（流内走 SSE error 事件透传该文案） |
| 50400 | 504 | 请求处理超时（asyncio.TimeoutError 全局兜底）：LLM/Neo4j/MinIO 等外部依赖调用超时 |

---

## 13. 与 DESIGN.md 的差异说明

本文档以实际代码为准，与 DESIGN.md 第六章接口设计存在以下差异，对接时请以本文档为准：

1. **不存在非流式问答接口**：DESIGN.md 中的 `POST /rag/chat`（非流式）**未实现**，
   所有问答统一走 `POST /api/v1/rag/chat-stream`（SSE）。`rag.py` 路由文件注释明确
   「流式问答 (SSE, 统一走此接口)」。
2. **对话会话与反馈挂在 `/rag` 前缀下**：`conversations` 相关接口实际路径为
   `/api/v1/rag/conversations/*`（而非独立 `/conversations` 前缀），消息反馈为
   `/api/v1/rag/messages/{id}/feedback`。
3. **系统端点不走统一包装**：`GET /api/v1/ping`、`GET /health`、`GET /` 返回裸 JSON，
   不套 `{code, msg, data}`。
4. **SSE 请求方法为 POST**：chat-stream 使用 `POST` 而非 GET，且需 `Authorization` 头，
   前端使用 fetch + ReadableStream 解析（EventSource 不支持自定义头）。
5. **业务码体系**：统一响应 `code` 为五位业务码（如 `40100`），HTTP 状态码 = code/100，
   错误场景细分到 40000/40100/40300/40400/40900/41300/41500/42200/42900/500/50300–50304/50400
   （见 [第 12 章](#12-错误码总表)）。
6. **分类删除为物理删除**：文档采用软删（status=-1），但分类、用户、对话删除为物理删除，
   与「全部软删除」的默认假设不同，各端点小节已标注。

---

## 附：核心 sys_config 配置键（与接口行为相关）

| 配置键 | 默认值 | 影响接口/行为 |
|---|---|---|
| `chunk_size` | 512 | 文档向量化分块大小 |
| `chunk_overlap` | 64 | 分块重叠大小 |
| `top_k` | 5 | 向量检索返回条数 |
| `similarity_threshold` | 0.7 | 相似度阈值（低于则视为无匹配） |
| `max_context_tokens` | 4096 | 上下文最大 Token（整块截断） |
| `chat_history_rounds` | 5 | 多轮对话携带历史轮数 |
| `graph_enhance_enabled` | false | 是否启用图谱增强检索 |
| `graph_entity_top_k` | 5 | 图谱增强单实体邻居数量上限 |
| `upload_max_size_mb` | 50 | 上传文件大小上限（MB） |
| `rate_limit_enabled` | false | 接口限流开关 |
| `rate_limit_requests` | 60 | 限流窗口内单 IP 最大请求数 |
| `rate_limit_window_seconds` | 60 | 限流窗口时长（秒） |

以上键均可通过 `GET /api/v1/admin/configs` 查看、`PUT /api/v1/admin/configs/{key}` 修改（管理员，实时生效）。

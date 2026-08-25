# 企业知识库智能助手 — 项目设计方案

## 一、项目概述

基于 RAG（检索增强生成）技术的企业知识库智能助手，帮助员工快速检索企业内部文档、获取精准答案。

---

## 二、技术架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    前端 (Vue3 + TS)                      │
│   ElementPlus → Pinia → VueRouter → Axios               │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP / SSE (流式回答)
┌────────────────────▼────────────────────────────────────┐
│                 后端 (FastAPI)                           │
│   ┌──────────┬──────────┬──────────┬────────────────┐   │
│   │ Auth     │ Document │ RAG      │ Prompt         │   │
│   │ Service  │ Service  │ Service  │ Template Svc   │   │
│   └────┬─────┴────┬─────┴────┬─────┴───────┬────────┘   │
│        │          │          │             │             │
│   ┌────▼──────────▼──────────▼─────────────▼────────┐   │
│   │              LlamaIndex (RAG 编排)               │   │
│   │  文档解析 → 分块 → Embedding → 检索 → 生成       │   │
│   └────┬──────────────┬──────────────┬───────────────┘   │
└────────┼──────────────┼──────────────┼───────────────────┘
         │              │              │
   ┌─────▼─────┐  ┌─────▼─────┐  ┌────▼──────┐
   │   MySQL   │  │  Chroma   │  │   Neo4j   │   MinIO
   │ (关系数据) │  │ (向量库)  │  │ (知识图谱)│  (文件存储)
   └───────────┘  └───────────┘  └───────────┘
```

### Docker 环境

| 服务 | 端口 | 用途 |
|------|------|------|
| MySQL 8.0 | 3306 | 业务关系数据 |
| Neo4j 5.x | 7474 (HTTP) / 7687 (Bolt) | 知识图谱 |
| MinIO | 9000 (API) / 9001 (Console) | 文件对象存储 |

---

## 三、功能模块设计

### 模块全景图

```
企业知识库智能助手
├── 1. 员工认证模块 (Auth)
│   ├── 1.1 注册
│   ├── 1.2 登录 / 注销
│   ├── 1.3 密码修改 / 重置
│   └── 1.4 个人信息管理
│
├── 2. 知识库分类管理 (Category)
│   ├── 2.1 分类树 CRUD
│   ├── 2.2 分类排序
│   └── 2.3 分类关联关系
│
├── 3. 文档管理模块 (Document)
│   ├── 3.1 文档上传（PDF / DOCX / TXT / MD / XLSX）
│   ├── 3.2 文档列表 & 搜索 & 筛选
│   ├── 3.3 文档预览 / 下载
│   ├── 3.4 文档删除（软删除）
│   ├── 3.5 文档向量化（手动触发 / 上传自动）
│   ├── 3.6 向量化状态追踪
│   └── 3.7 批量操作
│
├── 4. 提示词模版管理 (PromptTemplate)
│   ├── 4.1 模版 CRUD
│   ├── 4.2 模版变量占位符（如 {{category}}, {{question}}）
│   ├── 4.3 模版关联知识库分类
│   ├── 4.4 系统预置模版 + 员工自定义模版
│   ├── 4.5 模版使用统计
│   └── 4.6 模版预览 / 快速选择
│
├── 5. RAG 智能问答 (RAG)
│   ├── 5.1 对话式问答（多轮对话上下文）
│   ├── 5.2 提示词模版快捷选择
│   ├── 5.3 知识库分类范围限定
│   ├── 5.4 流式回答（SSE / Streaming）
│   ├── 5.5 答案来源引用（展示参考文档 & 分块）
│   ├── 5.6 对话历史管理（新建 / 切换 / 删除）
│   ├── 5.7 回答反馈（点赞 / 点踩 + 评论）
│   └── 5.8 Token 用量统计
│
├── 6. 知识图谱模块 (Knowledge Graph)
│   ├── 6.1 文档实体抽取
│   ├── 6.2 实体关系构建
│   ├── 6.3 图谱可视化
│   └── 6.4 图谱增强检索
│
├── 7. 管理后台 (Admin Dashboard)
│   ├── 7.1 数据统计看板（文档数、用户数、问答量）
│   ├── 7.2 用户管理
│   ├── 7.3 操作日志
│   └── 7.4 系统配置
│
└── 8. 通用模块
    ├── 8.1 统一响应格式
    ├── 8.2 全局异常处理
    ├── 8.3 JWT 鉴权中间件
    └── 8.4 操作日志记录
```

---

## 四、数据库设计

### 4.1 MySQL 表结构

#### 4.1.1 `sys_user` — 系统用户表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | 用户ID |
| username | VARCHAR(50) | UNIQUE, NOT NULL | 用户名（工号） |
| password_hash | VARCHAR(255) | NOT NULL | bcrypt 密码哈希 |
| email | VARCHAR(100) | | 邮箱 |
| phone | VARCHAR(20) | | 手机号 |
| real_name | VARCHAR(50) | | 真实姓名 |
| department | VARCHAR(100) | | 部门 |
| position | VARCHAR(100) | | 职位 |
| avatar_url | VARCHAR(500) | | 头像URL |
| role | ENUM('admin','employee') | NOT NULL, DEFAULT 'employee' | 角色 |
| status | TINYINT | NOT NULL, DEFAULT 1 | 1=启用 0=禁用 |
| last_login_at | DATETIME | | 最后登录时间 |
| created_at | DATETIME | NOT NULL, DEFAULT NOW() | |
| updated_at | DATETIME | ON UPDATE NOW() | |

> **索引**: `idx_username`(username), `idx_department`(department)

---

#### 4.1.2 `kb_category` — 知识库分类表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | |
| name | VARCHAR(100) | NOT NULL | 分类名称 |
| parent_id | BIGINT | FK → kb_category.id, NULL | 父分类（NULL=一级分类） |
| description | TEXT | | 分类描述 |
| sort_order | INT | DEFAULT 0 | 排序 |
| icon | VARCHAR(255) | | 图标 |
| status | TINYINT | DEFAULT 1 | 1=启用 0=禁用 |
| created_by | BIGINT | FK → sys_user.id | |
| created_at | DATETIME | DEFAULT NOW() | |
| updated_at | DATETIME | ON UPDATE NOW() | |

> **索引**: `idx_parent`(parent_id), `idx_sort`(sort_order)

---

#### 4.1.3 `kb_document` — 知识库文档表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | |
| title | VARCHAR(255) | NOT NULL | 文档标题 |
| category_id | BIGINT | FK → kb_category.id | 所属分类 |
| file_name | VARCHAR(255) | NOT NULL | 原始文件名 |
| file_type | VARCHAR(20) | NOT NULL | pdf / docx / txt / md / xlsx |
| file_size | BIGINT | NOT NULL | 文件大小(字节) |
| file_path | VARCHAR(500) | NOT NULL | MinIO 对象路径 |
| file_hash | VARCHAR(64) | | SHA256 去重 |
| vector_status | ENUM('pending','processing','completed','failed') | DEFAULT 'pending' | 向量化状态 |
| chunk_count | INT | DEFAULT 0 | 分块数量 |
| description | TEXT | | 文档描述 |
| tags | VARCHAR(500) | | 标签（逗号分隔） |
| view_count | INT | DEFAULT 0 | 浏览次数 |
| download_count | INT | DEFAULT 0 | 下载次数 |
| status | TINYINT | DEFAULT 1 | 1=发布 0=草稿 -1=已删除 |
| uploaded_by | BIGINT | FK → sys_user.id | |
| vectorized_at | DATETIME | | 向量化完成时间 |
| created_at | DATETIME | DEFAULT NOW() | |
| updated_at | DATETIME | ON UPDATE NOW() | |

> **索引**: `idx_category`(category_id), `idx_status`(status), `idx_vector_status`(vector_status), `idx_file_hash`(file_hash)

---

#### 4.1.4 `kb_document_chunk` — 文档分块记录表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | |
| document_id | BIGINT | FK → kb_document.id, CASCADE | |
| chunk_index | INT | NOT NULL | 分块序号 |
| chunk_text | TEXT | NOT NULL | 分块文本 |
| chunk_hash | VARCHAR(64) | | 分块哈希 |
| chroma_chunk_id | VARCHAR(255) | | Chroma 中对应 ID |
| token_count | INT | | Token 数量 |
| created_at | DATETIME | DEFAULT NOW() | |

> **索引**: `idx_document`(document_id), `idx_chroma_id`(chroma_chunk_id)

---

#### 4.1.5 `pt_template` — 提示词模版表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | |
| name | VARCHAR(200) | NOT NULL | 模版名称 |
| description | TEXT | | 模版描述 |
| category_id | BIGINT | FK → kb_category.id, NULL | 默认关联知识库分类 |
| template_content | TEXT | NOT NULL | 模版内容（含占位符） |
| variables | JSON | | 变量定义 |
| tags | VARCHAR(500) | | 标签 |
| usage_count | INT | DEFAULT 0 | 使用次数 |
| is_system | TINYINT | DEFAULT 0 | 1=系统预置 0=用户自定义 |
| status | TINYINT | DEFAULT 1 | 1=启用 0=禁用 |
| created_by | BIGINT | FK → sys_user.id | |
| created_at | DATETIME | DEFAULT NOW() | |
| updated_at | DATETIME | ON UPDATE NOW() | |

> `variables` JSON 结构:
> ```json
> {
>   "question": { "type": "string", "description": "用户问题", "required": true, "default": "" },
>   "context":  { "type": "string", "description": "检索到的知识库上下文", "required": true, "default": "" }
> }
> ```

> **索引**: `idx_category`(category_id), `idx_is_system`(is_system), `idx_usage`(usage_count)

---

#### 4.1.6 `pt_template_category` — 模版-知识库分类关联表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | |
| template_id | BIGINT | FK → pt_template.id, CASCADE | |
| category_id | BIGINT | FK → kb_category.id, CASCADE | |

> **唯一约束**: UNIQUE(template_id, category_id)

---

#### 4.1.7 `rag_conversation` — RAG 对话会话表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | |
| user_id | BIGINT | FK → sys_user.id | |
| title | VARCHAR(255) | DEFAULT '新对话' | 对话标题 |
| template_id | BIGINT | FK → pt_template.id, NULL | 使用的模版 |
| category_ids | VARCHAR(500) | | 限定知识库范围（逗号分隔） |
| message_count | INT | DEFAULT 0 | 消息轮数 |
| status | ENUM('active','ended') | DEFAULT 'active' | |
| created_at | DATETIME | DEFAULT NOW() | |
| updated_at | DATETIME | ON UPDATE NOW() | |
| ended_at | DATETIME | | |

> **索引**: `idx_user`(user_id), `idx_status`(status)

---

#### 4.1.8 `rag_message` — RAG 对话消息表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | |
| conversation_id | BIGINT | FK → rag_conversation.id, CASCADE | |
| role | ENUM('user','assistant','system') | NOT NULL | |
| question | TEXT | | 用户问题 (user消息时) |
| answer | TEXT | | 助手回答 (assistant消息时) |
| prompt_full | TEXT | | 实际发送的完整 prompt |
| retrieved_chunks | JSON | | 检索到的分块信息 |
| sources | JSON | | 来源文档信息 |
| model_name | VARCHAR(100) | | 使用的模型 |
| token_usage | JSON | | Token 用量 |
| response_time_ms | INT | | 响应时间(毫秒) |
| feedback | ENUM('positive','negative') | NULL | 用户反馈 |
| feedback_comment | TEXT | | 反馈备注 |
| error_message | TEXT | | 错误信息 |
| created_at | DATETIME | DEFAULT NOW() | |

> `retrieved_chunks` JSON 结构:
> ```json
> [
>   { "chunk_id": "abc123", "document_id": 1, "title": "员工手册",
>     "text": "请假流程...", "score": 0.92 }
> ]
> ```

> `sources` JSON 结构:
> ```json
> [
>   { "document_id": 1, "title": "员工手册", "file_name": "handbook.pdf",
>     "relevance_score": 0.92 }
> ]
> ```

> `token_usage` JSON 结构:
> ```json
> { "prompt_tokens": 1500, "completion_tokens": 300, "total_tokens": 1800 }
> ```

> **索引**: `idx_conversation`(conversation_id), `idx_created`(created_at)

---

#### 4.1.9 `sys_operation_log` — 操作日志表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | |
| user_id | BIGINT | FK → sys_user.id, NULL | |
| username | VARCHAR(50) | | 操作人用户名（冗余） |
| action | VARCHAR(100) | NOT NULL | 操作类型 |
| module | VARCHAR(100) | | 操作模块 |
| target_type | VARCHAR(50) | | 目标类型 |
| target_id | VARCHAR(100) | | 目标ID |
| detail | JSON | | 操作详情 |
| ip_address | VARCHAR(50) | | |
| user_agent | VARCHAR(500) | | |
| status | VARCHAR(20) | DEFAULT 'success' | success / failed |
| error_info | TEXT | | 错误信息 |
| created_at | DATETIME | DEFAULT NOW() | |

> **索引**: `idx_user`(user_id), `idx_module`(module), `idx_created`(created_at)

---

#### 4.1.10 `sys_config` — 系统配置表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | |
| config_key | VARCHAR(100) | UNIQUE, NOT NULL | 配置键 |
| config_value | TEXT | | 配置值 |
| config_type | VARCHAR(50) | DEFAULT 'string' | string / json / number |
| description | VARCHAR(255) | | 配置说明 |
| updated_by | BIGINT | FK → sys_user.id | |
| updated_at | DATETIME | ON UPDATE NOW() | |
| created_at | DATETIME | DEFAULT NOW() | |

> 预置配置项:
> - `default_model`: 默认 LLM 模型名
> - `chunk_size`: 文档分块大小 (默认 512)
> - `chunk_overlap`: 分块重叠大小 (默认 64)
> - `top_k`: 检索返回数 (默认 5)
> - `similarity_threshold`: 相似度阈值 (默认 0.7)
> - `max_context_tokens`: 上下文最大 Token 数
> - `upload_max_size_mb`: 上传文件大小上限

---

### 4.2 Chroma 向量库

#### Collection: `document_chunks`

```
{
  "id": "自动生成UUID",
  "document": "分块文本内容 (用于 Embedding)",
  "embedding": "[float array] — 由 embedding模型自动生成",
  "metadata": {
    "document_id": 1,
    "document_title": "员工手册",
    "chunk_index": 0,
    "category_id": 1,
    "category_name": "人事制度",
    "file_name": "handbook.pdf",
    "file_type": "pdf",
    "chunk_hash": "abc123...",
    "created_at": "2026-08-05T..."
  }
}
```

> 检索时按 `category_id` 做 metadata 过滤，限定知识库范围。

---

### 4.3 Neo4j 图数据库

#### 节点标签

| 标签 | 属性 | 说明 |
|------|------|------|
| `Entity` | `name, type(Person/Org/Term/Product/...), description, aliases` | 知识实体 |
| `Document` | `document_id, title, file_name` | 文档节点（映射 MySQL） |
| `Category` | `category_id, name` | 分类节点 |

#### 关系类型

| 关系 | 方向 | 属性 | 说明 |
|------|------|------|------|
| `BELONGS_TO` | (Document)→(Category) | | 文档归属分类 |
| `MENTIONS` | (Document)→(Entity) | `count, positions` | 文档提及某实体 |
| `RELATED_TO` | (Entity)→(Entity) | `weight, relation_type` | 实体间关系 |
| `SIMILAR_TO` | (Document)→(Document) | `score` | 文档相似度 |

#### 示例图谱查询

```cypher
// 查询与"请假"相关的所有实体及其关系
MATCH (e:Entity)-[r:RELATED_TO]-(other:Entity)
WHERE e.name CONTAINS '请假'
RETURN e, r, other

// 查询某文档涉及的所有实体
MATCH (d:Document {document_id: 1})-[:MENTIONS]->(e:Entity)
RETURN e

// 查询两个实体之间的所有路径
MATCH path = (a:Entity {name: '年假'})-[*1..3]-(b:Entity {name: '考勤'})
RETURN path
```

---

## 五、ER 关系图（文字版）

```
sys_user 1──N kb_document       (uploaded_by)
sys_user 1──N pt_template       (created_by)
sys_user 1──N rag_conversation  (user_id)
sys_user 1──N sys_operation_log (user_id)

kb_category 1──N kb_document    (category_id)
kb_category 1──N pt_template    (category_id)
kb_category 1──N kb_category    (parent_id, 自引用)

kb_document 1──N kb_document_chunk (document_id)

pt_template N──M kb_category    (pt_template_category)

rag_conversation 1──N rag_message (conversation_id)
rag_conversation N──1 pt_template (template_id)
rag_conversation N──1 sys_user    (user_id)
```

---

## 六、API 接口设计（概要）

### 6.1 认证模块 `/api/v1/auth`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/register` | 注册 |
| POST | `/api/v1/auth/login` | 登录（返回 JWT） |
| POST | `/api/v1/auth/logout` | 注销 |
| GET | `/api/v1/auth/me` | 获取当前用户信息 |
| PUT | `/api/v1/auth/password` | 修改密码 |

### 6.2 用户管理 `/api/v1/users`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/users/` | 用户列表（管理员） |
| GET | `/api/v1/users/{id}` | 用户详情 |
| PUT | `/api/v1/users/{id}` | 更新用户信息 |
| PUT | `/api/v1/users/{id}/status` | 启用/禁用 |

### 6.3 知识库分类 `/api/v1/categories`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/categories/` | 分类列表（树形） |
| POST | `/api/v1/categories/` | 创建分类 |
| PUT | `/api/v1/categories/{id}` | 更新分类 |
| DELETE | `/api/v1/categories/{id}` | 删除分类 |

### 6.4 文档管理 `/api/v1/documents`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/documents/` | 文档列表（分页+筛选） |
| POST | `/api/v1/documents/upload` | 上传文档 |
| GET | `/api/v1/documents/{id}` | 文档详情 |
| GET | `/api/v1/documents/{id}/download` | 下载文档 |
| DELETE | `/api/v1/documents/{id}` | 删除文档 |
| POST | `/api/v1/documents/{id}/vectorize` | 触发向量化 |
| POST | `/api/v1/documents/batch-vectorize` | 批量向量化 |
| GET | `/api/v1/documents/{id}/chunks` | 查看分块列表 |

### 6.5 提示词模版 `/api/v1/templates`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/templates/` | 模版列表 |
| POST | `/api/v1/templates/` | 创建模版 |
| GET | `/api/v1/templates/{id}` | 模版详情 |
| PUT | `/api/v1/templates/{id}` | 更新模版 |
| DELETE | `/api/v1/templates/{id}` | 删除模版 |
| GET | `/api/v1/templates/by-category/{category_id}` | 按分类获取模版 |
| GET | `/api/v1/templates/popular` | 热门模版 |

### 6.6 RAG 问答 `/api/v1/rag`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/rag/chat` | 发起问答（支持流式 SSE） |
| POST | `/api/v1/rag/chat-stream` | 流式问答 |
| GET | `/api/v1/rag/conversations/` | 我的对话列表 |
| POST | `/api/v1/rag/conversations/` | 新建对话 |
| GET | `/api/v1/rag/conversations/{id}` | 对话详情（含消息） |
| DELETE | `/api/v1/rag/conversations/{id}` | 删除对话 |
| PUT | `/api/v1/rag/conversations/{id}/title` | 修改对话标题 |
| POST | `/api/v1/rag/messages/{id}/feedback` | 回答反馈 |

### 6.7 知识图谱 `/api/v1/graph`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/graph/entities/` | 实体列表 |
| GET | `/api/v1/graph/entities/{name}` | 实体详情+关系 |
| GET | `/api/v1/graph/search` | 图谱搜索 |
| POST | `/api/v1/graph/build` | 触发图谱构建 |

### 6.8 管理后台 `/api/v1/admin`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/dashboard` | 统计面板数据 |
| GET | `/api/v1/admin/logs` | 操作日志 |
| GET | `/api/v1/admin/configs` | 系统配置列表 |
| PUT | `/api/v1/admin/configs/{key}` | 更新配置 |

---

## 七、前端页面路由设计

```
/login                          # 登录页
/register                       # 注册页
/layout                         # 主布局（含侧边栏）
  /dashboard                    # 数据看板
  /knowledge
    /categories                 # 知识库分类管理
    /documents                  # 文档列表（含上传、搜索）
    /documents/upload           # 上传文档
    /documents/:id              # 文档详情
  /templates                    # 提示词模版列表
    /templates/create           # 新建模版
    /templates/:id/edit         # 编辑模版
  /chat
    /                           # 对话主界面（含历史侧边栏）
    /:conversationId            # 指定对话
  /graph                        # 知识图谱可视化
  /profile                      # 个人信息
  /admin
    /users                      # 用户管理
    /logs                       # 操作日志
    /config                     # 系统配置
```

---

## 八、RAG 核心流程

```
用户提问
  │
  ▼
1. 选择提示词模版（可选）
  │  → 填充模版变量
  │  → 叠加知识库分类过滤条件
  │
  ▼
2. Query 改写 / 扩展 (LlamaIndex)
  │  → HyDE (假设文档嵌入) 或 多查询生成
  │
  ▼
3. 向量检索 (ChromaDB)
  │  → 相似度搜索 + 分类元数据过滤
  │  → 返回 Top-K 文档分块
  │
  ▼
4. (可选) 知识图谱增强
  │  → Neo4j 检索相关实体 & 关系
  │  → 补充额外上下文
  │
  ▼
5. 上下文组装
  │  → 拼接检索到的分块文本
  │  → 组装最终 Prompt
  │
  ▼
6. LLM 生成 (流式)
  │  → 返回答案 + 引用来源
  │
  ▼
7. 后处理
  │  → 保存对话记录
  │  → 记录 Token 用量
  │  → 记录反馈
```

---

## 九、项目目录结构

```
eakb/
├── docker-compose.yml              # MySQL + Neo4j + MinIO
├── .env.example                    # 环境变量模版
├── README.md
├── DESIGN.md                       # 本文件
├── CLAUDE.md
│
├── backend/
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI 入口 + 生命周期
│   │   ├── config.py               # Pydantic Settings
│   │   ├── dependencies.py         # 依赖注入 (get_db, get_current_user)
│   │   │
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── deps.py             # API 公共依赖
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── router.py       # 汇总路由
│   │   │       ├── auth.py
│   │   │       ├── users.py
│   │   │       ├── categories.py
│   │   │       ├── documents.py
│   │   │       ├── templates.py
│   │   │       ├── conversations.py
│   │   │       ├── rag.py
│   │   │       ├── graph.py
│   │   │       └── admin.py
│   │   │
│   │   ├── models/                 # SQLAlchemy ORM 模型
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # 基类 (id, created_at, updated_at)
│   │   │   ├── user.py
│   │   │   ├── category.py
│   │   │   ├── document.py
│   │   │   ├── document_chunk.py
│   │   │   ├── template.py
│   │   │   ├── conversation.py
│   │   │   ├── message.py
│   │   │   ├── operation_log.py
│   │   │   └── system_config.py
│   │   │
│   │   ├── schemas/                # Pydantic 请求/响应模型
│   │   │   ├── __init__.py
│   │   │   ├── common.py           # 公共 (PageResponse, APIResponse)
│   │   │   ├── auth.py
│   │   │   ├── user.py
│   │   │   ├── category.py
│   │   │   ├── document.py
│   │   │   ├── template.py
│   │   │   ├── conversation.py
│   │   │   ├── rag.py
│   │   │   └── graph.py
│   │   │
│   │   ├── services/               # 业务逻辑层
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py
│   │   │   ├── user_service.py
│   │   │   ├── category_service.py
│   │   │   ├── document_service.py
│   │   │   ├── template_service.py
│   │   │   ├── conversation_service.py
│   │   │   ├── rag_service.py      # RAG 核心编排
│   │   │   ├── embedding_service.py # 向量化服务
│   │   │   ├── minio_service.py     # MinIO 文件操作
│   │   │   ├── graph_service.py     # Neo4j 图谱操作
│   │   │   ├── dashboard_service.py # 统计面板
│   │   │   └── log_service.py
│   │   │
│   │   ├── core/                   # 基础设施
│   │   │   ├── __init__.py
│   │   │   ├── security.py         # JWT + 密码哈希
│   │   │   ├── database.py         # SQLAlchemy engine + session
│   │   │   ├── chroma_client.py    # ChromaDB 客户端封装
│   │   │   ├── neo4j_client.py     # Neo4j 驱动封装
│   │   │   ├── minio_client.py     # MinIO 客户端封装
│   │   │   └── llm.py              # LLM 配置 (LlamaIndex Settings)
│   │   │
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── file_parser.py      # PDF/DOCX/TXT/MD 解析
│   │       ├── text_splitter.py    # 文档分块工具
│   │       ├── response.py         # 统一响应封装
│   │       └── exceptions.py       # 自定义异常
│   │
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_auth.py
│       ├── test_documents.py
│       └── test_rag.py
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── index.html
│   ├── .env.development
│   ├── .env.production
│   │
│   ├── src/
│   │   ├── main.ts                 # 入口
│   │   ├── App.vue
│   │   ├── env.d.ts                # 类型声明
│   │   │
│   │   ├── router/
│   │   │   └── index.ts            # 路由配置 + 守卫
│   │   │
│   │   ├── stores/                  # Pinia 状态管理
│   │   │   ├── index.ts
│   │   │   ├── auth.ts             # 用户认证状态
│   │   │   ├── knowledge.ts        # 知识库状态
│   │   │   ├── chat.ts             # 对话状态
│   │   │   └── app.ts              # 全局状态 (侧边栏、主题)
│   │   │
│   │   ├── api/                    # Axios 请求封装
│   │   │   ├── request.ts          # Axios 实例 (拦截器、JWT)
│   │   │   ├── auth.ts
│   │   │   ├── user.ts
│   │   │   ├── category.ts
│   │   │   ├── document.ts
│   │   │   ├── template.ts
│   │   │   ├── conversation.ts
│   │   │   └── rag.ts
│   │   │
│   │   ├── views/                   # 页面组件
│   │   │   ├── login/
│   │   │   │   └── LoginView.vue
│   │   │   ├── register/
│   │   │   │   └── RegisterView.vue
│   │   │   ├── dashboard/
│   │   │   │   └── DashboardView.vue
│   │   │   ├── knowledge/
│   │   │   │   ├── CategoryManage.vue
│   │   │   │   ├── DocumentList.vue
│   │   │   │   ├── DocumentUpload.vue
│   │   │   │   └── DocumentDetail.vue
│   │   │   ├── template/
│   │   │   │   ├── TemplateList.vue
│   │   │   │   └── TemplateForm.vue   # 新建/编辑共用
│   │   │   ├── chat/
│   │   │   │   ├── ChatView.vue       # 对话主容器
│   │   │   │   ├── ChatSidebar.vue    # 历史会话列表
│   │   │   │   ├── ChatMain.vue       # 消息展示区
│   │   │   │   ├── ChatInput.vue      # 输入区（含模版选择）
│   │   │   │   └── SourcePanel.vue    # 来源引用面板
│   │   │   ├── graph/
│   │   │   │   └── GraphView.vue
│   │   │   ├── profile/
│   │   │   │   └── ProfileView.vue
│   │   │   └── admin/
│   │   │       ├── UserManage.vue
│   │   │       ├── LogList.vue
│   │   │       └── SystemConfig.vue
│   │   │
│   │   ├── components/              # 通用组件
│   │   │   ├── common/
│   │   │   │   ├── Pagination.vue
│   │   │   │   ├── SearchBar.vue
│   │   │   │   ├── ConfirmDialog.vue
│   │   │   │   └── FileUploader.vue
│   │   │   ├── layout/
│   │   │   │   ├── AppLayout.vue
│   │   │   │   ├── SidebarMenu.vue
│   │   │   │   ├── TopHeader.vue
│   │   │   │   └── BreadcrumbNav.vue
│   │   │   └── chat/
│   │   │       ├── MessageBubble.vue
│   │   │       ├── TemplateSelector.vue
│   │   │       ├── CategoryFilter.vue
│   │   │       └── FeedbackButtons.vue
│   │   │
│   │   ├── composables/             # 组合式函数
│   │   │   ├── useAuth.ts
│   │   │   ├── usePagination.ts
│   │   │   ├── useFileUpload.ts
│   │   │   └── useSSE.ts            # SSE 流式接收
│   │   │
│   │   ├── types/                   # TypeScript 类型定义
│   │   │   ├── user.ts
│   │   │   ├── document.ts
│   │   │   ├── template.ts
│   │   │   ├── chat.ts
│   │   │   └── common.ts
│   │   │
│   │   ├── utils/
│   │   │   ├── storage.ts           # localStorage 封装
│   │   │   └── format.ts            # 日期/文件大小格式化
│   │   │
│   │   └── styles/
│   │       ├── index.less           # 全局样式入口
│   │       ├── variables.less       # Less 变量
│   │       ├── mixins.less          # Less 混入
│   │       ├── reset.less           # 样式重置
│   │       └── element-override.less # ElementPlus 定制
│   │
│   └── public/
│       └── favicon.ico
│
└── docs/
    ├── api-reference.md             # API 详细文档
    └── deployment.md                # 部署文档
```

---

## 十、关键设计要点

### 10.1 提示词模版系统

模版使用示例（变量用 `{{ }}` 包裹）：

```
# 角色
你是一个{{company}}公司的企业知识库助手，专注于回答{{category_name}}相关问题。

# 参考知识库
以下是相关知识库内容：
{{context}}

# 要求
1. 基于上述知识库内容回答问题，不得编造
2. 如果知识库中没有相关信息，请明确告知用户
3. 回答需简洁、准确、结构化
4. 引用来源时标注文档名称

# 用户问题
{{question}}
```

用户选择模版后，只需输入问题，系统自动填充 `{{context}}`（检索结果）和 `{{question}}`。

### 10.2 文档处理流水线

```
上传文件 → MinIO 存储 → 异步任务: 解析文本 → 分块 → Embedding → 存入 Chroma
                                                     ↓
                                                 记录分块信息到 MySQL
                                                     ↓
                                                 实体抽取 → Neo4j (可选)
```

使用 **LlamaIndex** 的 `SimpleDirectoryReader` + `IngestionPipeline` 完成。

### 10.3 流式回答 (SSE)

- 前端通过 `EventSource` / `fetch` + `ReadableStream` 接收 SSE 事件
- 后端使用 `StreamingResponse` 逐 Token 返回
- LlamaIndex 原生的 `StreamingResponse` 支持

### 10.4 安全设计

- JWT Token 鉴权（access_token + refresh_token）
- 密码 bcrypt 哈希
- 文件上传类型/大小校验
- SQL 注入防护（ORM 参数化查询）
- CORS 配置
- API 限流（可选）

---

## 十一、开发阶段建议

| 阶段 | 内容 | 目标 |
|------|------|------|
| **Phase 1** | 项目初始化：Docker 环境、FastAPI 骨架、Vue3 骨架、数据库迁移 | 跑通基础框架 |
| **Phase 2** | 用户认证模块：注册、登录、JWT、个人信息管理 | 完成认证闭环 |
| **Phase 3** | 知识库管理：分类 CRUD + 文档上传/管理 + MinIO + 向量化 | 知识库闭环 |
| **Phase 4** | 提示词模版：模版 CRUD + 分类关联 | 模版体系建立 |
| **Phase 5** | RAG 核心：对话问答 + 流式回答 + 来源引用 | 核心功能交付 |
| **Phase 6** | 知识图谱：实体抽取 + 图谱可视化 | 增强检索 |
| **Phase 7** | 管理后台：统计看板 + 日志 + 系统配置 | 管理闭环 |
| **Phase 8** | 优化完善：异常处理、性能优化、文档、测试 | 交付标准 |

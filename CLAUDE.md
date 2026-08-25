## 项目基础信息

### 项目名称

企业知识库智能助手（EAKB Enterprise AI Knowledge Base）

### 技术栈总览

#### 后端

- 运行环境：Ubuntu 26.04，Python 3.14.4
- Web 框架：FastAPI
- ORM：SQLAlchemy + Alembic（数据库迁移）
- RAG 编排核心：LlamaIndex
- 向量数据库：ChromaDB
- 图数据库：Neo4j 5.x
- 关系数据库：MySQL 8.0
- 对象存储：MinIO
- 安全鉴权：JWT + bcrypt 密码哈希
- 文件解析：PDF/DOCX/TXT/MD/XLSX 通用解析器
- 流式输出：FastAPI StreamingResponse / SSE

#### 前端

- 框架：Vue3 + TypeScript
- UI 组件：Element Plus
- 状态管理：Pinia
- 路由：VueRouter
- 请求：Axios + SSE（EventSource）
- 构建工具：Vite
- 样式：Less

#### 容器化环境

Docker Compose 一键拉起依赖服务：MySQL 8.0、Neo4j 5.x、MinIO

### 项目核心定位

基于 RAG 检索增强生成技术，面向企业内部员工的私有知识库问答系统，支持文档上传解析、向量检索、多轮对话、自定义提示词模板、知识图谱增强检索、后台数据管控全流程能力。

## 一、开发环境统一规范

### 1. 系统与 Python 版本强制约束

- 操作系统：Ubuntu 26.04
- Python 版本：3.14.4（项目所有后端代码、依赖、虚拟环境统一使用该版本，不兼容其他 Python 主版本）
- 包管理：pip + venv 虚拟环境，禁止全局安装项目依赖
- 代码格式化：ruff（格式化 + lint）
- 类型校验：mypy（全后端 TS 风格强类型约束）

### 2. 后端虚拟环境初始化脚本（Ubuntu 26.04）

```
# 安装系统依赖
sudo apt update && sudo apt install -y python3.14 python3.14-dev python3.14-venv build-essential libmysqlclient-dev poppler-utils libreoffice

# 进入backend目录
cd backend
# 创建专属3.14虚拟环境
python3.14 -m venv .venv
# 激活环境
source .venv/bin/activate
# 升级pip
pip install --upgrade pip setuptools wheel
# 安装项目依赖
pip install -r requirements.txt
```

### 3. 环境变量规范

项目根目录提供 `.env.example`，开发 / 部署复制为 `.env`，禁止提交真实密钥到代码仓库
关键环境变量分类：

1. 数据库配置：MySQL 连接地址、账号密码、库名
2. Chroma 向量库：持久化存储路径、嵌入模型路径 / API 地址
3. Neo4j 图谱库：bolt 地址、账号密码
4. MinIO 对象存储：API 地址、控制台地址、access/secret 密钥、存储桶名
5. LLM 配置：模型名称、API Key、接口地址、上下文限制、分块参数（chunk_size、overlap、top_k、相似度阈值）
6. JWT 鉴权：密钥、过期时长、刷新 Token 配置
7. 文件上传：最大上传尺寸、允许文件后缀白名单
8. 服务基础配置：后端监听端口、跨域白名单、日志级别

### 4. Docker 服务端口对照表

表格

| 服务 | 端口 | 访问用途 |
| --- | --- | --- |
| MySQL 8.0 | 3306 | 业务关系数据读写 |
| Neo4j 5.x | 7474(HTTP) / 7687(Bolt) | 图谱可视化页面、程序连接 |
| MinIO | 9000(API) / 9001(Console) | 文件上传接口、管理控制台 |

## 二、代码分层架构规范（后端强制遵守）

### 目录分层职责（backend/app）

1. **core/** 基础设施层（无业务逻辑，全局通用客户端、安全、数据库连接）
   - security.py：JWT 签发 / 校验、bcrypt 密码加密
   - database.py：SQLAlchemy 引擎、会话工厂
   - chroma_client.py：Chroma 向量库单例封装
   - neo4j_client.py：Neo4j 驱动连接封装
   - minio_client.py：MinIO 存储操作封装
   - llm.py：LlamaIndex 全局 Settings、LLM/Embedding 初始化
2. **models/** ORM 数据模型（仅数据库表映射，无业务代码）
所有 MySQL 表一一对应，字段、索引、外键与 DESIGN.md 完全对齐，使用 Alembic 管理迁移脚本
3. **schemas/** Pydantic 请求 / 响应模型（入参校验、出参序列化）
区分 Create/Update/Response/Page 通用分页结构，统一全局返回体 `APIResponse`
4. **utils/** 工具函数（纯工具，不操作数据库、不调用外部服务）
文件解析、文本分割、统一异常、响应格式化、哈希计算、日期工具
5. **services/** 业务逻辑层（核心业务处理，所有数据库、第三方服务调用收敛在此）
每个模块独立 Service，路由仅调用 Service，禁止路由内写业务逻辑
6. **api/v1/** 路由层（仅参数接收、鉴权、调用 service、返回数据）
职责单一：接收 HTTP 请求、参数校验、依赖注入、调用对应服务、返回标准化 JSON
7. **dependencies.py** 全局依赖注入：登录鉴权、分页参数、权限校验（admin/employee）
8. **main.py** 项目入口：生命周期事件、全局中间件、异常捕获、路由挂载、SSE 流式配置

### 三层调用强制规则

路由 (api) → 服务 (service) → core 客户端 /models 数据库操作
禁止跨层逆向调用，禁止路由直接操作数据库 / 向量库 / MinIO

## 三、数据库设计规范

### MySQL 约束规则

1. 主键统一 BIGINT 自增 id，所有业务表必须包含 `created_at`、`updated_at`
2. 软删除统一使用 status 字段：1 正常、0 草稿、-1 删除，禁止物理删除业务文档
3. 外键统一设置级联删除 / 空值策略，关联查询必须建立对应索引（与 DESIGN.md 索引保持一致）
4. JSON 类型字段统一使用 Pydantic 模型序列化 / 反序列化，不裸操作 JSON 字符串
5. 枚举字段使用数据库 ENUM 约束，代码内同步定义枚举类保持一致

### Chroma 向量库规范

- 唯一集合 `document_chunks`，所有文档分块统一存储
- metadata 必须携带：document_id、category_id、分块索引、文档基础信息，用于检索过滤
- 分块文本哈希 `chunk_hash` 用于去重，避免重复向量化

### Neo4j 知识图谱规范

固定三类节点：Entity 实体、Document 文档、Category 分类
固定关系：BELONGS_TO、MENTIONS、RELATED_TO、SIMILAR_TO
实体抽取仅在文档向量化完成后异步执行，支持手动触发重建图谱

## 四、功能模块开发规范

### 1. 用户认证模块 Auth

- 登录签发 access_token+refresh_token，接口鉴权全局依赖 `get_current_user`
- 角色区分 admin/employee，后台管理接口增加管理员权限校验依赖
- 密码存储仅存 bcrypt 哈希，接口永不返回原始密码、哈希值

### 2. 知识库分类 & 文档管理

- 分类树形结构，支持父子级递归查询、拖拽排序
- 文档上传流程：校验后缀 + 大小 → MinIO 持久化 → MySQL 记录元数据 → 异步向量化任务
- 向量化状态四状态流转：pending 待处理 → processing 处理中 → completed 完成 → failed 失败
- 批量向量化接口支持多选文档一键重建向量

### 3. 提示词模板系统

- 支持系统预置模板（不可删除）+ 用户自定义模板
- 模板变量固定 `{{question}}`、`{{context}}`，variables 字段 JSON 定义变量约束
- 模板多对多绑定知识库分类，问答时自动匹配对应分类默认模板

### 4. RAG 智能问答（核心模块）

标准执行流程强制固定：
用户提问 → 模板变量填充 → Query 改写扩展 → Chroma 向量检索（分类过滤）→（可选图谱增强）→ 上下文组装 Prompt → LLM 流式生成 → 存储对话消息、统计 Token、记录来源引用

1. 流式输出统一使用 SSE 接口 `/api/v1/rag/chat-stream`
2. 每条消息存储检索分块、来源文档、token 消耗、响应耗时、用户点赞 / 点踩反馈
3. 回答必须携带文档来源引用，无知识库匹配内容禁止编造答案

### 5. 知识图谱模块

- 文档上传 / 重向量化后自动抽取实体，支持后台手动全量重建图谱
- 提供实体搜索、关联关系查询、可视化数据接口
- 问答时可选启用图谱增强，补充实体关联信息丰富上下文

### 6. 管理后台模块

- 数据看板聚合：用户总数、文档总量、问答会话量、今日访问统计
- 操作日志全模块埋点，记录操作人、模块、操作内容、IP、执行结果
- 系统配置统一存储 sys_config 表，后端全局读取，管理员页面可视化修改

## 五、接口开发规范

### 统一响应格式（全局拦截封装）

成功返回示例：

```
{
  "code": 200,
  "msg": "success",
  "data": { ...业务数据... }
}
```

分页统一包裹 PageResponse 结构，携带 total/page/page_size/pages
错误返回统一错误码、错误信息、详细堆栈（开发环境）

### HTTP 方法语义强制规范

- GET：查询列表 / 详情，无数据变更
- POST：新增、异步任务、批量操作、登录、问答流式接口
- PUT：全量更新资源
- DELETE：删除资源（软删为主）

### 鉴权规则

除登录、注册接口外，全部接口必须携带 Authorization: Bearer {token}
后台 admin 接口增加角色校验，普通员工禁止访问用户管理、系统配置接口

## 六、前端开发规范

1. 路由与 DESIGN.md 路由表严格对齐，路由守卫统一校验登录状态、角色权限
2. 状态管理使用 Pinia 拆分模块：auth、knowledge、chat、app 全局状态
3. 文件上传封装通用 FileUploader 组件，统一校验文件格式大小
4. SSE 流式对话封装 useSSE 组合式函数，统一处理消息分片、异常断开重连
5. 页面组件分层：页面容器、通用业务组件、基础公共组件，禁止业务代码耦合在公共基础组件
6. TypeScript 完整类型定义，所有接口请求 / 返回结构统一 types 目录声明

## 七、异步任务与流水线规范

文档处理为异步流水线，同步接口仅做任务下发，实际解析、分块、向量化、实体抽取后台执行：

1. 文件存储 MinIO
2. 文本解析提取纯文本
3. 文本分块（读取系统配置 chunk_size/chunk_overlap）
4. 生成 Embedding 写入 Chroma
5. MySQL 同步更新 vector_status、chunk_count、分块记录表
6. 可选：实体抽取写入 Neo4j 图谱
任务失败更新状态为 failed，保留错误日志支持重新触发向量化

## 八、安全强制规范

1. 所有用户输入参数校验，文件上传后缀白名单，拦截可执行脚本
2. ORM 参数化查询杜绝 SQL 注入，前端输入转义避免 Prompt 注入
3. CORS 仅放行配置内前端域名，禁止 * 全跨域
4. 敏感配置（密钥、数据库密码、LLM Key）仅通过环境变量注入，不硬编码
5. 接口限流可配置开启，防止高频问答消耗模型资源
6. 所有用户操作写入操作日志，不可删除审计记录

## 九、项目开发阶段划分（对齐 DESIGN.md）

1. Phase1 基础环境搭建：Docker 依赖、前后端骨架、数据库迁移
2. Phase2 认证用户模块：登录注册 JWT、权限体系
3. Phase3 知识库基础：分类 CRUD、文档上传 MinIO、基础文档管理
4. Phase4 提示词模板模块：模板增删改查、分类关联
5. Phase5 RAG 核心问答：检索、流式对话、来源引用、对话历史
6. Phase6 知识图谱：实体抽取、图谱查询可视化、检索增强
7. Phase7 管理后台：统计看板、操作日志、系统配置
8. Phase8 优化收尾：全局异常、性能调优、单元测试、部署文档

## 十、测试规范

后端 tests 目录编写 pytest 用例，覆盖核心模块：

- 认证登录鉴权测试
- 文档上传、向量化流程测试
- RAG 问答检索、流式输出测试
- 权限边界测试（普通员工访问管理员接口拦截）
单元测试使用测试专用 MySQL/Chroma 临时库，测试完成自动销毁数据

## 十一、部署规范

1. 生产环境使用 docker-compose 完整编排所有服务，分离前后端容器
2. 生产关闭详细异常堆栈返回，日志输出至文件 / 日志收集器
3. LLM 模型服务独立部署，通过 API 调用，不本地加载大模型
4. MinIO 配置持久化存储，MySQL/Neo4j 挂载数据卷防止数据丢失
5. 前端打包静态资源，Nginx 反向代理分发，流式接口透传 SSE 长连接
6. 定时备份 MySQL、Chroma 持久化目录、MinIO 存储桶

## 十二、代码提交规范

1. 分支规范：main (生产)、dev (开发主干)、feature/xxx (功能分支)、fix/xxx (缺陷修复)
2. Commit 信息格式：`[模块] 操作描述`，示例：`[rag] 修复流式问答断流问题`
3. 提交前执行格式化校验：ruff check + mypy 类型校验，无报错方可提交
4. 禁止提交.env、虚拟环境、缓存文件、编译产物、模型权重至代码仓库

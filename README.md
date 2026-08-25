# EAKB — 企业知识库智能助手 (Enterprise AI Knowledge Base)

基于 RAG（检索增强生成）技术的企业内部私有知识库问答系统。支持文档上传解析、向量检索、多轮对话、自定义提示词模板、知识图谱增强检索与后台数据管控全流程。

## 功能清单

| 模块 | 能力 |
| --- | --- |
| 用户认证 | 注册 / 登录 / JWT 双 Token 自动续期 / 个人信息 / 修改密码，admin / employee 角色权限体系 |
| 知识库分类 | 树形分类 CRUD、父子递归查询、拖拽排序 |
| 文档管理 | 批量上传（PDF/DOCX/TXT/MD/XLSX）、SHA256 去重、MinIO 持久化、软删除、异步向量化（状态追踪 + 失败重试）、分块查看、下载 |
| 提示词模板 | 系统预置 + 自定义模板、`{{question}}`/`{{context}}` 变量、分类绑定自动匹配、渲染预览、热门统计 |
| RAG 智能问答 | SSE 流式输出、多轮对话、分类限定检索、图谱增强检索、来源引用、点赞点踩反馈、Token 统计；无知识库匹配不编造答案 |
| 知识图谱 | 实体自动抽取（文档向量化后异步执行）、实体搜索 / 关联查询 / 可视化数据、问答图谱增强 |
| 管理后台 | 数据看板（6 项统计）、用户管理（含批量操作）、操作日志（审计只读）、系统配置（实时生效） |
| 平台能力 | 统一响应/异常格式、接口限流（sys_config 开关）、操作日志全模块埋点、全局加载提示、SSE 断线重连 |

## 技术栈

- **后端**：Python 3.14 + FastAPI + SQLAlchemy(async) + Alembic + LlamaIndex + ChromaDB + Neo4j 5 + MySQL 8 + MinIO + JWT/bcrypt；质量工具 ruff + mypy + pytest
- **前端**：Vue 3 + TypeScript + Element Plus + Pinia + VueRouter + Vite + Less；SSE 用 fetch + ReadableStream（携带 Bearer 头）
- **LLM**：OpenAI 兼容接口（默认 DeepSeek V4）；Embedding 默认本地 bge-large-zh-v1.5（可切远端接口）
- **依赖服务**：MySQL 8.0 / Neo4j 5.x / MinIO 由 Docker Compose 一键拉起

## 目录结构

```
eakb/
├── backend/                 # FastAPI 后端 (app/core|models|schemas|utils|services|api 分层)
│   ├── alembic/             # 数据库迁移 (0001~0006)
│   ├── tests/               # pytest 用例 (约 130 个)
│   └── requirements.txt
├── frontend/                # Vue3 + TS 前端 (views|components|composables|stores|api|types)
├── docs/                    # 文档: DESIGN / api-reference / deployment / 各阶段测试指南
├── scripts/                 # init_ubuntu / run_tests / check_quality / format_code / backup
├── deploy/                  # Nginx 反代配置样例
├── docker-compose.yml       # 开发: 中间件编排 (MySQL/Neo4j/MinIO)
├── docker-compose.prod.yml  # 生产: 完整编排 (+后端/前端容器)
└── .env.example             # 环境变量模板
```

## 开发启动步骤

### 1. 依赖服务

```bash
sudo docker compose up -d          # MySQL(3306) / Neo4j(7474,7687) / MinIO(9000,9001)
```

### 2. 后端

```bash
cd backend
python3.14 -m venv venv && source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install torch --index-url https://download.pytorch.org/whl/cpu   # 先装 CPU 版 torch
pip install -r requirements.txt

cp ../.env.example ../.env          # 修改 LLM_API_KEY / JWT_SECRET_KEY 等
alembic upgrade head                # 建表 + 种子配置
uvicorn app.main:app --reload --port 8000
```

### 3. 前端

```bash
cd frontend
npm install
npm run dev                         # http://localhost:5173 (代理 /api → 8000)
```

## 账号初始化

- 数据库迁移后访问注册接口创建账号（默认角色 employee），或用接口创建：
  `POST /api/v1/auth/register` `{"username":"zhangsan","password":"Abc123456","confirm_password":"Abc123456"}`
- 首个管理员：注册后由管理员在「用户管理」中把角色改为 admin（或直接改库 `UPDATE sys_user SET role='admin' WHERE username='zhangsan';`）
- 管理员登录后进入「数据看板」，普通员工登录后进入「智能问答」

## 测试与质量

```bash
bash scripts/run_tests.sh        # pytest 全量（排除 Neo4j 集成测试; --include-neo4j 可含）
bash scripts/check_quality.sh    # ruff format --check + ruff check + mypy (提交前必过)
bash scripts/format_code.sh      # ruff 自动格式化修复
```

⚠️ VM 上 `--fix` 修改过的文件需拷回 Windows 端，避免单向同步覆盖回退。

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [docs/DESIGN.md](docs/DESIGN.md) | 总体设计方案（架构/表结构/API/路由/RAG 流程） |
| [docs/api-reference.md](docs/api-reference.md) | 全部 API 接口文档（入参/出参/错误码/SSE 协议） |
| [docs/deployment.md](docs/deployment.md) | 生产部署（容器编排/裸机+Nginx/备份/日志/安全检查） |
| [docs/phase8-test-guide.md](docs/phase8-test-guide.md) | Phase 8 验收测试指南与交付清单 |
| docs/phase2~7 指南 | 各阶段自测记录（含已知边界） |

## 生产部署

见 [docs/deployment.md](docs/deployment.md)。两条路径：`docker-compose.prod.yml` 完整容器编排，或裸机 uvicorn + systemd + Nginx。数据备份用 `scripts/backup.sh` + crontab。

## 开发规范

分层架构（api → service → core/models）、提交规范（`[模块] 操作描述`）、ruff+mypy 校验通过方可提交，详见 [CLAUDE.md](CLAUDE.md)。

# Phase 6 知识图谱增强检索模块 — 测试流程

覆盖：Neo4j 约束初始化、实体抽取（DeepSeek JSON 直连）、图谱构建（全量/单文档/权限边界）、实体列表/详情/搜索/画布全景、SIMILAR_TO 相似边、图谱增强 RAG（开关切换）、文档软删除图谱同步、前端图谱可视化页面。

## 0. 前置条件

```bash
# 1) 启动依赖服务 (MySQL / Neo4j / MinIO)
#    ⚠️ 必须在项目根目录执行 (docker-compose.yml 所在位置)
cd ~/eakb
sudo docker compose up -d

# 2) 后端虚拟环境
cd ~/eakb/backend && source venv/bin/activate

# 3) 本阶段无新增依赖、无 Alembic 迁移 (图谱状态全存 Neo4j,
#    sys_config 键无值时回退 settings 默认值, 无需建表/迁移)
#    ⚠️ 确认 LLM 模型名为 deepseek-v4-pro (旧名 deepseek-chat 已失效;
#    双 .env 陷阱: 根目录 ~/eakb/.env 覆盖 backend/.env, 要改根目录那份):
tr -d '\r' < ~/eakb/.env | grep LLM_MODEL_NAME

# 4) 启动后端 — 日志确认 Neo4j 连接与约束初始化:
#    [核心] Neo4j 连接: bolt://127.0.0.1:7687
#    [Neo4j] 连接成功: bolt://127.0.0.1:7687
#    [Neo4j] 图谱约束初始化完成
#    模型日志应为: [LLM] 模型已初始化: deepseek-v4-pro
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 5) 启动前端
cd ~/eakb/frontend && npm run dev
```

> ⚠️ Windows → VM 文件同步有滞后，执行前先确认以下新文件已在 VM 上：
>
> - `backend/app/core/neo4j_client.py`（约束补齐 + 全部写/查封装）、`core/chroma_client.py`（get_document_embeddings）、`core/llm.py`（achat_json）、`core/config.py`（DEFAULT_GRAPH_*）
> - `backend/app/services/graph_service.py`（新建）、`services/embedding_service.py`（步骤 8 钩子）、`services/document_service.py`（软删同步）、`services/config_service.py`（get_bool）、`services/rag_service.py`（步骤 3.5）
> - `backend/app/schemas/graph.py`、`api/v1/graph.py`、`api/v1/router.py`、`main.py`
> - `backend/tests/test_graph.py`、`tests/test_graph_neo4j_integration.py`
> - `frontend/src/types/graph.ts`、`api/graph.ts`、`views/graph/GraphView.vue`、`router/index.ts`、`components/layout/AppLayout.vue`

> 测试数据（VM 库中已有）：分类 1人事制度 / 2考勤管理 / 3技术文档；文档 1（考勤管理制度，含年假/加班/保密条款，在分类 2）、文档 2 有效且已向量化；文档 3/4 已软删。zhangsan / Abc123456（role=admin）。

## 0.5 单元测试

```bash
cd ~/eakb/backend && source venv/bin/activate

# 纯函数测试 (无需外部服务)
pytest tests/test_graph.py -v

# Neo4j 集成往返测试 (真实 Neo4j, 数据自清理, 不污染业务库)
NEO4J_TEST_URI=bolt://127.0.0.1:7687 NEO4J_TEST_USER=neo4j \
NEO4J_TEST_PASSWORD=neo4j123456 pytest tests/test_graph_neo4j_integration.py -v
```

## 1. 登录获取 Token

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"zhangsan","password":"Abc123456"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")
AUTH="Authorization: Bearer $TOKEN"
```

## 2. sys_config 图谱配置键播种

```bash
sudo docker exec -i eakb-mysql mysql -ueakb -peakb123456 eakb <<'SQL'
INSERT INTO sys_config (config_key, config_value, config_type, description) VALUES
  ('graph_enhance_enabled', 'false', 'string', '图谱增强RAG开关 (true/false)'),
  ('graph_entity_top_k', '5', 'number', '图谱增强单实体邻居数量上限'),
  ('graph_similarity_threshold', '0.5', 'number', '文档SIMILAR_TO余弦相似度阈值(文档质心级,实测主题交叠~0.55/无关~0.42)')
AS new
ON DUPLICATE KEY UPDATE config_value = new.config_value;
SQL
```

## 3. 图谱构建

```bash
# 3.1 全量重建 (admin) — 立即返回 "已下发", 后端日志观察:
#     [图谱] 文档 X 抽取完成: N 实体, M 关系, K 批
#     [图谱] 文档 X SIMILAR_TO 更新: N 条
#     [图谱] 全量重建完成: 2 个文档
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/graph/build -d '{}'

# 3.2 单文档重建 — 文档 1
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/graph/build -d '{"document_id": 1}'
# 预期: {"code":200, "msg":"图谱重建任务已下发 (文档 1)", ...}

# 3.3 单文档重建 — 未完成向量化的文档 → 400 (code=40000)
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/graph/build -d '{"document_id": 999}'
# 3.4 鉴权边界: 不传 Token → 401 (code=40100)
curl -s -X POST http://127.0.0.1:8000/api/v1/graph/build -d '{}'
```

> ⚠️ 抽取逐批调用 DeepSeek（每 ~2500 字符一批），全量重建耗时随文档数线性增长。
> 操作日志应出现 module=graph、action=build_graph 的记录（前端管理后台 → 操作日志可查）。

## 4. 实体查询验证

```bash
# 4.1 实体分页列表 — 应包含「年假」等实体 (mention_count 降序)
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/graph/entities/?page=1&page_size=10"

# 4.2 关键词 + 类型过滤 (别名同样可命中)
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/graph/entities/?keyword=%E5%B9%B4%E5%81%87"
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/graph/entities/?type=Policy"

# 4.3 实体详情 (name 必须 URL 编码) — 核对 neighbors (RELATED_TO 邻居)
#     与 documents (提及文档, 含 count/positions)
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/graph/entities/%E5%B9%B4%E5%81%87"

# 4.4 不存在的实体 → 404 (code=40400)
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/graph/entities/not_exist"
```

Neo4j Browser 对照（http://192.168.1.80:7474，neo4j / neo4j123456）：

```cypher
MATCH (d:Document)-[m:MENTIONS]->(e:Entity) RETURN d.title, e.name, e.type, m.count LIMIT 20;
MATCH (a:Entity)-[r:RELATED_TO]->(b:Entity) RETURN a.name, b.name, r.relation_type, r.weight LIMIT 20;
MATCH (d:Document)-[:BELONGS_TO]->(c:Category) RETURN d.title, c.name;
```

## 5. 图谱搜索 / 画布全景

```bash
# 5.1 全景 (无 keyword) — nodes 三类节点 (id 约定: Entity=name,
#     Document=doc_{id}, Category=cat_{id}), edges 四类边, stats 六计数
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/graph/search"

# 5.2 搜索子图 — 匹配实体 + 一跳邻居 + 提及文档 (仅 RELATED_TO/MENTIONS 边)
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/graph/search?keyword=%E8%AF%B7%E5%81%87"

# 5.3 SIMILAR_TO 验证 — 全景 edges 中 edge_type=SIMILAR_TO 的边
#     score >= 0.5 (文档质心级阈值, 远低于分块级 0.7), 每文档不超过 3 条
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/graph/search" \
  | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print([e for e in d['edges'] if e['edge_type']=='SIMILAR_TO'])"
```

## 6. 图谱增强 RAG 问答

> 开关默认关闭（不强制启用）。开启后提问含实体名/别名时，上下文会追加 `[知识图谱关联]` 文本块。

```bash
# 6.1 开启开关
sudo docker exec -i eakb-mysql mysql -ueakb -peakb123456 eakb \
  -e "UPDATE sys_config SET config_value='true' WHERE config_key='graph_enhance_enabled';"

# 6.2 提问含实体名 — SSE 正常流式输出
CID=$(curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/rag/conversations/ -d '{}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['id'])")
curl -N -s -X POST http://127.0.0.1:8000/api/v1/rag/chat-stream \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"question":"年假和考勤有什么关系？","conversation_id":'$CID'}'

# 6.3 落库校验 — prompt_full 应包含 "[知识图谱关联]"
#     ⚠️ 必须加 --default-character-set=utf8mb4, 否则中文 LIKE 字面量
#     在 mysql 客户端默认字符集下匹配失败 (返回 0)
sudo docker exec -i eakb-mysql mysql --default-character-set=utf8mb4 -ueakb -peakb123456 eakb -N \
  -e "SELECT prompt_full LIKE '%知识图谱关联%' FROM rag_message ORDER BY id DESC LIMIT 1;"

# 6.4 关闭开关后再问同类问题 — prompt_full 不应包含图谱块
sudo docker exec -i eakb-mysql mysql -ueakb -peakb123456 eakb \
  -e "UPDATE sys_config SET config_value='false' WHERE config_key='graph_enhance_enabled';"

# 6.5 Neo4j 停机降级 — 问答仍正常走纯向量检索 (仅后端日志出现
#     "[RAG] 图谱增强失败, 降级纯向量检索" 或 "[Neo4j] 连接失败")
sudo docker stop eakb-neo4j
curl -N -s -X POST http://127.0.0.1:8000/api/v1/rag/chat-stream \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"question":"年假可以休几天？","conversation_id":'$CID'}'
sudo docker start eakb-neo4j
```

## 7. 文档软删除 → 图谱同步清理

```bash
# 7.1 软删除文档 2 (需先确认其存在; 删除后 Neo4j 同步清理)
curl -s -X DELETE -H "$AUTH" http://127.0.0.1:8000/api/v1/documents/2

# 7.2 Neo4j Browser 验证: 文档节点消失、孤儿实体被清
# MATCH (d:Document {document_id: 2}) RETURN d;          → 空
# MATCH (e:Entity) WHERE NOT (e)<-[:MENTIONS]-() RETURN e; → 无仅被文档2提及的实体

# 7.3 重新向量化/上传文档可重新触发抽取 (向量化完成后自动执行)
```

## 8. 前端手测清单

| 步骤 | 预期 |
| --- | --- |
| 侧边栏出现「知识图谱」菜单（智能问答下方），点击进入 /graph | 页面标题「知识图谱」，路由守卫要求登录 |
| 首次进入自动加载全景 | 力导向画布渲染，实体(蓝)/文档(橙)/分类(青)三类节点颜色 + 右上图例 + 悬停 tooltip；stats 行显示实体/文档/关系计数 |
| 搜索框输入「年假」回车 | 画布切换为子图（年假实体 + 关联实体 + 提及文档），无匹配时提示"未找到匹配实体" |
| 点击实体节点 | 右侧抽屉：类型/别名/描述/被提及次数 + 关联实体表（关系类型/权重）+ 提及文档列表 |
| 抽屉内点「展开关联」 | 邻居实体节点与 RELATED_TO 边并入当前画布（不重复添加） |
| 点击文档节点 / 分类节点 | 仅提示信息，不打开抽屉 |
| 图谱无数据时 | el-empty 提示"图谱暂无数据…文档向量化完成后将自动抽取实体" |
| admin 账号点「重建图谱」 | 二次确认框 → 确认后提示任务已下发；操作日志出现 module=graph 记录 |
| employee 账号访问 /graph | 页面正常，但无「重建图谱」按钮 |

## 9. 已知边界

- 实体名含 `/` 等路径字符时，`GET /graph/entities/{name}` 详情接口无法按路径定位（子图/全景走 keyword 参数不受影响）。
- 全量重建按文档数 × 批次串行调 LLM，文档多时耗时较长；失败批次自动丢弃，不影响其他批次。
- 图谱是 MySQL 的增强副本，任何状态漂移可通过「重建图谱」幂等恢复（MERGE + 先删旧边）。

# Phase 5 RAG 智能问答模块 — 测试流程

覆盖：对话会话 CRUD、SSE 流式问答（逐 token 输出）、分类限定检索、模板切换、无匹配禁止编造、来源引用、点赞点踩反馈、多轮上下文、操作日志、前端对话页面。

## 0. 前置条件

```bash
# 1) 启动依赖服务 (MySQL / Neo4j / MinIO)
#    ⚠️ 必须在项目根目录执行 (docker-compose.yml 所在位置),
#    在其他目录会报 "no configuration file provided"
cd ~/eakb
sudo docker compose up -d

# 2) 后端虚拟环境 (Phase 4 已装好依赖, 本阶段无新增依赖)
cd ~/eakb/backend && source venv/bin/activate

# 3) 执行 Phase 5 数据库迁移 (rag_conversation / rag_message)
alembic upgrade head
# 验证建表:
sudo docker exec -i eakb-mysql mysql -ueakb -peakb123456 eakb \
  -e "show tables like 'rag_%'; describe rag_conversation; describe rag_message;"

# 4) 启动后端 (日志确认 [LLM] 模型已初始化: deepseek-chat)
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 5) 启动前端
cd ~/eakb/frontend && npm run dev
```

> ⚠️ Windows → VM 文件同步有滞后，执行前先确认以下新文件已在 VM 上：
>
> - `backend/alembic/versions/20260816_0004_phase5_rag.py`
> - `backend/app/models/conversation.py`、`models/message.py`
> - `backend/app/schemas/conversation.py`、`schemas/rag.py`
> - `backend/app/services/conversation_service.py`、`services/rag_service.py`
> - `backend/app/api/v1/rag.py`
> - `backend/app/core/llm.py`（Phase 5 重写）、`core/chroma_client.py`（query_embeddings 修复）、`main.py`（中间件改纯 ASGI）
> - `frontend/src/types/chat.ts`、`api/conversation.ts`、`api/rag.ts`、`composables/useSSE.ts`、`stores/chat.ts`
> - `frontend/src/views/chat/`（5 个文件）、`frontend/src/components/chat/`（MessageBubble/CategoryFilter/FeedbackButtons）

> 测试数据（VM 库中已有）：分类 1人事制度 / 2考勤管理 / 3技术文档；文档 1、2 有效且已向量化。
> ⚠️ 实测数据分布：**「考勤管理制度」（doc 1，含年假/加班/保密条款）在分类 2**，
> 分类 1 下暂无与「年假」匹配的分块。命中性问题请用 `category_ids:[2]`，
> 无匹配问题用 `category_ids:[1]` 或无关问题。

## 1. 登录获取 Token

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"zhangsan","password":"Abc123456"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")
AUTH="Authorization: Bearer $TOKEN"
```

## 2. 对话会话 CRUD

```bash
# 2.1 新建对话 (带分类限定 1人事制度), 记录 CID
CID=$(curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/rag/conversations/ -d '{
    "title": "年假咨询",
    "category_ids": [1]
  }' | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['id'])")
echo "CID=$CID"

# 2.2 对话列表 — 应包含刚建的对话, category_ids=[1]
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/rag/conversations/?page=1&page_size=10"

# 2.3 对话详情 — 空消息列表
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/rag/conversations/$CID"

# 2.4 修改标题
curl -s -X PUT -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/rag/conversations/$CID/title -d '{"title":"年假政策咨询"}'

# 2.5 鉴权边界: 不传 Token → 401 (code=40100)
curl -s "http://127.0.0.1:8000/api/v1/rag/conversations/"
```

## 3. SSE 流式问答 (核心)

> curl 加 `-N` 禁用缓冲, 逐事件观察输出; 事件顺序固定为
> `meta → sources → delta* → done`。

### 3.1 基础流式问答 (指定会话)

```bash
curl -N -s -X POST http://127.0.0.1:8000/api/v1/rag/chat-stream \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"question":"年假可以休几天？","conversation_id":'$CID'}'
```

预期：
- `event: meta` — conversation_id=$CID, user_message_id 为新增用户消息 ID
- `event: sources` — sources/retrieved_chunks 包含文档 1 (员工手册类) 的分块
- 多个 `event: delta` — 逐 token 输出
- `event: done` — message_id/token_usage/response_time_ms

### 3.2 无匹配知识库内容 → 禁止编造

```bash
curl -N -s -X POST http://127.0.0.1:8000/api/v1/rag/chat-stream \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"question":"量子计算原理是什么？","conversation_id":'$CID'}'
```

预期：不调用 LLM，delta 直接输出「知识库中未找到与您问题相关的资料…」固定提示，
`sources` 为空数组，`done` 中 `token_usage` 为 null。

### 3.3 分类限定检索 (分类 2 命中 / 分类 1 不命中)

```bash
# 限定分类 2 (考勤管理, 年假条款所在) → 应命中 (sources 含「考勤管理制度」)
curl -N -s -X POST http://127.0.0.1:8000/api/v1/rag/chat-stream \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"question":"年假可以休几天？","conversation_id":'$CID',"category_ids":[2]}'

# 限定分类 1 (人事制度, 无年假分块) → 应无匹配 (sources 为空 + 固定提示)
curl -N -s -X POST http://127.0.0.1:8000/api/v1/rag/chat-stream \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"question":"年假可以休几天？","conversation_id":'$CID',"category_ids":[1]}'
```

### 3.4 模板显式指定 / 自动匹配

```bash
# 显式指定模板 2 (简洁精炼) → meta 事件 template_id=2
curl -N -s -X POST http://127.0.0.1:8000/api/v1/rag/chat-stream \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"question":"年假可以休几天？","conversation_id":'$CID',"template_id":2}'

# 不传会话自动新建: conversation_id 省略 → meta 返回新会话 ID, 标题=问题前20字
curl -N -s -X POST http://127.0.0.1:8000/api/v1/rag/chat-stream \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"question":"加班费怎么计算？","category_ids":[2]}'

# 非法模板 → error 事件 (msg=提示词模板不存在或已禁用), 落库 error_message
curl -N -s -X POST http://127.0.0.1:8000/api/v1/rag/chat-stream \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"question":"测试","conversation_id":'$CID',"template_id":99999}'

# 非法分类 → 标准 400 (code=40000), 流未建立
curl -s -X POST http://127.0.0.1:8000/api/v1/rag/chat-stream \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"question":"测试","category_ids":[99999]}'
```

### 3.5 多轮上下文

```bash
# 第一问 (命中) → 第二问省略主语的模糊追问, 应关联上一轮语境
curl -N -s -X POST http://127.0.0.1:8000/api/v1/rag/chat-stream \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"question":"请假需要提前多久申请？","conversation_id":'$CID'}'

curl -N -s -X POST http://127.0.0.1:8000/api/v1/rag/chat-stream \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"question":"那需要提前多久？","conversation_id":'$CID'}'
```

> 多轮检索兜底（已实现）: 裸问题检索无命中时, 依次用「最近一轮完整问答的
> 用户问题 + 当前问题」拼接检索、再直接用该用户问题检索; 无匹配固定回复与
> 失败消息不参与历史组装 (噪音剔除)。第二问预期 sources 命中、回答含
> 「提前一天在 OA 系统提交」。

### 3.6 数据落库验证

```bash
# 对话详情: 消息成对出现, assistant 消息带 retrieved_chunks/sources/token_usage/response_time_ms
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/rag/conversations/$CID"

# 数据库直查
sudo docker exec -i eakb-mysql mysql -ueakb -peakb123456 eakb -e "
select id,role,left(question,20) q,left(answer,30) a,response_time_ms,feedback from rag_message where conversation_id=$CID;
select id,title,message_count,template_id,category_ids from rag_conversation where id=$CID;"

# 操作日志 (module=rag, action=chat)
sudo docker exec -i eakb-mysql mysql -ueakb -peakb123456 eakb \
  -e "select username,action,module,target_id,detail from sys_operation_log where module='rag' order by id desc limit 5;"
```

## 4. 消息反馈

```bash
# 取一条 assistant 消息 ID (上一步详情返回或 SQL 查询)
MID=<assistant消息ID>

# 4.1 点赞
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/rag/messages/$MID/feedback \
  -d '{"feedback":"positive","comment":"回答准确"}'
# 预期: data.feedback=positive, data.feedback_comment=回答准确

# 4.2 点踩覆盖
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/rag/messages/$MID/feedback \
  -d '{"feedback":"negative"}'

# 4.3 非法值 → 422
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/rag/messages/$MID/feedback \
  -d '{"feedback":"neutral"}'

# 4.4 对用户消息反馈 → 400 (code=40000)
UMID=<user消息ID>
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/rag/messages/$UMID/feedback \
  -d '{"feedback":"positive"}'
```

## 5. 删除对话

```bash
# 5.1 删除测试会话 → 消息级联清理
curl -s -X DELETE -H "$AUTH" http://127.0.0.1:8000/api/v1/rag/conversations/$CID
sudo docker exec -i eakb-mysql mysql -ueakb -peakb123456 eakb \
  -e "select count(*) from rag_message where conversation_id=$CID;"  # → 0

# 5.2 再次删除/访问 → 404 (code=40400)
curl -s -X DELETE -H "$AUTH" http://127.0.0.1:8000/api/v1/rag/conversations/$CID
```

## 6. pytest 单元测试

```bash
cd ~/eakb/backend
pytest tests/test_rag.py -v
# 预期全部通过 (纯逻辑用例, 无需真实 DB/Chroma/LLM)
```

## 7. 前端页面自测

浏览器打开 http://localhost:5173，登录 zhangsan / Abc123456，左侧菜单进入「智能问答」：

1. **新对话发送**：输入「年假可以休几天？」发送 → 观察逐字流式输出 + 打字光标；
   发送后左侧自动出现标题为问题前 20 字的新会话。
2. **来源引用**：回答完成后气泡底部显示「引用来源 (N)」→ 点击打开右侧面板 →
   来源按文档聚合（名称/文件名/相关度），展开可见分块文本与相似度。
3. **分类限定**：输入区「分类筛选」勾选「人事制度」再问年假 → 返回固定无匹配提示；
   切换回「考勤管理」→ 正常回答。清空筛选 → 检索全库。
4. **模板切换**：模板下拉切换「简洁精炼」→ 发送后 DB 验证 prompt_full 以
   「请用简洁的语言回答用户问题」开头（实测 id=79 ✓）。注意简单事实型问题
   两种模板风格接近属正常，想看明显差异用开放性问题对比
   （如「详细讲解」问保密制度）。
5. **多轮对话**：继续追问「那需要提前多久申请？」→ 回答关联上文语境。
6. **点赞点踩**：点击「有帮助」→ 弹备注框 → 提交 → 按钮高亮 + 成功提示；
   点「无帮助」可覆盖；刷新页面 (F5) 后反馈状态保持。
7. **历史会话**：左侧列表切换会话 → 消息完整加载、输入区回填该会话的模板与分类范围；
   重命名（铅笔图标）/ 删除（垃圾桶图标，二次确认）生效；删除当前会话自动回到新对话页。
8. **断线重试**：流式输出中途断开后端 (Ctrl+C 停 uvicorn) → 错误条显示
   「连接已中断，请点击重试」→ 重启后端后点「重试」→ 重新发起回答。
9. **停止按钮**：流式中点击「停止」→ 输出中止，可继续提问。
10. **路由直达**：地址栏输入 /chat/123 (存在的会话) 直接打开对应会话；
    未登录访问 /chat → 跳转登录页。

## 8. 注意事项

- DeepSeek 流式最终块若取不到 usage，token_usage 为估算值（`estimate_usage` 兜底），属正常。
- 首次问答需加载本地 bge 嵌入模型（CPU 编码查询向量，约 1-2 秒），后续秒级响应。
- 如 `meta` 后长时间无 `delta`，检查后端日志：Embedding 未初始化（bge 加载失败）或
  DeepSeek Key 无效会以 `error` 事件返回，且消息落库 `error_message` 可查。

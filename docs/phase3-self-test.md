# Phase 3 知识库模块 — 自测流程

覆盖：分类树管理、文档上传（单/批量）、解析、分块、向量入库、软删除、批量向量化、操作日志。

## 0. 前置条件

```bash
# 1) 启动依赖服务 (MySQL / Neo4j / MinIO)
sudo docker compose up -d

# 2) 确认后端虚拟环境并安装依赖
#    新增: sentence-transformers + torch (本地 bge Embedding 模型)
cd ~/eakb/backend && source venv/bin/activate
# ⚠️ 顺序很重要: 先单独装 CPU 版 torch, 再装其余依赖
# (默认 PyPI 的 torch 是 CUDA 版, nvidia 依赖 4-5GB, 会撑爆 1.7G 的 /tmp 报 Errno 122)
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

# 3) 预下载 Embedding 模型 (首次向量化会自动下载, 也可提前验证连通性)
python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-large-zh-v1.5')"
# 网络受限时: export HF_ENDPOINT=https://hf-mirror.com

# 4) 执行 Phase 3 数据库迁移 (kb_category / kb_document / kb_document_chunk / sys_config)
alembic upgrade head
# 验证 (VM 未装 mysql 客户端, 通过容器执行):
# sudo docker exec -i eakb-mysql mysql -ueakb -peakb123456 eakb -e "show tables;"

# 5) 配置 .env (Embedding 默认本地 bge, 无需任何 LLM_EMBEDDING_* 配置)
#    LLM_MODEL_NAME=deepseek-chat / LLM_API_BASE=https://api.deepseek.com/v1 / LLM_API_KEY=sk-xxxx  (Phase 5 使用)
#    ⚠️ .env 中 UPLOAD_ALLOWED_EXTENSIONS 需更新为: pdf,docx,txt,md,xlsx (旧值含 doc/xls)
#    ⚠️ 若显式配置了 LLM_EMBEDDING_API_KEY, 将优先走远端 OpenAI 兼容接口

# 6) 启动后端 (首次向量化会加载 bge 模型, 内存约 +2GB)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> 注意：Windows 编辑 → VM 运行存在文件同步，执行前先确认 `alembic/versions/20260813_0002_*.py`
> 等新文件已在 VM 上（`ls ~/eakb/backend/alembic/versions/`）。

## 1. 单元测试

```bash
cd ~/eakb/backend
source venv/bin/activate
python -m pytest tests/test_text_splitter.py tests/test_file_parser.py -v
```

预期全部通过：分块重叠连续性、段落边界、多编码解析、DOCX 段落+表格、XLSX 多工作表、
不支持类型/空内容报错等。

## 2. 登录获取 Token

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"zhangsan","password":"Abc123456"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")
echo $TOKEN
AUTH="Authorization: Bearer $TOKEN"
```

> 测试账号若已改密，用你自己的账号；也可注册新账号。

## 3. 分类树自测

```bash
# 3.1 创建一级分类
curl -s -X POST http://127.0.0.1:8000/api/v1/categories/ -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"name":"人事制度","sort_order":0,"description":"公司人事相关制度"}'

# 3.2 创建二级分类 (parent_id=1)
curl -s -X POST http://127.0.0.1:8000/api/v1/categories/ -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"name":"考勤管理","parent_id":1,"sort_order":0}'

# 3.3 创建二级分类 (技术文档)
curl -s -X POST http://127.0.0.1:8000/api/v1/categories/ -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"name":"技术文档","parent_id":null,"sort_order":1}'

# 3.4 查询树 (应返回两级树形结构)
curl -s http://127.0.0.1:8000/api/v1/categories/ -H "$AUTH" | python3 -m json.tool

# 3.5 拖拽排序模拟 (把分类 2 移动到"技术文档"分类下, sort_order=0)
# ⚠️ 技术文档的实际 ID 以 3.4 树查询结果为准 (此处示例为 3)
curl -s -X PUT http://127.0.0.1:8000/api/v1/categories/2/move -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"parent_id":3,"sort_order":0}'

# 3.6 删除守卫: 删除有文档/子分类的分类应返回 400 错误
curl -s -X DELETE http://127.0.0.1:8000/api/v1/categories/1 -H "$AUTH"
```

## 4. 单文件上传 → 解析 → 向量化完整链路

```bash
# 准备测试文件 (UTF-8)
cat > /tmp/kb-test.txt <<'EOF'
企业知识库智能助手（EAKB）测试文档。

一、考勤管理制度
公司实行标准工时制，工作时间为周一至周五 9:00-18:00。
员工因故不能出勤的，应提前一天在 OA 系统提交请假申请。
年假天数按照工作年限计算：满 1 年不满 10 年 5 天，满 10 年不满 20 年 10 天，满 20 年 15 天。

二、加班管理
加班须经直属主管审批，工作日加班可安排调休，休息日加班优先调休。
调休有效期为加班发生后 3 个月内。

三、保密制度
员工在职期间及离职后，均不得泄露公司商业秘密及客户资料。
EOF

# 4.1 上传 (category_id 指向考勤管理分类, 如 2)
curl -s -X POST http://127.0.0.1:8000/api/v1/documents/upload -H "$AUTH" \
  -F "files=@/tmp/kb-test.txt" -F "category_id=2" -F "title=考勤管理制度" \
  -F "tags=考勤,制度" | python3 -m json.tool
# 预期: 立即返回文档信息, vector_status=pending (接口不阻塞)

# 4.2 轮询状态: pending → processing → completed
DOC_ID=1
curl -s http://127.0.0.1:8000/api/v1/documents/$DOC_ID -H "$AUTH" | python3 -m json.tool
# 预期: vector_status=completed, chunk_count>0, vectorized_at 有值

# 4.3 查看分块记录
curl -s "http://127.0.0.1:8000/api/v1/documents/$DOC_ID/chunks?page=1&page_size=10" \
  -H "$AUTH" | python3 -m json.tool
# 预期: chunk_index 从 0 递增, 每块含 chunk_hash / chroma_chunk_id / token_count

# 4.4 下载 (返回预签名 URL)
curl -s http://127.0.0.1:8000/api/v1/documents/$DOC_ID/download -H "$AUTH" | python3 -m json.tool

# 4.5 验证 Chroma 向量已入库
cd ~/eakb/backend && source venv/bin/activate && python3 -c "
import chromadb
c = chromadb.PersistentClient(path='./chroma_data')
col = c.get_collection('document_chunks')
print('总块数:', col.count())
print(col.get(where={'document_id': 1}, include=['metadatas'])['metadatas'])
"

# 4.6 验证 MinIO 文件已持久化
# 浏览器打开 http://192.168.1.80:9001 (minioadmin/minioadmin123456)
# 查看 eakb-documents 桶 → documents/2026/08/ 路径下的对象
```

## 5. 批量文件上传（混合格式）

```bash
# 准备 md / xlsx / 新 txt 三个文件
cat > /tmp/faq.md <<'EOF'
# 常见问题 FAQ

## 如何申请年假？
在 OA 系统提交请假申请，选择年假类型，等待主管审批。

## 如何报销差旅费？
出差结束后 30 天内，在财务系统提交报销单并上传发票。
EOF

cat > /tmp/kb-test-2.txt <<'EOF'
技术文档中心使用规范。

一、代码仓库规范
所有项目代码托管于内部 GitLab，主干分支禁止直接推送，必须通过 MR 评审合入。

二、发布流程
生产发布须填写发布申请单，经运维与项目负责人双审后方可执行。
EOF

python3 - <<'PY'
from openpyxl import Workbook
wb = Workbook()
ws = wb.active
ws.title = "报销标准"
ws.append(["城市级别", "住宿上限(元/晚)", "餐补(元/天)"])
ws.append(["一线城市", 600, 100])
ws.append(["二线城市", 450, 80])
wb.save("/tmp/expense.xlsx")
PY

# 批量上传 3 个文件到技术文档分类 (实际 ID 以树查询结果为准, 示例为 3)
curl -s -X POST http://127.0.0.1:8000/api/v1/documents/upload -H "$AUTH" \
  -F "files=@/tmp/faq.md" \
  -F "files=@/tmp/expense.xlsx" \
  -F "files=@/tmp/kb-test-2.txt" \
  -F "category_id=3" -F "description=批量上传测试" | python3 -m json.tool
# 预期: 一次返回 3 个文档, 均 pending; 后台逐文档执行向量化
# 注意: 批量上传为三阶段校验 (整体校验 → MinIO → 入库),
#       任一文件与库中已有文档 SHA256 重复 / 与同批次其他文件重复,
#       整个批次都会被拒绝, 不会产生部分脏数据

# 列表轮询 (按分类过滤, 含子分类)
curl -s "http://127.0.0.1:8000/api/v1/documents/?page=1&page_size=10&category_id=3" \
  -H "$AUTH" | python3 -m json.tool
# 预期: 3 个文档全部 completed (md/xlsx/txt 解析分块均成功)
```

## 6. 失败与边界场景

```bash
# 6.1 重复上传 (同文件 SHA256 相同) → 409
curl -s -X POST http://127.0.0.1:8000/api/v1/documents/upload -H "$AUTH" \
  -F "files=@/tmp/kb-test.txt" -F "category_id=2"

# 6.2 非法后缀 → 415
echo "test" > /tmp/evil.sh
curl -s -X POST http://127.0.0.1:8000/api/v1/documents/upload -H "$AUTH" \
  -F "files=@/tmp/evil.sh" -F "category_id=2"

# 6.3 超大文件 → 413 (生成 60MB 文件, 上限默认 50MB)
dd if=/dev/zero of=/tmp/big.txt bs=1M count=60
curl -s -X POST http://127.0.0.1:8000/api/v1/documents/upload -H "$AUTH" \
  -F "files=@/tmp/big.txt" -F "category_id=2"

# 6.4 本地模型未就绪 → 上传成功但 vector_status=failed, error_message 有明确提示
# 临时把 EMBEDDING_MODEL_NAME 改成不存在的模型名重启后端, 重传一个新文件观察
# (恢复配置后可用 /vectorize 接口重试)

# 6.5 失败重试: 配置好 Embedding 后重新触发
curl -s -X POST http://127.0.0.1:8000/api/v1/documents/$DOC_ID/vectorize -H "$AUTH"
```

## 7. 批量向量化 / 软删除

```bash
# 7.1 批量重建向量 (多选文档)
curl -s -X POST http://127.0.0.1:8000/api/v1/documents/batch-vectorize -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"document_ids":[2,3]}'
# 预期: 返回逐文档结果 (triggered=true/false), 处理中/待处理的会被跳过

# 7.2 软删除 (status=-1, 同步清理 Chroma 向量)
curl -s -X DELETE http://127.0.0.1:8000/api/v1/documents/3 -H "$AUTH"
# 验证 1: 列表不再返回该文档
curl -s "http://127.0.0.1:8000/api/v1/documents/?page=1&page_size=20" -H "$AUTH"
# 验证 2: Chroma 中 document_id=3 的块已删除
python3 -c "
import chromadb
c = chromadb.PersistentClient(path='./chroma_data')
col = c.get_collection('document_chunks')
print('doc3 剩余块:', len(col.get(where={'document_id': 3})['ids']))
"
# 验证 3: MySQL 分块记录保留 (审计)
sudo docker exec -i eakb-mysql mysql -ueakb -peakb123456 eakb \
  -e "select count(*) from kb_document_chunk where document_id=3;"
```

## 8. 操作日志验证

```bash
sudo docker exec -i eakb-mysql mysql -ueakb -peakb123456 eakb -e \
  "select id,username,action,module,target_id,created_at from sys_operation_log order by id desc limit 10;"
# 预期包含: upload_document / create_category / move_category / batch_vectorize / delete_document
```

## 9. 前端页面自测

```bash
cd ~/eakb/frontend && npm run dev
# 浏览器打开 http://localhost:5173 登录后:
```

1. **分类管理** (`/knowledge/categories`)：新增一级/子分类 → 拖拽节点调整顺序与层级
   （拖到自身子分类下应被拦截）→ 删除有文档的分类提示失败
2. **上传文档** (`/knowledge/documents/upload`)：选分类 → 拖入多文件（试试 .sh 非法文件，
   应被前端拦截并提示）→ 上传 → 自动跳转列表
3. **文档列表** (`/knowledge/documents`)：筛选（分类/状态/类型/关键词）→ 勾选多行 →
   批量向量化 → 详情/下载/删除；处理中状态 5s 自动轮询
4. **文档详情** (`/knowledge/documents/:id`)：元数据、失败错误提示（红色 alert）、
   分块列表展开全文、向量化中 3s 自动轮询直到 completed

## 10. 常见问题排查

| 现象 | 排查 |
|------|------|
| 上传后一直是 pending | 检查后端日志 `[向量化]` 输出；BackgroundTasks 在请求返回后执行，稍等几秒 |
| 状态 failed | 看详情页 error_message：MinIO 未启动 / Embedding Key 未配置 / 文件解析失败 |
| 迁移报错 | 确认迁移文件已同步到 VM；`alembic current` 检查版本号是否停在 0002 |
| Chroma 写入失败 | 检查 `CHROMA_PERSIST_DIR` 目录写权限 |
| 前端 404 | 后端未重启加载新路由；检查 VITE_API_BASE_URL 指向 8000 端口 |

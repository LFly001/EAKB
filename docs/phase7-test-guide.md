# Phase 7 管理后台模块 — 全功能测试流程

覆盖：数据看板聚合统计、操作日志分页多条件筛选（审计只读）、系统配置可视化修改与实时生效、用户管理批量操作、admin 权限边界（员工拦截）、前端四页面。

## 0. 前置条件

```bash
# 1) 启动依赖服务 (MySQL / Neo4j / MinIO)
#    ⚠️ 必须在项目根目录执行 (docker-compose.yml 所在位置)
cd ~/eakb
sudo docker compose up -d

# 2) 后端虚拟环境 + 代码校验 (⚠️ ruff --fix 会改 VM 文件,
#    改完必须拷回 Windows, 防止下次同步覆盖回退)
cd ~/eakb/backend && source venv/bin/activate
ruff check --fix app alembic && mypy app

# 3) 本阶段迁移: 补种 3 个图谱配置键 (不建表, sys_config 已于 Phase 3 建好)
alembic upgrade head
# 预期输出: Running upgrade 20260816_0004 -> 20260824_0005
# 验证种子键 (应为 10 行):
sudo docker exec eakb-mysql mysql -ueakb -peakb123456 --default-character-set=utf8mb4 \
  -e "SELECT config_key, config_value, config_type FROM eakb.sys_config ORDER BY id"

# 4) 启动后端
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 5) 启动前端
cd ~/eakb/frontend && npm run dev
```

> ⚠️ Windows → VM 文件同步有滞后，执行前先确认以下新文件已在 VM 上：
>
> - `backend/app/schemas/admin.py`（新建）、`services/dashboard_service.py`（新建）、`api/v1/admin.py`（新建）
> - `backend/app/services/log_service.py`（补时间范围筛选）、`services/config_service.py`（补 list_all/get_by_key/update/get_upload_max_size_mb）、`services/document_service.py`（上传大小改读 sys_config）、`api/v1/users.py`（批量接口）、`api/v1/router.py`（挂载 admin）、`schemas/user.py`（UserBatchRequest）
> - `backend/alembic/versions/20260824_0005_phase7_admin.py`（新建迁移）
> - `frontend/src/types/admin.ts`、`api/admin.ts`（新建）、`api/user.ts`（批量）、`views/dashboard/DashboardView.vue`、`views/admin/UserManage.vue`、`views/admin/LogList.vue`、`views/admin/SystemConfig.vue`、`router/index.ts`、`components/layout/AppLayout.vue`

> 测试账号：zhangsan / Abc123456（role=admin）。VM 库已有数据：分类 3 个、文档 1/2 有效、问答历史若干。

## 0.5 单元测试

```bash
cd ~/eakb/backend && source venv/bin/activate
# 全量回归 (Phase 7 无新增单测文件, 确认既有 90 用例不受影响)
pytest tests/ -v --ignore=tests/test_graph_neo4j_integration.py
```

## 1. 登录获取 Token

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"zhangsan","password":"Abc123456"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")
echo $TOKEN
```

## 2. 权限边界测试（仅 admin 可访问）

```bash
# 2.1 无 Token 访问 admin 接口 → 401
curl -s http://127.0.0.1:8000/api/v1/admin/dashboard
# 预期: {"detail":"未提供认证凭证"} 且 HTTP 401

# 2.2 注册一个普通员工 (lisi / Abc123456) 并获取其 Token
# 注册接口必填 confirm_password; 若 lisi 已存在会返回 409, 直接执行下一行登录即可
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"lisi","password":"Abc123456","confirm_password":"Abc123456","real_name":"李四"}'
EMP_TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"lisi","password":"Abc123456"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")

# 2.3 员工访问 admin 四个接口 → 全部 403
for url in dashboard logs configs; do
  echo "== /admin/$url =="
  curl -s http://127.0.0.1:8000/api/v1/admin/$url -H "Authorization: Bearer $EMP_TOKEN"
done
curl -s -X PUT http://127.0.0.1:8000/api/v1/admin/configs/top_k \
  -H "Authorization: Bearer $EMP_TOKEN" -H "Content-Type: application/json" \
  -d '{"config_value":"5"}'
# 预期: 全部 {"detail":"需要管理员权限"} 且 HTTP 403

# 2.4 员工访问用户管理/批量接口 → 403
curl -s http://127.0.0.1:8000/api/v1/users/ -H "Authorization: Bearer $EMP_TOKEN"
curl -s -X POST http://127.0.0.1:8000/api/v1/users/batch \
  -H "Authorization: Bearer $EMP_TOKEN" -H "Content-Type: application/json" \
  -d '{"user_ids":[1],"action":"enable"}'
```

**前端权限验证**：
1. 用 lisi / Abc123456 登录 → 左侧菜单**无「管理后台」子菜单**、无「数据看板」入口
2. 浏览器直接访问 `http://localhost:5173/admin/users`、`/admin/logs`、`/admin/config`、`/dashboard` → 均被路由守卫弹回 `/chat`
3. 用 zhangsan 登录 → 「管理后台」子菜单可见（数据看板/用户管理/操作日志/系统配置四项），`/dashboard` 可访问

## 3. 数据看板（GET /admin/dashboard）

```bash
curl -s http://127.0.0.1:8000/api/v1/admin/dashboard -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

预期返回 6 个字段，且与库内实际数据一致：

| 字段 | 口径 | 预期值（当前 VM 数据） |
|------|------|------|
| user_count | 全部用户 | ≥ 2（zhangsan + lisi + 历史用户） |
| document_count | 未软删文档 | 2（文档 3/4 已软删不计） |
| conversation_count | 会话总量 | Phase5 历史会话数 |
| today_question_count | 今日 user 消息 | 今天问答过的次数 |
| vectorized_document_count | completed 且未删 | 2 |
| today_operation_count | 今日操作日志 | 本次测试写入的日志数 |

对账 SQL（可选）：

```bash
sudo docker exec eakb-mysql mysql -ueakb -peakb123456 --default-character-set=utf8mb4 -e "
SELECT '用户总数' k, COUNT(*) v FROM eakb.sys_user
UNION ALL SELECT '文档总量(未软删)', COUNT(*) FROM eakb.kb_document WHERE status != -1
UNION ALL SELECT '向量化文档', COUNT(*) FROM eakb.kb_document WHERE vector_status='completed' AND status != -1
UNION ALL SELECT '会话总量', COUNT(*) FROM eakb.rag_conversation
UNION ALL SELECT '今日提问', COUNT(*) FROM eakb.rag_message WHERE role='user' AND created_at >= CURDATE();"
```

**前端验证**：管理员登录 → 数据看板页 6 张统计卡数字与接口一致；点「刷新」更新；页面下方有统计口径说明。

## 4. 操作日志（GET /admin/logs）

```bash
# 4.1 默认分页 (20 条/页, 倒序)
curl -s "http://127.0.0.1:8000/api/v1/admin/logs?page=1&page_size=20" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# 预期: data.items 数组 + total/pages 分页字段; 刚才的登录/配置操作已入日志

# 4.2 模块筛选 (认证模块)
curl -s "http://127.0.0.1:8000/api/v1/admin/logs?module=auth" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(d['total'],[i['action'] for i in d['items'][:5]])"

# 4.3 用户名模糊筛选
curl -s "http://127.0.0.1:8000/api/v1/admin/logs?username=lisi" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print('lisi日志数:',d['total'])"
# 预期: lisi 注册/登录的日志 ≥ 2

# 4.4 结果筛选 + 时间范围 (今天 0 点 → 现在, 本地时间字符串不带 Z)
curl -s "http://127.0.0.1:8000/api/v1/admin/logs?status=success&start_time=$(date +%Y-%m-%d)T00:00:00" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print('今日成功日志:',d['total'])"

# 4.5 组合筛选 (模块=user + 批量操作关键字)
curl -s "http://127.0.0.1:8000/api/v1/admin/logs?module=user" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print([i['action'] for i in d['items'][:10]])"

# 4.6 审计约束: 不存在删除接口 (路径未注册 → 404, 无任何删除入口)
curl -s -X DELETE "http://127.0.0.1:8000/api/v1/admin/logs/1" -H "Authorization: Bearer $TOKEN"
# 预期: 404 Not Found (/admin/logs/{id} 路径未注册, 仅 GET /logs 可访问)
```

**前端验证**：操作日志页 → 模块下拉（认证/用户管理/知识库/提示词模板/RAG问答/知识图谱/系统配置）、操作人输入框、执行结果下拉、时间范围选择器均可筛选；点「详情」抽屉展示完整字段（detail JSON、UserAgent、错误信息）；页面有「仅审计查询、不支持删除」提示。

## 5. 系统配置（GET /admin/configs + PUT /admin/configs/{key}）

```bash
# 5.1 配置列表 (应为 10 项: Phase3 的 7 个 + 本阶段迁移补种的 3 个图谱键)
curl -s http://127.0.0.1:8000/api/v1/admin/configs -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(len(d),[c['config_key'] for c in d])"

# 5.2 修改 top_k = 8 → 实时生效
curl -s -X PUT http://127.0.0.1:8000/api/v1/admin/configs/top_k \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"config_value":"8"}'
# 预期: msg 含"实时生效"; 立即读回验证:
curl -s http://127.0.0.1:8000/api/v1/admin/configs -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print([ (c['config_key'],c['config_value']) for c in d if c['config_key']=='top_k'])"

# 5.3 实时生效验证 (RAG): 问答一次, 观察检索分块数变为 8
#     前端 /chat 提问「年假怎么申请」→ 来源引用面板分块数 ≤ 8 且 > 5 (原 top_k=5)
#     (知识库仅 2 篇文档, 若总分块不足 8 则实际数受分块总量限制, 属正常)

# 5.4 实时生效验证 (上传大小): upload_max_size_mb 改为 1, 上传 >1MB 文件被拦截
curl -s -X PUT http://127.0.0.1:8000/api/v1/admin/configs/upload_max_size_mb \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"config_value":"1"}'
head -c 2097152 /dev/zero > /tmp/big2mb.txt   # 2MB 测试文件
# 注意: 上传接口 files 与 category_id 均为 multipart Form 字段
curl -s -X POST http://127.0.0.1:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@/tmp/big2mb.txt" \
  -F "category_id=3"
# 预期: 400 错误 "超过 1MB 限制" (上传前校验, MinIO 无脏数据)
# ⚠️ 测完恢复:
curl -s -X PUT http://127.0.0.1:8000/api/v1/admin/configs/upload_max_size_mb \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"config_value":"50"}'

# 5.5 类型校验: number 键传非数字 → 400; json 键传非法 JSON → 400
curl -s -X PUT http://127.0.0.1:8000/api/v1/admin/configs/chunk_size \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"config_value":"abc"}'
# 预期: 400 "不是合法数字"

# 5.6 不存在的键 → 404
curl -s -X PUT http://127.0.0.1:8000/api/v1/admin/configs/not_exist_key \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"config_value":"x"}'
# 预期: 404 "配置项 'not_exist_key' 不存在"

# 5.7 图谱开关可视化修改 (Phase 6 参数):
curl -s -X PUT http://127.0.0.1:8000/api/v1/admin/configs/graph_enhance_enabled \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"config_value":"true"}'
# 预期: 保存成功; /chat 问答的 context 中出现 "[知识图谱关联]" 块 (需 Neo4j 有实体)
```

**前端验证**：系统配置页 → 10 行配置（键/说明/值/类型标签/更新时间）；点「编辑」行内输入（数字键提示"数字，如 512 / 0.7"，JSON 键多行框）→「保存」成功提示"已更新, 实时生效"；数字键输 `abc` 保存被前端拦截报错；「生效说明」按钮弹窗解释回退机制。

## 6. 用户管理批量操作（POST /users/batch）

```bash
# 6.1 创建 3 个测试用户
for u in test1 test2 test3; do
  curl -s -X POST http://127.0.0.1:8000/api/v1/users/ \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"username\":\"$u\",\"password\":\"Abc123456\",\"role\":\"employee\"}" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['msg'],d.get('data',{}).get('id'))"
done

# 6.2 批量禁用 (拿到 3 个 id, 例如 5,6,7)
IDS=$(curl -s "http://127.0.0.1:8000/api/v1/users/?keyword=test" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(','.join(str(i['id']) for i in d['items']))")
echo "测试用户IDs: $IDS"
ID_LIST=$(echo $IDS | tr ',' '\n' | python3 -c "import sys,json;print(json.dumps([int(x) for x in sys.stdin.read().split()]))")
curl -s -X POST http://127.0.0.1:8000/api/v1/users/batch \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"user_ids\":$ID_LIST,\"action\":\"disable\"}"
# 预期: msg "批量禁用完成: 3 个用户"; 列表页状态全为禁用
# 验证禁用用户无法登录 (401 账号已被禁用):
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" -d '{"username":"test1","password":"Abc123456"}'

# 6.3 批量启用后再批量删除
curl -s -X POST http://127.0.0.1:8000/api/v1/users/batch \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"user_ids\":$ID_LIST,\"action\":\"enable\"}"
curl -s -X POST http://127.0.0.1:8000/api/v1/users/batch \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"user_ids\":$ID_LIST,\"action\":\"delete\"}"
# 预期: 删除完成; 日志页出现 batch_disable_user / batch_enable_user / batch_delete_user 记录

# 6.4 自操作拦截: 批量列表含自己 (zhangsan 的 id) → 400
curl -s -X POST http://127.0.0.1:8000/api/v1/users/batch \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"user_ids\":[1],\"action\":\"delete\"}"
# 预期: 400 "不能批量操作自己的账号" (zhangsan id=1)

# 6.5 非法 action → 400
curl -s -X POST http://127.0.0.1:8000/api/v1/users/batch \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"user_ids":[2],"action":"rename"}'
# 预期: 400 "action 仅支持 enable / disable / delete"
```

**前端验证**：用户管理页 → 角色/状态下拉筛选 + 关键词搜索；勾选多行 → 顶部「批量启用/禁用/删除」按钮（未勾选时禁用）；「创建用户」弹窗（用户名/初始密码必填校验）→ 创建成功列表刷新；行内「编辑」弹窗（无密码项）→ 修改部门/角色保存生效。

## 7. 回归验证

```bash
# 7.1 全量 pytest (排除 Neo4j 集成用例)
cd ~/eakb/backend && source venv/bin/activate
pytest tests/ -v --ignore=tests/test_graph_neo4j_integration.py

# 7.2 前端构建无类型错误
cd ~/eakb/frontend
npx vue-tsc --noEmit && npm run build

# 7.3 修复后的文件拷回 Windows (⚠️ ruff --fix / 表单校验改动)
#     确认 VM 上被 --fix 改动的文件已同步回 d:\Project\eakb
```

## 8. 已知边界

- 看板「今日」统计按服务器本地零点（容器 TZ=Asia/Shanghai）计算
- 日志时间筛选传本地时间字符串（前端已处理，勿带 UTC Z 后缀，否则偏差 8 小时）
- 批量操作非事务：中途某个 ID 不存在会整体返回 404，已处理部分不回滚（单条日志）
- 修改 chunk_size / chunk_overlap 仅影响之后新上传文档的向量化，已分块文档不受影响
- sys_config 配置值置空不允许（前端校验），删除配置键的行为不在管理界面提供；键缺失时业务自动回退 .env 默认值

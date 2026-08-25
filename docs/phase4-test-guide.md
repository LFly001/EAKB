# Phase 4 提示词模板模块 — 测试流程

覆盖：模板 CRUD、系统预置模板保护、变量校验、分类绑定/解绑、按分类筛选、热门模板、变量渲染、操作日志、前端页面（列表/表单/模板选择组件）。

## 0. 前置条件

```bash
# 1) 启动依赖服务 (MySQL / Neo4j / MinIO)
sudo docker compose up -d

# 2) 后端虚拟环境 (Phase 3 已装好依赖, 本阶段无新增依赖)
cd ~/eakb/backend && source venv/bin/activate

# 3) 执行 Phase 4 数据库迁移 (pt_template / pt_template_category + 3 个系统预置模板种子)
alembic upgrade head
# 验证建表 + 种子:
sudo docker exec -i eakb-mysql mysql -ueakb -peakb123456 eakb \
  -e "show tables like 'pt_%'; select id,name,is_system,status from pt_template;"

# 4) 启动后端
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 5) 启动前端
cd ~/eakb/frontend && npm run dev
```

> ⚠️ Windows → VM 文件同步有滞后，执行前先确认以下新文件已在 VM 上：
> - `backend/alembic/versions/20260815_0003_phase4_templates.py`
> - `backend/app/models/template.py`、`app/schemas/template.py`、`app/services/template_service.py`、`app/api/v1/templates.py`
> - `frontend/src/views/template/`、`frontend/src/api/template.ts`、`frontend/src/types/template.ts`、`frontend/src/components/chat/TemplateSelector.vue`

## 1. 登录获取 Token

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"zhangsan","password":"Abc123456"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")
AUTH="Authorization: Bearer $TOKEN"
```

## 2. 系统预置模板 (迁移种子验证)

```bash
# 2.1 模板列表 — 应返回 3 个系统模板, is_system=1, usage_count=0
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/templates/?page=1&page_size=10"

# 2.2 按类型筛选
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/templates/?is_system=1"

# 2.3 删除系统模板 → 必须 403 (code=40300, msg=系统预置模板不可删除)
curl -s -X DELETE -H "$AUTH" "http://127.0.0.1:8000/api/v1/templates/1"
```

## 3. 创建自定义模板 + 变量校验

```bash
# 3.1 正常创建 (variables 缺省自动使用标准结构), 并把返回的 data.id 存入 TID
#     ⚠️ TID 变量被后续所有步骤引用, 必须先执行本步
TID=$(curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/templates/ -d '{
    "name": "人事制度问答",
    "description": "面向人事制度分类的问答模板",
    "template_content": "你是人事制度专员。\n相关资料:\n{{context}}\n\n问题: {{question}}\n\n请依据资料作答。",
    "tags": "人事,制度"
  }' | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['id'])")
echo "TID=$TID"

# 3.2 非法变量 → 必须 400 (code=40000, msg 提示仅支持 {{question}}/{{context}})
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/templates/ -d '{
    "name": "非法变量模板",
    "template_content": "分类是 {{category}}，问题: {{question}}"
  }'

# 3.3 默认分类不存在 → 404 (code=40400, msg=分类不存在)
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/templates/ -d '{
    "name": "坏分类模板",
    "category_id": 99999,
    "template_content": "{{question}}"
  }'
```

## 4. 绑定 / 解绑知识库分类

```bash
# VM 现有分类: 1=人事制度 2=考勤管理 3=技术文档 (以实际库为准)

# 4.1 批量绑定 (追加语义) — TID 替换为 3.1 返回的模板 ID
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/templates/$TID/categories -d '{"category_ids": [1, 2]}'

# 4.2 重复绑定同一分类 → 不报错, 不产生重复记录 (UNIQUE 约束)
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/templates/$TID/categories -d '{"category_ids": [1]}'

# 4.3 设置绑定 (整体替换) — 变为 [1, 3]
curl -s -X PUT -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/templates/$TID/categories -d '{"category_ids": [1, 3]}'

# 4.4 解绑单个分类
curl -s -X DELETE -H "$AUTH" "http://127.0.0.1:8000/api/v1/templates/$TID/categories/3"

# 4.5 绑定不存在的分类 → 400
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/templates/$TID/categories -d '{"category_ids": [99999]}'

# 4.6 详情应携带 category_ids / category_names
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/templates/$TID"
```

## 5. 按分类筛选 + 热门模板

```bash
# 5.1 按分类筛选 (绑定分类 OR 默认分类命中)
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/templates/?category_id=1"

# 5.2 按分类获取可用模板 (DESIGN 6.5, Phase 5 问答自动匹配用; 绑定该分类的排前面)
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/templates/by-category/1"

# 5.3 热门模板 (按 usage_count 倒序, 仅启用)
curl -s -H "$AUTH" "http://127.0.0.1:8000/api/v1/templates/popular?limit=10"
```

## 6. 变量渲染 (问答组装 Prompt 预演)

```bash
# 渲染测试: {{question}}/{{context}} 自动填充
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/templates/$TID/render -d '{
    "question": "年假可以休多少天？",
    "context": "【来源: 考勤管理制度】员工工作满一年后可享受带薪年假5天……"
  }'
# 预期: data.rendered 中 {{question}}/{{context}} 已替换为传入值, 不残留占位符

# 禁用模板后渲染 → 400
curl -s -X PUT -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/templates/$TID -d '{"status": 0}'
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/templates/$TID/render -d '{"question": "测试"}'
# 恢复启用
curl -s -X PUT -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/templates/$TID -d '{"status": 1}'
```

## 7. 更新 / 删除 + 操作日志

```bash
# 7.1 更新模板 (含非法变量校验)
curl -s -X PUT -H "$AUTH" -H "Content-Type: application/json" \
  http://127.0.0.1:8000/api/v1/templates/$TID -d '{
    "name": "人事制度问答 v2",
    "template_content": "你是人事专员。\n资料:\n{{context}}\n\n问题: {{question}}"
  }'

# 7.2 删除自定义模板 → 成功, 关联绑定 CASCADE 清除
curl -s -X DELETE -H "$AUTH" "http://127.0.0.1:8000/api/v1/templates/$TID"

# 7.3 操作日志 — 日志接口属 Phase 7, 当前直接查库验证
#     应看到 module='template' 的 create/update/delete/bind/unbind 记录
sudo docker exec -i eakb-mysql mysql -ueakb -peakb123456 eakb \
  -e "select id,username,module,action,target_id,status,created_at from sys_operation_log where module='template' order by id desc limit 10;"
```

## 8. 前端页面测试 (http://<VM_IP>:5173)

1. **模板列表 `/templates`**
   - 侧边栏出现「提示词模板」菜单
   - 列表展示 3 个系统预置模板（黄色「系统预置」标签）+ 自定义模板
   - 系统模板行**无删除按钮**；自定义模板有删除按钮，删除需二次确认
   - 类型 / 标签 / 关联分类筛选生效；使用次数列可排序；状态开关可启停模板
2. **新建/编辑模板 `/templates/create`、`/templates/:id/edit`**
   - 工具栏「插入变量」按钮在光标位置插入 `{{question}}` / `{{context}}`
   - 输入非法变量（如 `{{category}}`）出现红色错误提示，保存被拦截
   - 「渲染预览」区实时展示占位符替换效果（可修改预览样例值）
   - 编辑页有「服务端渲染测试」按钮，弹窗展示后端渲染结果
   - 关联分类多选树保存后，返回列表可见绑定分类名称
3. **操作日志验证**：日志列表页属 Phase 7，本阶段按 7.3 节直接查 `sys_operation_log` 表确认模板操作已埋点（module='template'）

## 9. 问答页面选择模板（Phase 5 预演）

Phase 5 问答页接入 `TemplateSelector.vue` 后按此流程验证：

1. 问答页选择知识库分类 → 下拉框标注「适用当前分类」的模板自动排前
2. 选择模板后提问 → 后端用 `render_template_content()` 填充 `{{question}}`（用户输入）与 `{{context}}`（向量检索结果）组装 Prompt
3. 每次使用调用 `TemplateService.increment_usage()` → 列表「使用次数」+1、`/templates/popular` 排名上升

当前 Phase 4 阶段可用第 6 节渲染接口先行验证变量填充链路。

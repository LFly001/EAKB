# Phase 8 验收测试指南与交付清单

> Phase 8 内容：全局优化、单元测试、性能调优、部署交付。
> 前置：Phase 1-7 全部功能完成并实测通过（docs/phase2~7 指南）。
> 执行顺序：0 前置 → 1 代码质量 → 2 后端新特性自测 → 3 前端优化自测 → 4 全量回归 → 5 交付核对清单。

---

## 0. 前置条件

```bash
# 0.1 代码同步: 确认 Windows(d:\Project\eakb) 已同步到 VM(~/eakb), 特别注意新文件:
#     backend/alembic/versions/20260824_0006_phase8_rate_limit.py
#     backend/tests/ 下新增 6 个测试文件、backend/pytest.ini
#     frontend/src/utils/constants.ts、feedback.ts、eslint.config.js
#     deploy/、docker-compose.prod.yml、README.md、.gitignore

# 0.2 中间件服务
cd ~/eakb && sudo docker compose up -d && sudo docker compose ps

# 0.3 后端环境 + 依赖更新 (pytest.ini 等无需新依赖; 若 requirements 有更新则重新 pip install)
cd ~/eakb/backend && source venv/bin/activate

# 0.4 数据库迁移 (0005 → 0006: 补种限流配置键)
alembic upgrade head
# 验证: sys_config 应有 13 个键 (原 10 + 限流 3)
docker exec eakb-mysql sh -c "exec mysql -ueakb -peakb123456 --default-character-set=utf8mb4 -e 'SELECT config_key,config_value FROM eakb.sys_config ORDER BY id'"

# 0.5 启动后端
uvicorn app.main:app --reload --port 8000 &

# 0.6 前端
cd ~/eakb/frontend && npm install && npm run dev
```

测试账号：zhangsan / Abc123456（admin）。员工账号 lisi（若无则管理员创建）。

---

## 1. 代码质量校验（交付项 6）

```bash
cd ~/eakb
bash scripts/format_code.sh     # ruff format + ruff check --fix (会自动修改文件!)
bash scripts/check_quality.sh   # ruff format --check + ruff check + mypy — 三项全过方可提交
bash scripts/run_tests.sh       # pytest 全量 (排除 Neo4j 集成测试)
bash scripts/run_tests.sh --include-neo4j   # 可选: 含 Neo4j 集成 (需 NEO4J_TEST_URI)
```

预期：pytest **约 133 用例全绿**（原 90 + Phase 8 新增 43：认证 12 / 权限边界 5 / 上传向量化 8 / RAG 端点 5 / 限流 7 / Chroma 缓存 6）。
⚠️ 脚本改过的文件必须拷回 Windows（单向同步陷阱）。

---

## 2. 后端新特性自测

### 2.1 全局异常友好化（交付项 1）

| 场景 | 操作 | 预期 |
| --- | --- | --- |
| 数据冲突 | 注册已存在用户名 `POST /auth/register` | HTTP 409, `code: 40900` 友好提示（不再 500） |
| 数据库异常 | `sudo docker compose stop mysql` 后调用查库接口 (如登录) | HTTP 503, `code: 50301`「数据库服务异常」 |
| 对象存储异常 | `sudo docker compose stop minio` 后上传文件（**下载不触发**: 预签名 URL 是本地签名计算, 不请求 MinIO） | HTTP 503, `code: 50303`「文件存储服务异常」 |
| 向量库异常 | 临时改错 CHROMA_PERSIST_DIR 权限后问答 | SSE error 事件带友好提示, `code: 50302` |
| LLM 异常 | .env 填错 LLM_API_KEY 后问答 | SSE error 事件「大模型服务暂时不可用」, 不再透出 Key/堆栈 |
| 参数校验 | 缺字段请求 | HTTP 422, `code: 42200` 带字段定位 |
| 未知路由 | `GET /api/v1/nothing` | HTTP 404, `code: 40400` |

恢复：`sudo docker compose start mysql`。

### 2.2 接口限流（交付项 2）

1. 管理后台「系统配置」或接口把 `rate_limit_enabled` 改为 `true`、`rate_limit_requests=5`（实时生效，无需重启）：
   `PUT /api/v1/admin/configs/rate_limit_requests` `{"config_value":"5"}`
2. 快速连续 curl `/api/v1/ping` 6 次 → 第 6 次起 HTTP 429，`code: 42900`「请求过于频繁」
3. `/health`、`/` 不受限（非 /api/v1 路径）
4. 改回 `false` → 立即放行（缓存失效验证）
5. 反向验证：后端日志出现 `[限流] 429 GET /api/v1/... client=...`

### 2.3 慢查询优化（交付项 3）

- 看板合并查询：`GET /api/v1/admin/dashboard` 6 项数值与 SQL 对账一致（对照 phase7 指南 §3 的 SQL）；
  开启 `DB_ECHO=true` 重启后端可观察：kb_document 相关由 2 条 SQL 合并为 1 条条件聚合
- Chroma 检索缓存：连续两次相同问题，第二次响应显著更快（Embedding 冷加载后）；
  上传新文档/删除文档后检索行为正常（缓存已失效）
- 分页防护：所有列表接口 page_size > 100 时按 100 截断（dependencies.pagination_params）

### 2.4 批量操作优化（交付项 4）

- 批量用户：`POST /api/v1/users/batch` `{"action":"disable","user_ids":[存在的,不存在的,自己]}` →
  自操作整体拦截 40000；不含自己时：存在的处理、**不存在的跳过并在 msg 中说明**（与原逐条报错不同）
- 批量向量化：`POST /api/v1/documents/batch-vectorize` 混合 completed/processing/pending/不存在 ID →
  结果数组逐条给出 triggered 与跳过原因（语义与原一致，单次提交）

---

## 3. 前端优化自测（交付项二）

### 3.1 虚拟滚动（对话历史侧边栏）

- 构造 50+ 条历史对话（批量创建或导入），打开「智能问答」→ DevTools 检查：
  侧边栏 DOM 中 conv-item 行数远小于 50（仅渲染可视区），滚动流畅、选中/重命名/删除正常

### 3.2 SSE 断线重连

- **自动重连**（提问后、首字到达前断网）：DevTools Network 设 Offline → 提问 → 观察到 1-2 次自动重试请求（间隔 1s/2s）→ 恢复 Online 前最终提示「网络已断开，请恢复网络后重试」
- **手动重试**（已收到部分回答后断网）：流中断后提示「连接已中断，请点击重试」，不自动重发（防重复计费——既定设计）
- 正常问答回归：meta → sources → delta → done 完整流

### 3.3 全局加载进度条

- 访问慢接口（如大文档列表/看板）时页面顶部出现滑动进度条，请求结束消失；快请求不闪烁（300ms 延迟）

### 3.4 组件复用与冗余清理回归

- 文档列表/详情：向量化状态标签、筛选下拉正常（VECTOR_STATUS_META 已统一到 utils/constants.ts）
- 各页面删除确认弹窗正常（统一 confirmDanger 封装）
- 登录/刷新 Token/SSE 携带 Token 正常（TOKEN_KEY 统一后行为不变）

### 3.5 质量脚本

```bash
cd ~/eakb/frontend
npm run type-check     # vue-tsc 0 错误
npm run lint:check     # eslint 无 error (warn 可接受)
npm run build          # 构建通过
```

---

## 4. 全量回归

1. `bash scripts/run_tests.sh` 全绿
2. 前端手测回归：登录 → 分类/文档 → 上传+向量化 → 模板 → 问答（含来源引用/反馈/多轮）→ 图谱 → 管理后台四页 → 权限边界（员工访问 admin URL 被弹回）
3. `npm run build` 通过
4. 将 VM 上 ruff/format 修改过的文件拷回 Windows

---

## 5. 交付核对清单（校验项四）

### 5.1 DESIGN.md 功能核对结果

8 大模块全部实现 ✅（认证/分类/文档/模板/RAG/图谱/管理后台/通用能力，见 README 功能清单）。
与 DESIGN.md 的差异（已核实，非遗漏）：

| 差异 | 说明 |
| --- | --- |
| `POST /rag/chat` 未实现 | 统一走 `POST /rag/chat-stream`（SSE），DESIGN 中的同步 chat 端点被流式替代 |
| 实际多出端点 | auth/refresh、PUT /auth/me、users/batch、PUT /categories/{id}/move、templates/{id}/categories 三件套、templates/{id}/render |
| 前端路由 | DESIGN 的 `/layout` 前缀实现为根路径直挂 AppLayout；`/dashboard` 实际 requiresAdmin（Phase 7 调整） |
| conversations 模块 | 挂 `/rag` 前缀下（DESIGN 中独立 conversations.py 并入 rag.py） |

### 5.2 数据库表核对结果

10 张表全部落地，字段/索引/枚举与 DESIGN.md 4.1 对齐 ✅。核对明细：

| 表 | 索引 | 结论 |
| --- | --- | --- |
| sys_user / sys_operation_log / kb_category / kb_document / kb_document_chunk / sys_config / pt_template / pt_template_category / rag_conversation / rag_message | 全部与 DESIGN 一致（unique/enum 均匹配） | ✅ |
| kb_document | 实际多 `error_message TEXT` 字段（向量化失败原因, Phase 3 设计深化） | 文档已记录 |
| 迁移链 | 0001→0002→0003→0004→0005→**0006(Phase 8 限流种子键)** | ✅ |

### 5.3 目录分层核对结果

- backend/app：core / models / schemas / utils / services / api/v1 分层与 CLAUDE.md 第二章完全一致 ✅
- 路由无业务逻辑（api 仅参数校验 + 调用 service）、service 收敛全部 DB/第三方调用 ✅
- Phase 8 清理：删除空壳文件 `app/api/deps.py`（仅 docstring、无引用）；限流中间件收敛在 core/rate_limit.py ✅
- 前端：views / components(common|chat|layout) / composables / stores / api / types / utils 分层符合 ✅

### 5.4 交付物清单

| 交付物 | 位置 |
| --- | --- |
| 全量 API 接口文档 | docs/api-reference.md |
| 生产部署文档 | docs/deployment.md |
| 项目 README | README.md |
| 本验收清单 | docs/phase8-test-guide.md |
| 一键部署 | `sudo docker compose -f docker-compose.prod.yml up -d --build`（见 deployment.md §3） |
| 单测脚本 | scripts/run_tests.sh |
| 质量校验脚本 | scripts/check_quality.sh / scripts/format_code.sh |
| 数据备份脚本 | scripts/backup.sh |
| 新增基础设施 | backend/Dockerfile、frontend/Dockerfile、frontend/nginx.conf、deploy/nginx-eakb.conf、docker-compose.prod.yml、.gitignore |

### 5.5 已知边界（继承自前阶段 + Phase 8）

- 批量操作（向量化触发/用户批量）单次提交但非跨服务事务；用户批量对不存在的 ID 跳过（Phase 8 行为变更）
- 限流为单进程内存计数：多实例部署时按实例各自计数（当前 --workers 1 部署不受影响）
- Chroma 检索缓存 TTL 5 分钟 / 容量 512，写入即失效；多实例下各实例独立缓存
- 日志时间筛选需本地时间字符串（不带 Z）；看板"今日"按服务器本地零点
- SSE 收到部分内容后断线不自动重发（防 LLM 重复计费的既定设计）

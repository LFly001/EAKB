# EAKB 生产部署文档 (Phase 8)

> 本文档覆盖 EAKB 生产部署完整流程：环境准备、两种部署路径（容器化完整编排 / 裸机部署）、Nginx 反向代理（含 SSE 透传）、数据备份、日志收集、服务启停与安全检查清单。
> 开发环境快速启动请见 [README.md](../README.md)。

---

## 1. 部署架构

```
浏览器 ──> Nginx (前端静态 + /api 反代, SSE 透传) ──> FastAPI 后端 (:8000)
                                                          ├── MySQL 8.0 (:3306)
                                                          ├── Neo4j 5.x (:7687)
                                                          ├── MinIO (:9000)
                                                          ├── Chroma (本地持久化目录)
                                                          └── LLM API (DeepSeek 外部服务)
```

两种部署路径：

| 路径 | 适用场景 | 说明 |
| --- | --- | --- |
| **A. 容器化完整编排** | 标准生产交付 (CLAUDE.md §11.1) | `docker-compose.prod.yml` 一键拉起全部 5 个服务 |
| **B. 裸机 + Nginx** | 当前开发 VM 实践、小规模生产 | Docker 仅跑中间件，后端 venv + uvicorn + systemd，Nginx 托管前端 |

---

## 2. 前置准备（两条路径通用）

### 2.1 环境要求

- Ubuntu 24.04+（项目声明 26.04，24.04 实测可用），Docker ≥ 24 + compose 插件
- 路径 A 需要：Docker 仅此即可（镜像内自带 Python 3.14 / Node 20）
- 路径 B 需要：Python 3.14、Node 20+、Nginx；系统依赖安装见 `scripts/init_ubuntu.sh`

### 2.2 Docker 镜像加速（国内网络必需）

Docker Hub 被墙时配置镜像加速器：

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<'EOF'
{ "registry-mirrors": ["https://docker.m.daocloud.io", "https://dockerproxy.com"] }
EOF
sudo systemctl restart docker
```

### 2.3 本地 Embedding 模型（离线准备）

项目默认使用本地 bge-large-zh-v1.5 做向量化（不依赖外部 Embedding API）。HF 直连不可用时用 ModelScope 下载：

```bash
pip install modelscope
python -c "from modelscope import snapshot_download; print(snapshot_download('BAAI/bge-large-zh-v1.5'))"
# 记录输出目录, 如 /home/kun/.cache/modelscope/models/BAAI--bge-large-zh-v1.5/snapshots/master
```

- 路径 A：把模型目录挂载进后端容器（见 §3.3）
- 路径 B：`.env` 中 `EMBEDDING_MODEL_NAME` 直接指向该目录

### 2.4 环境变量

```bash
cp .env.example .env   # 修改实际值: JWT_SECRET_KEY(必改)、LLM_API_KEY、各服务密码
```

生产环境必须修改：`JWT_SECRET_KEY`（随机 32+ 字符）、MySQL/Neo4j/MinIO 密码、`LLM_API_KEY`。
生产参数建议：`APP_ENV=production`、`DEBUG=false`。

---

## 3. 路径 A：容器化完整编排（标准生产）

### 3.1 目录准备

```bash
# 将 bge 模型放入项目 models 目录 (compose 默认挂载 ./models 到容器 /models)
mkdir -p ~/eakb/models
# ⚠️ 必须用 cp -r 真实拷贝, 不能用 ln -s 符号链接:
# Docker bind mount 不会解析符号链接的宿主目标, 容器内会是悬空链接,
# 表现为问答报 "Embedding 模型未初始化" (模型路径不存在)
cp -r /home/kun/.cache/modelscope/models/BAAI--bge-large-zh-v1.5/snapshots/master \
  ~/eakb/models/bge-large-zh-v1.5
```

### 3.2 一键启动

```bash
# 先停掉开发态后端 (容器同样映射 8000 端口)
cd ~/eakb
sudo docker compose -f docker-compose.prod.yml up -d --build
```

编排内容：MySQL / Neo4j / MinIO（含健康检查）+ 后端（启动自动执行 `alembic upgrade head`）+ 前端 Nginx。
首次构建较慢（torch CPU 版 + sentence-transformers 较大）；前后端构建上下文已用 .dockerignore 排除 venv/node_modules 等大目录。

数据衔接说明：
- Chroma 直接绑定挂载宿主 `./backend/chroma_data`（可用 `EAKB_CHROMA_DIR` 覆盖），开发期向量数据无缝延续，无需重新向量化
- Embedding 模型挂载 `./models`（可用 `EAKB_EMBEDDING_MODEL_DIR` 覆盖），容器内固定路径 `/models/bge-large-zh-v1.5`
- 容器内 `EMBEDDING_MODEL_NAME` 由 compose 硬编码覆盖（不能写成 `${EMBEDDING_MODEL_NAME}` 插值——.env 中同名键会插值出宿主路径）

### 3.3 验证

```bash
sudo docker compose -f docker-compose.prod.yml ps        # 5 个服务均 healthy
curl http://127.0.0.1:8000/health                        # {"status":"ok",...}
curl -I http://127.0.0.1/                                # 前端 200
```

浏览器访问 `http://<服务器IP>/`，用初始管理员账号登录（初始化见 README「账号初始化」）。

### 3.4 数据卷清单

| 卷 | 内容 | 备份方式 |
| --- | --- | --- |
| `eakb_mysql_data` | 业务数据 | mysqldump 逻辑备份 |
| `./backend/chroma_data`（绑定挂载） | 向量库 | tar 打包（或与 MySQL 同点备份） |
| `eakb_minio_data` | 原始文件 | `mc mirror` 镜像桶 |
| `eakb_neo4j_data` | 图谱 | `neo4j-admin database dump`（可选） |

---

## 4. 路径 B：裸机部署 + Nginx（当前 VM 实践）

### 4.1 依赖服务（Docker）

```bash
cd ~/eakb
sudo docker compose up -d        # MySQL / Neo4j / MinIO
sudo docker compose ps           # 确认 healthy
```

### 4.2 后端

```bash
cd ~/eakb/backend
python3.14 -m venv venv          # 首次; 已存在则跳过
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install torch --index-url https://download.pytorch.org/whl/cpu   # 必须先装 CPU 版
pip install -r requirements.txt

# 数据库迁移 (迁移文件需已同步到 VM — Windows→VM 同步偶尔滞后)
alembic upgrade head

# 生产启动 (uvicorn)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

> 注意：后端含 Embedding 模型内存加载与 Chroma 本地持久化，**多 worker 会重复加载模型且 Chroma PersistentClient 多进程并发写不安全**，生产保持 `--workers 1`，横向扩展时拆出 Embedding/向量库为独立服务。

### 4.3 systemd 守护（推荐）

`/etc/systemd/system/eakb-backend.service`：

```ini
[Unit]
Description=EAKB FastAPI Backend
After=network.target docker.service

[Service]
User=kun
WorkingDirectory=/home/kun/eakb/backend
ExecStart=/home/kun/eakb/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=5
EnvironmentFile=/home/kun/eakb/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now eakb-backend
sudo systemctl status eakb-backend
```

### 4.4 前端构建

```bash
cd ~/eakb/frontend
npm ci
npm run build      # vue-tsc 类型检查 + vite 构建 → dist/
```

### 4.5 Nginx 反向代理

```bash
sudo apt install -y nginx
sudo cp ~/eakb/deploy/nginx-eakb.conf /etc/nginx/sites-available/eakb.conf
sudo ln -s /etc/nginx/sites-available/eakb.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

SSE 透传三要素（配置已包含）：`proxy_buffering off`、`proxy_cache off`、`proxy_read_timeout 3600s`。**若前端出现流式回答挂起/断流，首先检查反代缓冲配置。**

### 4.6 验证

```bash
curl http://127.0.0.1:8000/health
curl -I http://192.168.1.80/                 # 前端 200
curl -N -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"question":"年假怎么申请"}' \
  http://192.168.1.80/api/v1/rag/chat-stream  # 应看到 event: meta / delta 帧连续输出
```

---

## 5. 数据备份（CLAUDE.md §11.6）

一键备份 MySQL + Chroma + MinIO：

```bash
bash ~/eakb/scripts/backup.sh /srv/eakb-backups
```

定时备份（每天 02:30）：

```bash
crontab -e
# 追加:
30 2 * * * bash /home/kun/eakb/scripts/backup.sh /srv/eakb-backups >> /var/log/eakb-backup.log 2>&1
```

保留策略（清理 7 天前备份，放入 cron）：

```bash
find /srv/eakb-backups -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \;
```

恢复流程（MySQL 为例）：

```bash
docker exec -i eakb-mysql sh -c "exec mysql -ueakb -peakb123456 eakb" < mysql_eakb_XXXX.sql
# Chroma: tar 解回 backend/chroma_data 后重启后端
# MinIO: mc mirror 反向同步回桶
```

---

## 6. 日志收集

| 来源 | 位置 / 命令 |
| --- | --- |
| 后端应用日志（loguru） | uvicorn 标准输出；systemd 路径下 `journalctl -u eakb-backend -f` |
| 后端文件日志（可选） | uvicorn `--log-config` 或重定向：`uvicorn ... >> /var/log/eakb/backend.log 2>&1` |
| 中间件容器日志 | `sudo docker compose logs -f --tail=200 mysql` |
| Nginx 访问/错误日志 | `/var/log/nginx/access.log` / `error.log` |
| 操作审计日志 | 业务库 `sys_operation_log` 表（只读审计，接口无删除入口） |

生产环境关闭详细异常堆栈：`.env` 中 `APP_ENV=production`（全局异常处理器会自动隐藏内部细节，仅返回友好提示，细节留在日志）。

---

## 7. 服务启停速查

```bash
# 路径 A (容器化)
sudo docker compose -f docker-compose.prod.yml up -d --build     # 启动/更新
sudo docker compose -f docker-compose.prod.yml down              # 停止
sudo docker compose -f docker-compose.prod.yml restart backend   # 单服务重启

# 路径 B (裸机)
sudo systemctl restart eakb-backend                              # 重启后端
sudo systemctl stop eakb-backend                                 # 停止后端
sudo docker compose up -d / sudo docker compose down             # 中间件启停
sudo systemctl reload nginx                                      # 重载 Nginx 配置
```

---

## 8. 生产安全检查清单

- [ ] `.env` 中 JWT_SECRET_KEY / 各服务密码已改为强随机值，非示例值
- [ ] `APP_ENV=production`、`DEBUG=false`（关闭 /docs、异常堆栈）
- [ ] CORS 白名单 `FRONTEND_URL` 指向真实前端域名，未使用 `*`
- [ ] LLM Key / 数据库密码仅存于 `.env`，未硬编码、未提交仓库（已附 .gitignore）
- [ ] 接口限流：管理后台「系统配置」中 `rate_limit_enabled` 设为 true（默认关闭）
- [ ] Nginx 已限制上传体积（`client_max_body_size` 与 UPLOAD_MAX_SIZE_MB 一致）
- [ ] 定时备份任务已配置并做过一次恢复演练
- [ ] 服务器防火墙仅开放 80/443（及管理用 22），3306/7687/9000 不对公网暴露

---

## 9. 常见问题

| 现象 | 排查 |
| --- | --- |
| 流式回答中途挂起 | 检查反代 `proxy_buffering off`；后端日志是否有 LLM 超时 |
| Docker 拉镜像失败 | 配置 §2.2 镜像加速器后 `sudo systemctl restart docker` |
| 后端启动报连接 MySQL 失败 | 容器名/网络：容器内用服务名 `mysql`；裸机用 `127.0.0.1` |
| alembic 迁移未生效 | 确认迁移文件已从 Windows 同步到 VM（同步偶发滞后） |
| 向量化报嵌入模型加载失败 | 确认模型目录存在且 `EMBEDDING_MODEL_NAME` 指向正确路径 |
| 首次问答很慢 | Embedding 模型冷加载（启动阶段已预热，重启后第一次问答 10-60s 属正常） |
| 重启后端后图谱查询超时 | 已知冷启动现象，第二次请求恢复；超时自动降级纯向量检索 |

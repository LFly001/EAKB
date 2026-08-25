#!/usr/bin/env bash
# ============================================================
# EAKB — Ubuntu 26.04 一键初始化脚本
# 系统依赖 + Python 3.14 虚拟环境 + 后端依赖安装
# ============================================================
set -euo pipefail

# ---- 颜色 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

log_info "========================================="
log_info " EAKB 企业知识库智能助手 — Ubuntu 初始化"
log_info " 适配: Ubuntu 26.04 / Python 3.14.4"
log_info "========================================="

# ==========================================
# 1. 安装系统依赖
# ==========================================
log_info "[1/5] 安装系统依赖..."

sudo apt update

sudo apt install -y \
    python3.14 \
    python3.14-dev \
    python3.14-venv \
    build-essential \
    libmysqlclient-dev \
    libssl-dev \
    pkg-config \
    curl \
    wget \
    git \
    poppler-utils \
    libreoffice-core \
    libreoffice-writer \
    libmagic1 \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    ca-certificates \
    gnupg \
    lsb-release

log_info "系统依赖安装完成"

# ==========================================
# 2. 安装 Docker & Docker Compose (可选)
# ==========================================
log_info "[2/5] 检查 Docker 环境..."

if command -v docker &> /dev/null; then
    log_info "Docker 已安装: $(docker --version)"
else
    log_warn "Docker 未安装。如需使用 docker-compose 管理中间件，请安装:"
    log_warn "  curl -fsSL https://get.docker.com | sudo sh"
    log_warn "  sudo usermod -aG docker \$USER"
fi

if docker compose version &> /dev/null 2>&1; then
    log_info "Docker Compose 已安装"
else
    log_warn "Docker Compose 插件未找到"
fi

# ==========================================
# 3. 创建 Python 3.14 虚拟环境
# ==========================================
log_info "[3/5] 创建 Python 3.14 虚拟环境..."

cd "$PROJECT_ROOT/backend"

if [ -d ".venv" ]; then
    log_warn "虚拟环境 .venv 已存在，跳过创建"
else
    python3.14 -m venv .venv
    log_info "虚拟环境 .venv 创建成功"
fi

# 激活虚拟环境 (source)
source .venv/bin/activate

# 确认 Python 版本
PY_VER=$(python --version)
log_info "Python 版本: $PY_VER"

# ==========================================
# 4. 安装后端 Python 依赖
# ==========================================
log_info "[4/5] 升级 pip + 安装项目依赖..."

python -m pip install --upgrade pip setuptools wheel

# 安装所有依赖
pip install -r requirements.txt

log_info "Python 依赖安装完成"

# ==========================================
# 5. 初始化环境变量
# ==========================================
log_info "[5/5] 初始化环境变量..."

cd "$PROJECT_ROOT"

if [ -f ".env" ]; then
    log_warn ".env 文件已存在，跳过复制"
else
    cp .env.example .env
    log_info ".env 文件已从 .env.example 复制"
    log_warn ">>> 请编辑 .env 文件，填写真实的 LLM API Key、数据库密码等敏感配置 <<<"
fi

# ==========================================
# 6. 验证安装
# ==========================================
log_info "========================================="
log_info " 安装验证"
log_info "========================================="

# 验证关键包
cd "$PROJECT_ROOT/backend"
source .venv/bin/activate

echo ""
echo "--- Python 版本 ---"
python --version

echo ""
echo "--- 关键依赖检查 ---"
DEPS=("fastapi" "sqlalchemy" "llama_index" "chromadb" "neo4j" "minio" "pydantic" "bcrypt" "jose" "uvicorn" "alembic" "httpx")
for dep in "${DEPS[@]}"; do
    if pip show "$dep" &> /dev/null; then
        VER=$(pip show "$dep" 2>/dev/null | grep "^Version:" | awk '{print $2}')
        echo -e "  ${GREEN}✓${NC} $dep ($VER)"
    else
        echo -e "  ${RED}✗${NC} $dep — 未安装"
    fi
done

echo ""
log_info "========================================="
log_info " 初始化完成!"
log_info "========================================="
echo ""
echo "后续步骤:"
echo "  1. 编辑项目根目录 .env 文件，配置数据库密码和 LLM API Key"
echo ""
echo "  2. 启动 Docker 中间件:"
echo "     cd $PROJECT_ROOT"
echo "     docker compose up -d"
echo ""
echo "  3. 执行数据库迁移:"
echo "     cd $PROJECT_ROOT/backend"
echo "     source .venv/bin/activate"
echo "     alembic upgrade head"
echo ""
echo "  4. 启动后端服务:"
echo "     cd $PROJECT_ROOT/backend"
echo "     source .venv/bin/activate"
echo "     uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "  5. 启动前端开发服务:"
echo "     cd $PROJECT_ROOT/frontend"
echo "     npm install"
echo "     npm run dev"
echo ""
echo "  6. 访问服务:"
echo "     API 文档:   http://localhost:8000/docs"
echo "     健康检查:   http://localhost:8000/health"
echo "     前端页面:   http://localhost:5173"
echo "     MinIO 控制台: http://localhost:9001"
echo "     Neo4j 浏览器: http://localhost:7474"

# ============================================================
# EAKB 后端生产镜像 (Phase 8)
# 基础镜像: python:3.14-slim (对齐项目 Python 3.14.4 约束)
# 注意: torch 必须从 CPU 源单独安装 (PyPI 默认 CUDA 版依赖 4-5GB,
#       且镜像构建环境无 GPU), 再安装 requirements.txt
# ============================================================
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 依赖安装 (分层缓存: 先装 torch CPU 版, 再装项目依赖)
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install -r requirements.txt

# 应用代码 + 迁移脚本 + 质量工具配置
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ruff.toml mypy.ini pytest.ini ./

EXPOSE 8000

# 启动前执行数据库迁移, 再拉起服务
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

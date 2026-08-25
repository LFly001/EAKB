#!/usr/bin/env bash
# ============================================================
# EAKB 数据备份脚本 (CLAUDE.md 部署规范 §11.6)
# 备份内容: MySQL 逻辑备份 (mysqldump) / Chroma 持久化目录 / MinIO 存储桶
# 用法 (VM 项目根目录 ~/eakb 下执行):
#   bash scripts/backup.sh                    # 备份到 ./backups/<日期>/
#   bash scripts/backup.sh /srv/eakb-backups  # 指定备份根目录
#
# 建议配合 crontab 定时执行, 例如每天 02:30:
#   30 2 * * * bash /home/kun/eakb/scripts/backup.sh /srv/eakb-backups >> /var/log/eakb-backup.log 2>&1
# ============================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

BACKUP_ROOT="${1:-$PROJECT_DIR/backups}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/$STAMP"
mkdir -p "$BACKUP_DIR"

# ---- 读取 .env (兼容 CRLF 换行) ----
if [ -f .env ]; then
  # shellcheck disable=SC2046
  export $(sed 's/\r$//' .env | grep -v '^#' | grep -v '^$' | xargs -d '\n') 2>/dev/null || true
fi

MYSQL_CONTAINER="${MYSQL_CONTAINER:-eakb-mysql}"
MYSQL_DB="${MYSQL_DATABASE:-eakb}"
MYSQL_USER="${MYSQL_USER:-eakb}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-eakb123456}"

echo "============================================================"
echo "EAKB 数据备份 — 目标: $BACKUP_DIR"
echo "============================================================"

# ---- 1. MySQL 逻辑备份 ----
echo ">>> 1/3 MySQL 备份 (mysqldump)"
if docker ps --format '{{.Names}}' | grep -q "^${MYSQL_CONTAINER}$"; then
  docker exec "$MYSQL_CONTAINER" sh -c \
    "exec mysqldump --default-character-set=utf8mb4 -u$MYSQL_USER -p$MYSQL_PASSWORD $MYSQL_DB" \
    > "$BACKUP_DIR/mysql_${MYSQL_DB}_${STAMP}.sql"
  echo "    -> $BACKUP_DIR/mysql_${MYSQL_DB}_${STAMP}.sql ($(du -h "$BACKUP_DIR/mysql_${MYSQL_DB}_${STAMP}.sql" | cut -f1))"
else
  echo "    [警告] 容器 $MYSQL_CONTAINER 未运行, 跳过 MySQL 备份"
fi

# ---- 2. Chroma 持久化目录 ----
echo ">>> 2/3 Chroma 向量库备份 (tar)"
CHROMA_DIR="${CHROMA_PERSIST_DIR:-$PROJECT_DIR/backend/chroma_data}"
if [ -d "$CHROMA_DIR" ]; then
  tar czf "$BACKUP_DIR/chroma_data_${STAMP}.tar.gz" -C "$(dirname "$CHROMA_DIR")" "$(basename "$CHROMA_DIR")"
  echo "    -> $BACKUP_DIR/chroma_data_${STAMP}.tar.gz ($(du -h "$BACKUP_DIR/chroma_data_${STAMP}.tar.gz" | cut -f1))"
else
  echo "    [警告] Chroma 目录不存在 ($CHROMA_DIR), 跳过"
fi

# ---- 3. MinIO 存储桶 ----
echo ">>> 3/3 MinIO 存储桶备份 (mc mirror)"
MINIO_BUCKET="${MINIO_BUCKET:-eakb-documents}"
if command -v mc >/dev/null 2>&1; then
  mc alias set eakb-local "http://${MINIO_ENDPOINT:-127.0.0.1:9000}" \
    "${MINIO_ACCESS_KEY:-minioadmin}" "${MINIO_SECRET_KEY:-minioadmin123456}" >/dev/null
  mc mirror --overwrite "eakb-local/$MINIO_BUCKET" "$BACKUP_DIR/minio_${MINIO_BUCKET}/" >/dev/null
  echo "    -> $BACKUP_DIR/minio_${MINIO_BUCKET}/ ($(du -sh "$BACKUP_DIR/minio_${MINIO_BUCKET}" 2>/dev/null | cut -f1))"
else
  echo "    [警告] 未安装 mc 客户端, 跳过 MinIO 备份"
  echo "    安装: curl https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc && chmod +x /usr/local/bin/mc"
fi

echo "============================================================"
echo "✅ 备份完成: $BACKUP_DIR"
echo "   保留策略建议: 定期清理 N 天前的旧备份, 如:"
echo "   find $BACKUP_ROOT -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \;"
echo "============================================================"

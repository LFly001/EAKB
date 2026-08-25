#!/usr/bin/env bash
# ============================================================
# EAKB 后端代码格式化 (Phase 8: ruff format + ruff check --fix)
# 用法 (VM 项目根目录 ~/eakb 下执行):
#   bash scripts/format_code.sh
#
# ⚠️ 重要: ruff --fix 会直接修改文件, 本机 (VM) 修改后的文件
#   必须拷回 Windows (d:\Project\eakb), 否则下次 Windows→VM
#   单向同步会把修复覆盖回退、ruff 重新报错。
# ============================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR/backend"

if [ -d "venv" ]; then
  VENV_DIR="venv"
elif [ -d ".venv" ]; then
  VENV_DIR=".venv"
else
  echo "[错误] 未找到虚拟环境 (venv/.venv)"
  exit 1
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo ">>> ruff format (统一格式)"
ruff format app tests alembic

echo ">>> ruff check --fix (自动修复可修复项)"
ruff check --fix app tests alembic

echo ">>> 校验剩余问题 (不可自动修复项需手工处理)"
ruff check app tests alembic

echo ""
echo "✅ 格式化完成 — 请将修改后的文件拷回 Windows 端"

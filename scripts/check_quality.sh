#!/usr/bin/env bash
# ============================================================
# EAKB 后端代码质量校验 (提交前必须通过)
# 检查项: ruff 格式检查 + ruff lint + mypy 类型校验
# 用法 (VM 项目根目录 ~/eakb 下执行):
#   bash scripts/check_quality.sh
#
# ⚠️ 注意: 若 ruff format --check / ruff check 报差异, 先执行
#   bash scripts/format_code.sh 自动修复, 修复后的文件需同步回 Windows
#   (VM → Windows 拷回, 避免下次单向同步覆盖回退)
# ============================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR/backend"

# 虚拟环境探测 (兼容 venv 与 .venv)
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

PASS=1

step() { echo ""; echo ">>> $1"; }

step "1/3 ruff 格式检查 (ruff format --check)"
if ! ruff format --check app tests alembic; then
  echo "[失败] 格式不统一, 执行 bash scripts/format_code.sh 修复"
  PASS=0
fi

step "2/3 ruff lint 检查 (ruff check)"
if ! ruff check app tests alembic; then
  echo "[失败] lint 未通过"
  PASS=0
fi

step "3/3 mypy 类型校验 (mypy app)"
if ! mypy app; then
  echo "[失败] 类型校验未通过"
  PASS=0
fi

echo ""
if [ "$PASS" -eq 1 ]; then
  echo "✅ 全部检查通过, 可以提交"
  exit 0
else
  echo "❌ 存在未通过项, 请修复后重新执行"
  exit 1
fi

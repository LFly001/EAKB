#!/usr/bin/env bash
# ============================================================
# EAKB 后端单元测试执行脚本
# 用法 (VM 项目根目录 ~/eakb 下执行):
#   bash scripts/run_tests.sh            # 全量执行 (排除 Neo4j 集成测试)
#   bash scripts/run_tests.sh -k auth    # 按关键字过滤
#   bash scripts/run_tests.sh --include-neo4j   # 含 Neo4j 集成测试 (需 NEO4J_TEST_URI)
# ============================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR/backend"

# 虚拟环境探测 (兼容 venv 与 .venv 两种目录名)
if [ -d "venv" ]; then
  VENV_DIR="venv"
elif [ -d ".venv" ]; then
  VENV_DIR=".venv"
else
  echo "[错误] 未找到虚拟环境 (venv/.venv), 请先执行 scripts/init_ubuntu.sh"
  exit 1
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

EXTRA_ARGS=("$@")
INCLUDE_NEO4J=0
FILTERED_ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--include-neo4j" ]; then
    INCLUDE_NEO4J=1
  else
    FILTERED_ARGS+=("$arg")
  fi
done

echo "============================================================"
echo "EAKB 单元测试 — pytest (venv: $VENV_DIR)"
echo "============================================================"

if [ "$INCLUDE_NEO4J" -eq 1 ]; then
  echo "[提示] 包含 Neo4j 集成测试, 需设置 NEO4J_TEST_URI 环境变量"
  pytest tests/ -v "${FILTERED_ARGS[@]}"
else
  echo "[提示] 已排除 Neo4j 集成测试 (test_graph_neo4j_integration.py)"
  echo "       需要跑集成测试时: bash scripts/run_tests.sh --include-neo4j"
  pytest tests/ -v --ignore=tests/test_graph_neo4j_integration.py "${FILTERED_ARGS[@]}"
fi

echo "============================================================"
echo "测试完成 (退出码 $?)"
echo "============================================================"

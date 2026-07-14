#!/usr/bin/env bash
# ============================================================
# CBase 停止所有服务
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$SCRIPT_DIR"

echo "停止所有服务..."

# 停止 Docker Compose 容器
cd "$ROOT"
if command -v docker &>/dev/null; then
    docker compose down 2>/dev/null && echo "  容器已停止" || true
fi

# 停止原生进程（按端口）
for port in 8000 8080 5173; do
    pid=$(ss -tlnp "sport = :$port" 2>/dev/null | grep -oP 'pid=\K\d+' 2>/dev/null || true)
    if [ -n "$pid" ]; then
        kill "$pid" 2>/dev/null || true
        echo "  端口 $port (PID $pid) 已停止"
    fi
done

echo "全部停止"

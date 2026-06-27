#!/usr/bin/env bash
# ============================================================
# 企业知识助手 — 停止所有服务
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$SCRIPT_DIR"

echo "停止所有服务..."

# 停止 Docker Compose 服务
cd "$ROOT"
docker compose down 2>/dev/null && echo "  基础设施已停止" || echo "  基础设施未运行或已停止"

# 停止通过启动脚本启动的后台进程（按端口查杀）
for port in 8000 8080 5173; do
    pid=$(lsof -ti ":$port" 2>/dev/null || true)
    if [ -n "$pid" ]; then
        kill "$pid" 2>/dev/null || true
        echo "  端口 $port (PID $pid) 已停止"
    fi
done

echo "所有服务已停止"

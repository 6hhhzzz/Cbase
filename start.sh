#!/usr/bin/env bash
# ============================================================
# 企业知识助手 — 一键启动脚本
# 启动顺序: 基础设施 → Python AI → Java Backend → Frontend
# ============================================================
set -e

# ---- 路径解析（脚本可在任意位置执行） ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$SCRIPT_DIR"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +%H:%M:%S)] WARN${NC} $1"; }
err()  { echo -e "${RED}[$(date +%H:%M:%S)] ERROR${NC} $1"; }

# 后台进程 PID 记录
PIDS=()
cleanup() {
    echo ""
    log "正在关闭所有服务..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    log "所有服务已关闭"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ---- 前置检查 ----
check_prereqs() {
    local missing=0

    if ! command -v docker &>/dev/null; then
        err "未找到 docker，请先安装 Docker"
        missing=1
    fi

    if ! command -v uv &>/dev/null; then
        err "未找到 uv，请先安装 uv (https://docs.astral.sh/uv/)"
        missing=1
    fi

    if ! command -v mvn &>/dev/null; then
        err "未找到 mvn，请先安装 Maven"
        missing=1
    fi

    if ! command -v node &>/dev/null; then
        err "未找到 node，请先安装 Node.js"
        missing=1
    fi

    if [ "$missing" -ne 0 ]; then
        exit 1
    fi
    log "前置检查通过"
}

# ---- 阶段 1: 基础设施 ----
start_infra() {
    log "启动基础设施 (Docker Compose)..."
    cd "$ROOT"
    docker compose up -d

    log "等待服务健康检查..."
    local services=(postgres redis rabbitmq minio)
    local timeout=120
    local elapsed=0

    for svc in "${services[@]}"; do
        while [ $elapsed -lt $timeout ]; do
            local status
            status=$(docker compose ps --format json "$svc" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Health',''))" 2>/dev/null || echo "")
            if [ "$status" = "healthy" ]; then
                log "  $svc: healthy"
                break
            fi
            sleep 2
            elapsed=$((elapsed + 2))
        done
        if [ $elapsed -ge $timeout ]; then
            warn "  $svc: 健康检查超时，继续启动其他服务"
        fi
    done
    log "基础设施就绪"
}

# ---- 阶段 2: Python AI Service ----
start_python() {
    log "启动 Python AI Service (端口 8000)..."
    cd "$ROOT/ai-service"

    if [ -z "$DASHSCOPE_API_KEY" ]; then
        warn "DASHSCOPE_API_KEY 未设置，Python 服务启动时会报错"
        warn "请设置: export DASHSCOPE_API_KEY='your-key' 后重新运行"
    fi

    uv run uvicorn api.app:app --host 0.0.0.0 --port 8000 &
    PIDS+=($!)
    log "Python AI Service PID: ${PIDS[-1]}"
}

# ---- 阶段 3: Java Backend ----
start_java() {
    log "编译并启动 Java Backend (端口 8080)..."
    cd "$ROOT/backend"
    mvn spring-boot:run -q &
    PIDS+=($!)
    log "Java Backend PID: ${PIDS[-1]}"
}

# ---- 阶段 4: Frontend ----
start_frontend() {
    log "启动 Frontend (端口 5173)..."
    cd "$ROOT/frontend"

    if [ ! -d "node_modules" ]; then
        log "安装前端依赖..."
        npm install
    fi

    npm run dev &
    PIDS+=($!)
    log "Frontend PID: ${PIDS[-1]}"
}

# ---- 主流程 ----
main() {
    echo ""
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}     企业知识助手 — 一键启动${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""

    check_prereqs

    # 阶段 1: 基础设施（同步等待）
    start_infra

    # 阶段 2-4: 应用服务（并行启动）
    log "启动应用服务..."
    start_python
    sleep 2  # 给 Python 一点初始化时间
    start_java
    start_frontend

    echo ""
    echo -e "${BLUE}============================================${NC}"
    echo -e "${GREEN}  启动完成!${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""
    echo "  前端:       http://localhost:5173"
    echo "  Java API:   http://localhost:8080"
    echo "  Python API: http://localhost:8000"
    echo "  API 文档:   http://localhost:8000/docs"
    echo "  RabbitMQ:   http://localhost:15672  (kes/kes123)"
    echo "  MinIO:      http://localhost:9001  (minioadmin/minioadmin)"
    echo ""
    echo "  按 Ctrl+C 停止所有服务"
    echo ""

    # 等待所有后台进程
    wait
}

main "$@"

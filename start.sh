#!/usr/bin/env bash
# ============================================================
# CBase 一键启动
#
# 用法:
#   ./start.sh              Docker 模式（推荐）
#   ./start.sh --dev        开发模式（本地热重载，需要先跑 ./setup.sh）
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$SCRIPT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +%H:%M:%S)] WARN${NC} $1"; }
err()  { echo -e "${RED}[$(date +%H:%M:%S)] ERROR${NC} $1"; }

MODE="${1:-docker}"

# ---- Docker 模式 ----
start_docker() {
    log "Docker 模式启动..."

    if ! command -v docker &>/dev/null; then
        err "Docker 未安装，请先安装 Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi

    cd "$ROOT"

    # 检查 .env 中是否有 API Key
    if [ ! -f ".env" ] || ! grep -q "DASHSCOPE_API_KEY=sk-" .env 2>/dev/null; then
        warn "DASHSCOPE_API_KEY 未配置，AI 相关功能将不可用"
        warn "请编辑 .env 填入你的 API Key"
    fi

    log "构建镜像并启动..."
    docker compose up -d --build

    log "等待服务就绪..."
    sleep 3

    echo ""
    echo -e "${BLUE}============================================${NC}"
    echo -e "${GREEN}  CBase 启动完成${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""
    echo "  前端:       http://localhost"
    echo "  Java Backend: http://localhost:8080"
    echo "  Python AI:  http://localhost:8000/docs"
    echo "  RabbitMQ:   http://localhost:15672"
    echo "  MinIO:      http://localhost:9001"
    echo ""
    echo "  查看日志:   docker compose logs -f"
    echo "  停止服务:   ./stop.sh"
}

# ---- 开发模式（本地进程，热重载） ----
start_dev() {
    log "开发模式启动（本地进程）..."

    # 检查依赖
    for cmd in docker mvn uv node; do
        if ! command -v "$cmd" &>/dev/null; then
            err "$cmd 未安装，请先运行 ./setup.sh"
            exit 1
        fi
    done

    if [ ! -f "$ROOT/.env" ]; then
        cp "$ROOT/.env.example" "$ROOT/.env"
        warn "已创建 .env，请编辑填入 DASHSCOPE_API_KEY 后重新启动"
        exit 1
    fi
    # 加载 .env 中的环境变量（已有环境变量优先，不覆盖）
    # 系统级环境变量（如 /etc/environment、~/.bashrc 中 export 的）优先级更高
    while IFS= read -r _line; do
        # 跳过空行和注释
        [[ -z "$_line" || "$_line" =~ ^[[:space:]]*# ]] && continue
        # 提取 key=value（处理 value 中含 = 的情况）
        _key="${_line%%=*}"
        _value="${_line#*=}"
        [[ -z "$_key" || "$_key" == "$_line" ]] && continue
        # 仅当变量未设置时才从 .env 导入
        if [[ -z "${!_key}" ]]; then
            export "$_key=$_value"
        fi
    done < "$ROOT/.env"

    PIDS=()
    cleanup() {
        echo ""
        log "正在关闭所有服务..."
        for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
        log "已关闭"
        exit 0
    }
    trap cleanup SIGINT SIGTERM

    # 1. 基础设施
    log "启动基础设施..."
    cd "$ROOT"; docker compose up -d postgres redis rabbitmq minio
    sleep 3

    # 2. Python (热重载)
    log "启动 Python AI Service (http://localhost:8000)..."
    cd "$ROOT/ai-service"
    uv run uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload &
    PIDS+=($!)

    # 3. Java (mvn spring-boot:run 自带热重载)
    log "启动 Java Backend (http://localhost:8080)..."
    cd "$ROOT/backend"
    mvn spring-boot:run -q &
    PIDS+=($!)

    # 4. Frontend (Vite 热重载)
    log "启动 Frontend (http://localhost:5173)..."
    cd "$ROOT/frontend"
    npm run dev &
    PIDS+=($!)

    echo ""
    echo -e "${BLUE}============================================${NC}"
    echo -e "${GREEN}  开发模式启动完成${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""
    echo "  前端:       http://localhost:5173"
    echo "  Java API:   http://localhost:8080"
    echo "  Python API: http://localhost:8000/docs"
    echo ""
    echo "  按 Ctrl+C 停止所有服务"
    echo ""

    wait
}

# ---- Main ----
echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}          CBase 启动${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

case "$MODE" in
    --dev|-d|dev)
        start_dev
        ;;
    *)
        start_docker
        ;;
esac

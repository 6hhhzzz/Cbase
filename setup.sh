#!/usr/bin/env bash
# ============================================================
# CBase 开发环境初始化
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$SCRIPT_DIR"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'
log()  { echo -e "${GREEN}[setup]${NC} $1"; }
step() { echo -e "\n${BLUE}==> $1${NC}"; }
err()  { echo -e "${RED}[error]${NC} $1"; }

# ---- Python AI Service ----
setup_python() {
    step "1/3 Python AI Service"
    cd "$ROOT/ai-service"

    if ! command -v uv &>/dev/null; then
        err "uv 未安装。安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
        return 1
    fi

    log "安装依赖 (uv sync)..."
    uv sync
    log "Python 依赖完成"
}

# ---- Java Backend ----
setup_java() {
    step "2/3 Java Backend"
    cd "$ROOT/backend"

    if ! command -v mvn &>/dev/null; then
        err "Maven 未安装。安装: sudo apt install maven"
        return 1
    fi

    log "编译并下载依赖..."
    mvn compile -q
    log "Java 依赖完成"
}

# ---- Frontend ----
setup_frontend() {
    step "3/3 Frontend"
    cd "$ROOT/frontend"

    if ! command -v node &>/dev/null; then
        err "Node.js 未安装。安装: https://nodejs.org"
        return 1
    fi

    log "安装依赖 (npm install)..."
    npm install
    log "Frontend 依赖完成"
}

# ---- Main ----
main() {
    echo ""
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}       CBase — 开发环境初始化${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""

    local failed=0
    setup_python   || { err "Python 失败"; failed=1; }
    setup_java     || { err "Java 失败"; failed=1; }
    setup_frontend || { err "Frontend 失败"; failed=1; }

    echo ""
    if [ "$failed" -eq 0 ]; then
        echo -e "${GREEN}所有依赖安装完成!${NC}"
        echo ""
        echo "  下一步:"
        echo "    1. 复制环境变量: cp .env.example .env"
        echo "    2. 编辑 .env 填入 DASHSCOPE_API_KEY"
        echo "    3. 启动项目: ./start.sh"
    else
        err "部分依赖安装失败"
        exit 1
    fi
}

main "$@"

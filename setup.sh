#!/usr/bin/env bash
# ============================================================
# 企业知识助手 — 依赖环境安装脚本
# 所有依赖均为项目级隔离，不会污染全局环境:
#   Python : uv + .venv/          → 项目本地虚拟环境
#   Java   : .mvn/maven.config    → 项目本地 .m2/repository/
#   前端    : npm + node_modules/  → 项目本地目录
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

# ============================================================
# 1. Python AI Service (uv 管理)
# ============================================================
setup_python() {
    step "1/3 Python AI Service 依赖"

    if ! command -v uv &>/dev/null; then
        err "uv 未安装。安装方法: curl -LsSf https://astral.sh/uv/install.sh | sh"
        return 1
    fi

    cd "$ROOT/ai-service"

    log "同步依赖 (uv sync)..."
    uv sync

    log "验证关键依赖..."
    uv run python -c "
deps = ['fastapi','uvicorn','pydantic','openai','asyncpg','aio_pika','redis','yaml','jinja2']
ok = 0
for d in deps:
    try:
        __import__(d)
        ok += 1
    except:
        print(f'  MISS: {d}')
print(f'  {ok}/{len(deps)} 个依赖就绪')
"

    log "Python 依赖安装完成"
}

# ============================================================
# 2. Java Backend (Maven 管理)
# ============================================================
setup_java() {
    step "2/3 Java Backend 依赖 (项目级隔离: .m2/repository/)"

    if ! command -v mvn &>/dev/null; then
        err "Maven 未安装。安装方法: sudo apt install maven"
        return 1
    fi

    cd "$ROOT/backend"

    log "下载并编译 (mvn compile, 依赖写入 .m2/repository/)..."
    mvn compile -q

    log "Java 依赖安装完成"
}

# ============================================================
# 3. Frontend (npm 管理)
# ============================================================
setup_frontend() {
    step "3/3 Frontend 依赖"

    if ! command -v npm &>/dev/null; then
        err "npm 未安装。请安装 Node.js: https://nodejs.org"
        return 1
    fi

    cd "$ROOT/frontend"

    log "安装依赖 (npm install)..."
    npm install

    log "Frontend 依赖安装完成"
}

# ============================================================
# 主流程
# ============================================================
main() {
    echo ""
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}   企业知识助手 — 依赖环境安装${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""

    local failed=0

    setup_python || { err "Python 依赖安装失败"; failed=1; }
    setup_java   || { err "Java 依赖安装失败"; failed=1; }
    setup_frontend || { err "Frontend 依赖安装失败"; failed=1; }

    echo ""
    if [ "$failed" -eq 0 ]; then
        echo -e "${GREEN}============================================${NC}"
        echo -e "${GREEN}  所有依赖安装完成!${NC}"
        echo -e "${GREEN}============================================${NC}"
        echo ""
        echo "  下一步: 设置 DASHSCOPE_API_KEY 环境变量，然后运行 ./start.sh"
        echo ""
    else
        err "部分依赖安装失败，请检查上述错误信息"
        exit 1
    fi
}

main "$@"

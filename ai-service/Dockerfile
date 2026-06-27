# KES Python AI Service Dockerfile
FROM python:3.13-alpine
WORKDIR /app

# 系统依赖（pgvector/pg 客户端库、中文分词）
RUN apk add --no-cache gcc musl-dev libpq-dev

# 安装 uv 包管理器
RUN pip install uv --no-cache-dir

# 先复制依赖文件，利用 Docker 缓存
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen 2>/dev/null || uv sync

# 复制源码
COPY . .

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/v1/health')" 2>/dev/null || exit 1
CMD ["uv", "run", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]

#!/bin/bash
# Restart AI service with Langfuse tracing enabled
set -e
cd /home/zsl/projects/my_agent/ai-service

# Kill existing
pkill -f "uvicorn api.app" 2>/dev/null || true
sleep 2

# Load Langfuse keys from .env
export $(grep -E '^LANGFUSE_' /home/zsl/projects/my_agent/.env | xargs)

echo "Langfuse: ${LANGFUSE_SECRET_KEY:0:10}... @ $LANGFUSE_BASE_URL"

# Start with all required env vars
exec env \
  LANGFUSE_SECRET_KEY="$LANGFUSE_SECRET_KEY" \
  LANGFUSE_PUBLIC_KEY="$LANGFUSE_PUBLIC_KEY" \
  LANGFUSE_BASE_URL="$LANGFUSE_BASE_URL" \
  REDIS__HOST=localhost \
  PGVECTOR__HOST=localhost \
  RABBITMQ__HOST=localhost \
  MINIO__ENDPOINT=localhost:9000 \
  KES_JAVA_URL=http://localhost:8080 \
  DASHSCOPE_API_KEY="${DASHSCOPE_API_KEY:-}" \
  uv run uvicorn api.app:app --host 0.0.0.0 --port 8000

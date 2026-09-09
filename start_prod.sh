#!/usr/bin/env bash
# Linux 生产启动：多 worker。本地开发不要跑这个脚本，继续用单进程 uvicorn。
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

WORKERS="${WEB_CONCURRENCY:-4}"
HOST="${ZHISHI_BACKEND_HOST:-0.0.0.0}"
PORT="${ZHISHI_BACKEND_PORT:-8765}"
TIMEOUT="${GUNICORN_TIMEOUT:-180}"
CACHE_BACKEND="${CACHE_BACKEND:-memory}"
export WEB_CONCURRENCY="$WORKERS"

if [[ "$WORKERS" -gt 1 && "$CACHE_BACKEND" != "redis" ]]; then
  echo "多 worker 必须 CACHE_BACKEND=redis，否则验证码、限流、打断会在进程间分裂。" >&2
  exit 1
fi

echo "[生产] gunicorn uvicorn workers=${WORKERS} bind=${HOST}:${PORT} timeout=${TIMEOUT}s"
exec gunicorn server:app \
  -k uvicorn.workers.UvicornWorker \
  -w "$WORKERS" \
  --bind "${HOST}:${PORT}" \
  --timeout "$TIMEOUT" \
  --graceful-timeout 30 \
  --keep-alive 5

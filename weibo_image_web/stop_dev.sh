#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT_DIR/weibo_image_web/run/server.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "server not running (no pid file)"
  exit 0
fi

pid="$(cat "$PID_FILE")"

if ! kill -0 "$pid" 2>/dev/null; then
  echo "server not running (stale pid=$pid)"
  rm -f "$PID_FILE"
  exit 0
fi

kill "$pid"
# 等待进程退出，最多 5 秒
for _ in $(seq 1 10); do
  kill -0 "$pid" 2>/dev/null || break
  sleep 0.5
done

if kill -0 "$pid" 2>/dev/null; then
  echo "force killing pid=$pid"
  kill -9 "$pid" 2>/dev/null || true
fi

rm -f "$PID_FILE"
echo "server stopped: pid=$pid"
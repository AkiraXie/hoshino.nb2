#!/usr/bin/env bash
# x-image-web 开发启动脚本
# 启动 FastAPI 后端 (port 9997) 和 Vite 前端开发服务器 (port 3003)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PID_DIR="$SCRIPT_DIR/.pids"

mkdir -p "$PID_DIR"

# 检查是否已在运行
if [ -f "$PID_DIR/server.pid" ] && kill -0 "$(cat "$PID_DIR/server.pid")" 2>/dev/null; then
    echo "后端已在运行 (PID $(cat "$PID_DIR/server.pid"))"
else
    echo "启动后端 (port 9997)..."
    cd "$PROJECT_ROOT"
    nohup uv run python -m image_web x --port 9997 --reload \
        > "$PID_DIR/server.log" 2>&1 &
    echo $! > "$PID_DIR/server.pid"
    echo "后端已启动 (PID $!)"
fi

if [ -f "$PID_DIR/vite.pid" ] && kill -0 "$(cat "$PID_DIR/vite.pid")" 2>/dev/null; then
    echo "前端已在运行 (PID $(cat "$PID_DIR/vite.pid"))"
else
    echo "启动前端开发服务器 (port 3003)..."
    cd "$SCRIPT_DIR/frontend"
    nohup npm run dev -- --host 0.0.0.0 --port 3003 \
        > "$PID_DIR/vite.log" 2>&1 &
    echo $! > "$PID_DIR/vite.pid"
    echo "前端已启动 (PID $!)"
fi

echo ""
echo "前端: http://$(hostname | awk '{print $1}'):3003"
echo "后端: http://$(hostname | awk '{print $1}'):9997"
echo "停止: bash $SCRIPT_DIR/stop_dev.sh"

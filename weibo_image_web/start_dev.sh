#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WEB_DIR="$ROOT_DIR/weibo_image_web"
FRONTEND_DIR="$WEB_DIR/frontend"
LOG_DIR="$WEB_DIR/logs"
PID_DIR="$WEB_DIR/run"
PID_FILE="$PID_DIR/server.pid"
VITE_PID_FILE="$PID_DIR/vite.pid"

mkdir -p "$LOG_DIR" "$PID_DIR"

# ── 检查已有进程 ──────────────────────────────────────
if [ -f "$PID_FILE" ]; then
  old_pid="$(cat "$PID_FILE")"
  if kill -0 "$old_pid" 2>/dev/null; then
    echo "server already running: pid=$old_pid"
    read -rp "restart? [y/N] " answer
    case "$answer" in
      [yY]*)
        kill "$old_pid" 2>/dev/null || true
        for _ in $(seq 1 10); do
          kill -0 "$old_pid" 2>/dev/null || break
          sleep 0.5
        done
        if kill -0 "$old_pid" 2>/dev/null; then
          echo "force killing pid=$old_pid"
          kill -9 "$old_pid" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
        echo "old server stopped"
        ;;
      *)
        echo "keeping existing server"
        exit 0
        ;;
    esac
  else
    rm -f "$PID_FILE"
  fi
fi

# ── 构建前端 ──────────────────────────────────────────
echo "building frontend..."
(cd "$FRONTEND_DIR" && npm run build)
echo "frontend built"

# ── 启动 Vite dev server (HMR) ─────────────────────────
echo "starting vite dev server (port 3001)..."
nohup sh -c "cd '$FRONTEND_DIR' && npm run dev -- --host 0.0.0.0 --port 3001" \
  > "$LOG_DIR/vite.log" 2>&1 &
echo $! > "$VITE_PID_FILE"
echo "vite dev server started: pid=$(cat "$VITE_PID_FILE") port=3001"

# ── 启动后端 ─────────────────────────────────────────
nohup sh -c "cd '$ROOT_DIR' && uv run python weibo_image_web/server.py" \
  > "$LOG_DIR/server.log" 2>&1 &
echo $! > "$PID_FILE"
echo "server started: pid=$(cat "$PID_FILE") port=9998"
echo "log: $LOG_DIR/server.log"
echo ""
echo "  Frontend dev (HMR):  http://<server-ip>:3001"
echo "  Production:          http://<server-ip>:9998"

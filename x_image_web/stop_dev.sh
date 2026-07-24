#!/usr/bin/env bash
# 停止 x-image-web 开发服务器
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"

for name in server vite; do
    pidfile="$PID_DIR/$name.pid"
    if [ -f "$pidfile" ]; then
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            echo "已停止 $name (PID $pid)"
        else
            echo "$name 未在运行"
        fi
        rm -f "$pidfile"
    fi
done

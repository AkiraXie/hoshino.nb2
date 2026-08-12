#!/usr/bin/env bash
# x-image-web 开发启动脚本
# 启动 FastAPI 后端 (port 9997) 和 Vite 前端开发服务器 (port 3003)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PID_DIR="$SCRIPT_DIR/.pids"

mkdir -p "$PID_DIR"

# 返回 cmdline 本身或祖先链中包含关键字的、监听指定端口的进程 pid。
# 用于绕过失效 pid 文件：uv run/npm 包装进程退出后，实际服务进程可能仍占用端口。
port_pid() {
    local port="$1" keyword="$2" pid ppid
    for pid in $(ss -ltnp 2>/dev/null | awk -v p=":$port" '$4 ~ (p "$") { for (i = 1; i <= NF; i++) { if ($i ~ /pid=/) { gsub(/.*pid=/, "", $i); gsub(/,.*/, "", $i); print $i } } }'); do
        ppid="$pid"
        while [ -n "$ppid" ] && [ "$ppid" != "1" ]; do
            if [ -r "/proc/$ppid/cmdline" ] && tr '\0' ' ' < "/proc/$ppid/cmdline" 2>/dev/null | grep -q "$keyword"; then
                echo "$ppid"
                return 0
            fi
            ppid="$(awk '{print $4}' "/proc/$ppid/stat" 2>/dev/null || true)"
        done
    done
    return 1
}

# 服务是否已在运行：优先 pid 文件存活检查，其次按端口+关键字识别残留进程并刷新 pid 文件。
is_running() {
    local name="$1" keyword="$2" port="$3" pid
    pid="$(cat "$PID_DIR/$name.pid" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        return 0
    fi
    if pid="$(port_pid "$port" "$keyword")"; then
        echo "$pid" > "$PID_DIR/$name.pid"
        return 0
    fi
    return 1
}

# 检查是否已在运行
if is_running server image_web 9997; then
    echo "后端已在运行 (PID $(cat "$PID_DIR/server.pid"))"
else
    echo "启动后端 (port 9997)..."
    cd "$PROJECT_ROOT"
    nohup uv run python -m image_web x --port 9997 --reload \
        > "$PID_DIR/server.log" 2>&1 &
    echo $! > "$PID_DIR/server.pid"
    echo "后端已启动 (PID $!)"
fi

if is_running vite npm 3003; then
    echo "前端已在运行 (PID $(cat "$PID_DIR/vite.pid"))"
else
    echo "启动前端开发服务器 (port 3003)..."
    if [ ! -x "$SCRIPT_DIR/frontend/node_modules/.bin/vite" ]; then
        echo "前端依赖缺失，先执行 npm ci 安装..."
        npm --prefix "$SCRIPT_DIR/frontend" ci
    fi
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

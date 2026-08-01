#!/usr/bin/env bash
# 停止 x-image-web 开发服务器（后端 + Vite，含子进程树）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"

proc_cmd() {
  tr '\0' ' ' < "/proc/$1/cmdline" 2>/dev/null || true
}

# 打印 pid 及其所有后代进程（深度优先）
collect_tree() {
  local pid="$1"
  echo "$pid"
  local child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    collect_tree "$child"
  done
}

stop_one() {
  local name="$1" keyword="$2"
  local pidfile="$PID_DIR/$name.pid"
  if [ ! -f "$pidfile" ]; then
    echo "$name: 无 pid 文件，跳过"
    return 0
  fi
  local pid
  pid="$(cat "$pidfile")"
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "$name: 未在运行 (stale pid=$pid)"
    rm -f "$pidfile"
    return 0
  fi
  local cmd
  cmd="$(proc_cmd "$pid")"
  case "$cmd" in
    *"$keyword"*) ;;
    *)
      echo "$name: pid=$pid 不属于本项目 ($cmd)，跳过"
      rm -f "$pidfile"
      return 0
      ;;
  esac

  echo "$name: 停止进程树 (pid=$pid)..."
  local pids
  pids="$(collect_tree "$pid")"
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true

  local _
  for _ in $(seq 1 10); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.5
  done

  if kill -0 "$pid" 2>/dev/null; then
    echo "$name: 强制结束进程树 (pid=$pid)"
    pids="$(collect_tree "$pid")"
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi

  rm -f "$pidfile"
  echo "$name: 已停止"
}

stop_one server "image_web"
stop_one vite "npm"

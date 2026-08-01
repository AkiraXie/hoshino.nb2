#!/usr/bin/env bash
# Stop weibo-image-web dev servers (backend + Vite, including child process trees).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="$ROOT_DIR/weibo_image_web/run"

proc_cmd() {
  tr '\0' ' ' < "/proc/$1/cmdline" 2>/dev/null || true
}

# Print pid and all of its descendants (depth-first).
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
    echo "$name: no pid file, skipping"
    return 0
  fi
  local pid
  pid="$(cat "$pidfile")"
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "$name: not running (stale pid=$pid)"
    rm -f "$pidfile"
    return 0
  fi
  local cmd
  cmd="$(proc_cmd "$pid")"
  case "$cmd" in
    *"$keyword"*) ;;
    *)
      echo "$name: pid=$pid does not look like ours ($cmd), skipping"
      rm -f "$pidfile"
      return 0
      ;;
  esac

  echo "$name: stopping process tree (pid=$pid)..."
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
    echo "$name: force killing tree (pid=$pid)"
    pids="$(collect_tree "$pid")"
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi

  rm -f "$pidfile"
  echo "$name: stopped"
}

stop_one server "image_web"
stop_one vite "npm"

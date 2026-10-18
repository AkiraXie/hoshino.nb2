#!/usr/bin/env python3
"""Memray heap profile 辅助脚本。

用法示例::

    # 直接以 memray 为父进程启动 bot，记录到 data/profiles/
    uv run python scripts/heap_profile.py run --native

    # 生成可交互的 HTML 火焰图并在浏览器打开
    uv run python scripts/heap_profile.py flamegraph --open

    # 对正在运行的 bot 注入（需要 ptrace 权限）
    uv run python scripts/heap_profile.py attach --duration 60

    # 终端报告
    uv run python scripts/heap_profile.py summary
    uv run python scripts/heap_profile.py stats

Memray 没有 Web UI：``run --live`` 是终端 TUI，``flamegraph`` 生成的是
可在浏览器打开的静态/交互 HTML。``--temporal`` 才是“随时间变化”的图。
"""

from __future__ import annotations

import argparse
import subprocess  # noqa: S404 - 固定 argv、不经过 shell
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from mem_report import find_bot_pid

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "data" / "profiles"


def _memray() -> list[str]:
    return [sys.executable, "-m", "memray"]


def _run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)  # noqa: S603


def _capture_path(output: str | None, *, prefix: str = "hoshino") -> Path:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    if output:
        return Path(output).resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return (PROFILE_DIR / f"{prefix}-{stamp}.bin").resolve()


def _latest_capture() -> Path:
    captures = sorted(PROFILE_DIR.glob("*.bin"), key=lambda path: path.stat().st_mtime)
    if not captures:
        raise SystemExit(f"{PROFILE_DIR} 下没有 .bin，先运行 run 或 attach。")
    return captures[-1]


def _ptrace_scope() -> str:
    try:
        return Path("/proc/sys/kernel/yama/ptrace_scope").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def _add_capture_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("capture", nargs="?", help="memray 捕获文件；省略时取 data/profiles 最新")


def _run_command(args: argparse.Namespace) -> None:
    output = None if args.live or args.live_remote else _capture_path(args.output)
    command = [*_memray(), "run"]
    if args.live:
        command.append("--live")
    if args.live_remote:
        command.append("--live-remote")
    if args.live_port is not None:
        command += ["--live-port", str(args.live_port)]
    if args.native:
        command.append("--native")
    if args.trace_python_allocators:
        command.append("--trace-python-allocators")
    if output is not None:
        command += ["-o", str(output), "--force"]
    command.append(str(Path(args.script).resolve()))
    _run(command)
    if output is not None:
        print(f"\ncapture: {output}")


def _attach_command(args: argparse.Namespace) -> None:
    pid = args.pid or find_bot_pid()
    if pid is None:
        raise SystemExit("未找到 hoshino bot 进程，请用 --pid 指定。")
    scope = _ptrace_scope()
    if scope not in {"0", "unknown"}:
        print(
            f"警告：kernel.yama.ptrace_scope={scope}，普通用户 attach 会被拒绝。\n"
            "  临时放开：sudo sysctl -w kernel.yama.ptrace_scope=0\n"
            "  用完恢复：sudo sysctl -w kernel.yama.ptrace_scope=1",
            file=sys.stderr,
        )
    capture = _capture_path(args.output, prefix=f"attach-{pid}")
    command = [*_memray(), "attach", "-o", str(capture), "--force"]
    if args.duration is not None:
        command += ["--duration", str(args.duration)]
    if args.native:
        command.append("--native")
    if args.trace_python_allocators:
        command.append("--trace-python-allocators")
    command.append(str(pid))
    _run(command)
    print(f"\ncapture: {capture}")


def _resolve_capture(value: str | None) -> Path:
    return Path(value).resolve() if value else _latest_capture()


def _flamegraph_command(args: argparse.Namespace) -> None:
    capture = _resolve_capture(args.capture)
    output = (
        Path(args.output).resolve()
        if args.output
        else capture.with_name(f"{capture.stem}-flamegraph.html")
    )
    command = [*_memray(), "flamegraph", "-f", "-o", str(output)]
    if args.temporal:
        command.append("--temporal")
    if args.leaks:
        command.append("--leaks")
    if args.split_threads:
        command.append("--split-threads")
    if args.inverted:
        command.append("--inverted")
    if args.no_web:
        command.append("--no-web")
    command.append(str(capture))
    _run(command)
    print(f"flame graph: {output}")
    if args.open:
        webbrowser.open(output.as_uri())


def _reporter_command(args: argparse.Namespace, reporter: str) -> None:
    capture = _resolve_capture(args.capture)
    _run([*_memray(), reporter, str(capture)])


def _live_command(args: argparse.Namespace) -> None:
    _run([*_memray(), "live", str(args.port)])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="memray heap profile helper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="以 memray 为父进程启动 bot")
    run_parser.add_argument("--script", default=str(ROOT / "run.py"), help="默认 run.py")
    run_parser.add_argument("-o", "--output", help="捕获文件；默认 data/profiles/")
    run_parser.add_argument("--native", action="store_true", help="同时跟踪 C/C++ 栈")
    run_parser.add_argument(
        "--trace-python-allocators",
        action="store_true",
        help="跟踪 pymalloc 分配（开销更大）",
    )
    live_group = run_parser.add_mutually_exclusive_group()
    live_group.add_argument("--live", action="store_true", help="启动后直接接 TUI")
    live_group.add_argument("--live-remote", action="store_true", help="等待另一个终端连 TUI")
    run_parser.add_argument("--live-port", type=int, help="live 端口")
    run_parser.set_defaults(func=_run_command)

    attach_parser = subparsers.add_parser("attach", help="注入正在运行的 bot")
    attach_parser.add_argument("--pid", type=int, help="目标 PID；默认自动查找")
    attach_parser.add_argument("-o", "--output", help="捕获文件")
    attach_parser.add_argument("--duration", type=int, default=60, help="记录秒数，默认 60")
    attach_parser.add_argument("--native", action="store_true")
    attach_parser.add_argument("--trace-python-allocators", action="store_true")
    attach_parser.set_defaults(func=_attach_command)

    flamegraph_parser = subparsers.add_parser("flamegraph", help="生成 HTML 火焰图")
    _add_capture_argument(flamegraph_parser)
    flamegraph_parser.add_argument("-o", "--output", help="HTML 输出路径")
    flamegraph_parser.add_argument("--temporal", action="store_true", help="随时间变化的火焰图")
    flamegraph_parser.add_argument("--leaks", action="store_true", help="只显示未释放分配")
    flamegraph_parser.add_argument("--split-threads", action="store_true", help="按线程拆分")
    flamegraph_parser.add_argument("--inverted", action="store_true", help="反向火焰图")
    flamegraph_parser.add_argument("--no-web", action="store_true", help="使用本地静态资源")
    flamegraph_parser.add_argument("--open", action="store_true", help="生成后用浏览器打开")
    flamegraph_parser.set_defaults(func=_flamegraph_command)

    for reporter, help_text in (
        ("summary", "终端汇总：峰值时各函数 own/total 内存"),
        ("stats", "终端统计：分配/释放随时间的变化"),
    ):
        reporter_parser = subparsers.add_parser(reporter, help=help_text)
        _add_capture_argument(reporter_parser)
        reporter_parser.set_defaults(func=lambda args, name=reporter: _reporter_command(args, name))

    live_parser = subparsers.add_parser("live", help="连接 run --live-remote 的 TUI 客户端")
    live_parser.add_argument("port", type=int)
    live_parser.set_defaults(func=_live_command)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        return 130
    except subprocess.CalledProcessError as exc:
        return exc.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

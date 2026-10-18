#!/usr/bin/env python3
"""只读打印运行中进程的内存构成。

默认自动查找 hoshino bot，也可以 ``--pid`` 指定。数据来自
``/proc/<pid>/status``、``smaps``、``smaps_rollup`` 和 psutil。

重点是把 RSS 拆成：

* ``[heap]``：主分配器堆；
* 64MB 对齐的 anon 映射：glibc 线程 arena（通常包含已 free 但未还给内核的页）；
* 其他 anon / 文件映射 / THP。

脚本只读，不会对目标进程执行 ``malloc_trim``；arena 里的空闲页只能由进程
自己（或注入代码）释放。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import psutil

_ARENA_SIZE = 64 * 1024 * 1024
_ARENA_MIN_KB = 32 * 1024
_HEADER_RE = re.compile(r"^([0-9a-f]+)-([0-9a-f]+)\s")


@dataclass(frozen=True, slots=True)
class MemoryReport:
    pid: int
    cmdline: str
    rss_kb: int
    uss_bytes: int
    pss_bytes: int
    vm_hwm_kb: int
    heap_kb: int
    arena_count: int
    arena_kb: int
    other_anon_kb: int
    file_kb: int
    anon_huge_kb: int


@dataclass(frozen=True, slots=True)
class _Mappings:
    heap_kb: int
    arena_count: int
    arena_kb: int
    other_anon_kb: int
    file_kb: int


def _read_status(pid: int) -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        lines = Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        key, _, rest = line.partition(":")
        if key in {"VmRSS", "VmHWM", "VmSize"}:
            values[key] = int(rest.split()[0])
    return values


def _read_anon_huge_kb(pid: int) -> int:
    try:
        lines = Path(f"/proc/{pid}/smaps_rollup").read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    for line in lines:
        if line.startswith("AnonHugePages:"):
            return int(line.split()[1])
    return 0


def _read_mappings(pid: int) -> _Mappings:
    try:
        lines = Path(f"/proc/{pid}/smaps").read_text(encoding="utf-8").splitlines()
    except OSError:
        return _Mappings(0, 0, 0, 0, 0)

    heap_kb = 0
    arena_count = 0
    arena_kb = 0
    other_anon_kb = 0
    file_kb = 0
    index = 0
    while index < len(lines):
        header = _HEADER_RE.match(lines[index])
        if header is None:
            index += 1
            continue

        start = int(header.group(1), 16)
        end = int(header.group(2), 16)
        size_kb = (end - start) // 1024
        parts = lines[index].split(maxsplit=5)
        path = parts[5].strip() if len(parts) > 5 else ""
        rss_kb = 0
        index += 1
        while index < len(lines) and _HEADER_RE.match(lines[index]) is None:
            if lines[index].startswith("Rss:"):
                rss_kb = int(lines[index].split()[1])
            index += 1

        if path == "[heap]":
            heap_kb += rss_kb
        elif path and not path.startswith("["):
            file_kb += rss_kb
        elif not path and size_kb >= _ARENA_MIN_KB and start % _ARENA_SIZE == 0:
            arena_count += 1
            arena_kb += rss_kb
        else:
            other_anon_kb += rss_kb

    return _Mappings(heap_kb, arena_count, arena_kb, other_anon_kb, file_kb)


def _read_cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    text = " ".join(part for part in raw.decode("utf-8", "replace").split("\0") if part)
    return text if len(text) <= 300 else f"{text[:297]}..."


def find_bot_pid() -> int | None:
    for proc in psutil.process_iter(["pid", "cmdline"]):
        if proc.pid == os.getpid():
            continue
        try:
            cmdline = proc.info.get("cmdline") or []
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        joined = " ".join(cmdline)
        entrypoints = {Path(part).name for part in cmdline}
        if "hoshino" in entrypoints and ".venv" in joined:
            return proc.pid
        if "run.py" in entrypoints and "hoshino" in joined:
            return proc.pid
    return None


def _mib(kb: int) -> str:
    return f"{kb / 1024:.1f} MiB"


def _gib_from_bytes(value: int) -> str:
    return f"{value / 1024**3:.2f} GiB"


def build_report(pid: int) -> MemoryReport:
    status = _read_status(pid)
    mappings = _read_mappings(pid)
    uss_bytes = 0
    pss_bytes = 0
    try:
        mem = psutil.Process(pid).memory_full_info()
    except psutil.Error:
        mem = None
    if mem is not None:
        uss_bytes = mem.uss
        pss_bytes = mem.pss
    return MemoryReport(
        pid=pid,
        cmdline=_read_cmdline(pid),
        rss_kb=status.get("VmRSS", 0),
        uss_bytes=uss_bytes,
        pss_bytes=pss_bytes,
        vm_hwm_kb=status.get("VmHWM", 0),
        heap_kb=mappings.heap_kb,
        arena_count=mappings.arena_count,
        arena_kb=mappings.arena_kb,
        other_anon_kb=mappings.other_anon_kb,
        file_kb=mappings.file_kb,
        anon_huge_kb=_read_anon_huge_kb(pid),
    )


def _format(report: MemoryReport) -> str:
    return "\n".join(
        [
            f"目标 PID {report.pid}: {report.cmdline or '<unknown>'}",
            f"  RSS {_mib(report.rss_kb)} | USS {_gib_from_bytes(report.uss_bytes)}"
            f" | PSS {_gib_from_bytes(report.pss_bytes)} | VmHWM {_mib(report.vm_hwm_kb)}",
            f"  [heap] {_mib(report.heap_kb)}",
            f"  64MB 对齐 anon（glibc 线程 arena）: {report.arena_count} 个"
            f" / {_mib(report.arena_kb)}",
            f"  other anon {_mib(report.other_anon_kb)} | file-backed {_mib(report.file_kb)}",
            f"  THP {_mib(report.anon_huge_kb)}",
            "  只读报告；arena 中的空闲页需要进程内 malloc_trim，脚本无法远程释放。",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, help="目标 PID；省略时自动查找 hoshino bot")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    pid = args.pid or find_bot_pid()
    if pid is None:
        print("未找到 hoshino bot 进程，请用 --pid 指定。", file=sys.stderr)
        return 2

    report = build_report(pid)
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        print(_format(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

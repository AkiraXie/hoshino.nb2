"""进程内存构成诊断。

回答“USS 1GB 到底是谁占的”需要同时看三层：

* 进程视角：``/proc/self/status`` 的 RSS / 峰值，psutil 的 USS；
* 分配器视角：glibc ``mallinfo2`` 的 in-use / free，以及 ``smaps`` 里
  64MB 对齐的线程 arena——这部分是 free 但没还给内核的内存；
* Python 视角：GC 对象计数与（启动时启用 tracemalloc 后的）分配点。

只做诊断，不参与业务逻辑。任何读取失败都降级为“不可用”，不抛异常。
"""

from __future__ import annotations

import ctypes
import gc
import re
import tracemalloc
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import psutil

_PROC = Path("/proc/self")
_ARENA_SIZE = 64 * 1024 * 1024
_ARENA_MIN_KB = 32 * 1024
_HEADER_RE = re.compile(r"^([0-9a-f]+)-([0-9a-f]+)\s")


class _MallInfo2(ctypes.Structure):
    """glibc 2.33+ 的 ``struct mallinfo2``（10 个 size_t 字段）。"""

    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("arena", ctypes.c_size_t),
        ("ordblks", ctypes.c_size_t),
        ("smblks", ctypes.c_size_t),
        ("hblks", ctypes.c_size_t),
        ("hblkhd", ctypes.c_size_t),
        ("usmblks", ctypes.c_size_t),
        ("fsmblks", ctypes.c_size_t),
        ("uordblks", ctypes.c_size_t),
        ("fordblks", ctypes.c_size_t),
        ("keepcost", ctypes.c_size_t),
    ]


try:
    _LIBC = ctypes.CDLL(None)
except OSError:  # pragma: no cover - 非 Linux 平台
    _LIBC = None

_MALLINFO2 = getattr(_LIBC, "mallinfo2", None) if _LIBC is not None else None
_MALLOC_TRIM = getattr(_LIBC, "malloc_trim", None) if _LIBC is not None else None
if _MALLINFO2 is not None:
    _MALLINFO2.restype = _MallInfo2
if _MALLOC_TRIM is not None:
    _MALLOC_TRIM.argtypes = [ctypes.c_size_t]
    _MALLOC_TRIM.restype = ctypes.c_int


@dataclass(frozen=True, slots=True)
class _MappingStats:
    heap_kb: int
    arena_count: int
    arena_kb: int


def _read_status() -> dict[str, int]:
    """读取 VmRSS / VmHWM / VmSize（单位 kB）。"""
    values: dict[str, int] = {}
    try:
        lines = (_PROC / "status").read_text().splitlines()
    except OSError:
        return values
    for line in lines:
        key, _, rest = line.partition(":")
        if key in {"VmRSS", "VmHWM", "VmSize"}:
            values[key] = int(rest.split()[0])
    return values


def _read_anon_huge_kb() -> int:
    """读取 THP 折叠的匿名页大小，失败返回 0。"""
    try:
        lines = (_PROC / "smaps_rollup").read_text().splitlines()
    except OSError:
        return 0
    for line in lines:
        if line.startswith("AnonHugePages:"):
            return int(line.split()[1])
    return 0


def _mapping_stats() -> _MappingStats:
    """统计 ``[heap]`` 与 64MB 对齐的线程 arena（glibc ``new_heap``）。

    arena 被 ``heap_trim`` 收缩后 VMA 不再等于 64MB，但起始地址仍保持对齐，
    因此按“对齐 + 至少 32MB”识别，避免只统计完整 64MB 而漏掉已被部分归还的。
    """
    try:
        lines = (_PROC / "smaps").read_text().splitlines()
    except OSError:
        return _MappingStats(0, 0, 0)

    heap_kb = 0
    arena_count = 0
    arena_kb = 0
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
        elif not path and size_kb >= _ARENA_MIN_KB and start % _ARENA_SIZE == 0:
            arena_count += 1
            arena_kb += rss_kb
    return _MappingStats(heap_kb, arena_count, arena_kb)


def _top_object_types(limit: int = 12) -> list[tuple[str, int]]:
    """GC 跟踪对象的类型计数（str/int 等不可跟踪对象不在其中）。"""
    objects = gc.get_objects()
    try:
        return Counter(type(obj).__name__ for obj in objects).most_common(limit)
    finally:
        del objects


def _tracemalloc_top(limit: int = 6) -> list[str]:
    """tracemalloc 当前分配点 top；未启用时返回空列表。"""
    if not tracemalloc.is_tracing():
        return []
    snapshot = tracemalloc.take_snapshot()
    lines: list[str] = []
    for stat in snapshot.statistics("lineno")[:limit]:
        frame = stat.traceback[0] if stat.traceback else None
        location = f"{Path(frame.filename).name}:{frame.lineno}" if frame else "?"
        lines.append(f"{stat.size / 2**20:.1f}MB {stat.count} blocks {location}")
    return lines


def build_memory_report(*, trim: bool = True) -> str:
    """生成内存构成报告；``trim`` 为真时顺带 ``gc.collect`` + ``malloc_trim(0)``。"""
    status = _read_status()
    rss_kb = status.get("VmRSS", 0)
    hwm_kb = status.get("VmHWM", 0)
    try:
        uss_mb = psutil.Process().memory_full_info().uss / 2**20
    except psutil.Error:
        uss_mb = float("nan")

    mall = _MALLINFO2() if _MALLINFO2 is not None else None
    mappings = _mapping_stats()
    huge_kb = _read_anon_huge_kb()

    lines = [
        "内存构成（本进程）：",
        f"  USS {uss_mb:.1f} MB | RSS {rss_kb / 1024:.1f} MB | 峰值 {hwm_kb / 1024:.1f} MB",
    ]
    if mall is not None:
        lines.append(
            f"  glibc in-use {mall.uordblks / 2**20:.1f} MB | free {mall.fordblks / 2**20:.1f} MB"
            f" | arena {mall.arena / 2**20:.1f} MB | mmap {mall.hblkhd / 2**20:.1f} MB"
        )
    else:
        lines.append("  glibc 统计不可用（非 glibc 或 mallinfo2 缺失）")
    lines.append(
        f"  [heap] {mappings.heap_kb / 1024:.1f} MB | 64MB arena {mappings.arena_count} 个"
        f" / {mappings.arena_kb / 1024:.1f} MB | THP {huge_kb / 1024:.1f} MB"
    )

    if trim:
        gc.collect()
        released = _MALLOC_TRIM(0) if _MALLOC_TRIM is not None else None
        rss_after_kb = _read_status().get("VmRSS", rss_kb)
        if released is None:
            lines.append("  malloc_trim：不可用")
        else:
            lines.append(
                f"  gc + malloc_trim：RSS {rss_kb / 1024:.1f} -> {rss_after_kb / 1024:.1f} MB"
                f"（释放 {(rss_kb - rss_after_kb) / 1024:.1f} MB）"
            )

    types = _top_object_types()
    lines.append("  GC 对象 top：" + "，".join(f"{name} {count:,}" for name, count in types))
    traced = _tracemalloc_top()
    if traced:
        current, peak = tracemalloc.get_traced_memory()
        lines.append(f"  tracemalloc：当前 {current / 2**20:.1f} MB，峰值 {peak / 2**20:.1f} MB")
        lines.extend(f"    {line}" for line in traced)
    else:
        lines.append("  tracemalloc 未启用：用 PYTHONTRACEMALLOC=25 重启后可见分配点")
    return "\n".join(lines)


__all__ = ["build_memory_report"]

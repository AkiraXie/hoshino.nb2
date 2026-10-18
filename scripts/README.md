# scripts

运行时排障脚本，不参与 bot 启动和业务逻辑。内存构成分析从 bot 内置命令
`#mem` 移到了这里；bot 的 `#stat` 只保留 USS/CPU/协程数等总量。

## 为什么选 memray

| 工具 | 能做什么 | 不适合什么 |
| --- | --- | --- |
| **memray**（本目录采用） | Python + C/C++/Rust 分配栈、峰值/泄漏/临时分配、HTML 火焰图、TUI live、attach | CPU 时间线；没有 Web UI |
| pyroscope | 持续 CPU profiling + Grafana Web UI | Python 堆分配栈不是它的强项，需要额外服务端 |
| viztracer | 时间线 trace（函数调用/CPU） | 不回答“谁占了堆内存” |
| tracemalloc | 标准库、轻量、按行统计 | 只能看 Python 分配，看不到 native，需启动时开启 |

memray 已加入 `pyproject.toml` 的 dev 依赖。

## Memray 的“可视化”到底有什么

- **没有 Web UI**。`run --live` 是终端 TUI；`--live-remote` 也是给另一个终端
  的 TUI 客户端连。
- `flamegraph` 生成 **可在浏览器打开的交互式 HTML**（不是服务端 WebUI）。
  默认火焰图展示“堆峰值时刻”的分配栈。
- `flamegraph --temporal` 生成 **随时间变化** 的火焰图：页面顶部是内存曲线，
  下面两个滑块选择时间窗口。这是最接近“heap 和 profile 关系图”的视图。
- `flamegraph --leaks`：只显示未释放的分配（看泄漏）。
- `flamegraph --split-threads`：按线程拆分；`--inverted`：反向火焰图，适合看
  “某函数总共被哪些调用方分配”。
- `summary` / `stats` / `tree`：终端里的峰值汇总、时间统计、调用树。
- memray 只做 **heap allocation**，不做 CPU profile；想看 CPU 用 py-spy 等工具。

## 用法

### 1. 内存构成（只读）

```bash
uv run python scripts/mem_report.py            # 自动找 hoshino bot
uv run python scripts/mem_report.py --pid 1234
uv run python scripts/mem_report.py --json
```

输出 RSS / USS / PSS / VmHWM、`[heap]`、64MB 对齐的 glibc 线程 arena、
其他 anon、文件映射、THP。脚本只读，**不会**对目标进程执行 `malloc_trim`。
arena 里的空闲页只能在进程内释放。

### 2. 记录 heap profile

```bash
# 以 memray 为父进程启动 bot；记录到 data/profiles/
uv run python scripts/heap_profile.py run
uv run python scripts/heap_profile.py run --native          # 带 C/C++ 栈
uv run python scripts/heap_profile.py run --live            # 直接开 TUI
uv run python scripts/heap_profile.py run --live-remote --live-port 12345
# 另一个终端：
uv run python scripts/heap_profile.py live 12345
```

`run` 会一直记录到 bot 退出；文件可能很大，排障时建议记录一段时间后停掉。

### 3. 对正在运行的 bot 注入

```bash
uv run python scripts/heap_profile.py attach --duration 60
```

`attach` 只能看到 **注入之后** 的分配，不能追溯已经存在的 1.4GB。当前机器
`kernel.yama.ptrace_scope=1`，普通用户 attach 会被拒绝；需要临时：

```bash
sudo sysctl -w kernel.yama.ptrace_scope=0
# 用完恢复
sudo sysctl -w kernel.yama.ptrace_scope=1
```

### 4. 看报告

```bash
# 最新捕获文件
uv run python scripts/heap_profile.py flamegraph --open
uv run python scripts/heap_profile.py flamegraph --temporal --open
uv run python scripts/heap_profile.py flamegraph --leaks --split-threads
uv run python scripts/heap_profile.py summary
uv run python scripts/heap_profile.py stats
```

HTML 默认写到 `data/profiles/<capture>-flamegraph.html`。注意 HTML 里可能内嵌
源码行；分享前用 `memray flamegraph --confidential-files=all` 或不要外发。

`memray tree` 是 Textual TUI，不适合重定向到文件；需要调用树时直接在终端跑：

```bash
uv run memray tree data/profiles/<capture>.bin
```

## 看泄漏时的注意点

- Python 的 pymalloc 释放对象后不一定把内存还给内核，`--leaks` 可能把正常的
  分配器保留算成“泄漏”。要看真实泄漏，配合：

  ```bash
  PYTHONMALLOC=malloc uv run python scripts/heap_profile.py run --leaks
  ```

- RSS 高不一定是对象泄漏。先看 `mem_report.py` 的 arena/THP 占比，再用
  `flamegraph --temporal` 看峰值时刻的分配栈。
- 想压住 glibc 线程 arena 膨胀，启动时加 `MALLOC_ARENA_MAX=2`（或 4）。

## 参考

- [Memray 文档](https://bloomberg.github.io/memray/)
- [Live Reporting（终端 TUI）](https://bloomberg.github.io/memray/live.html)
- [Flame Graph Reporter（含 temporal / leaks / split-threads）](https://bloomberg.github.io/memray/flamegraph.html)
- [Attaching to a running process](https://bloomberg.github.io/memray/attach.html)

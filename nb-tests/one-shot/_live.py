"""one-shot live 探针共享设施：fixture 读取、deps/agent 构建、观测打印。

hoshino/nonebot 的 import 一律放在各 helper 函数内：pytest 收集期测试模块先于
nonebug 的 nonebot 初始化被 import，顶层 import hoshino 会因 core.schedule 的
``nonebot.require``（apscheduler）失败。各探针测试因此在测试函数内延迟 import
（该目录对 ruff PLC0415/PLC2701 豁免，见 pyproject）。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    """读取 ``fixtures/<name>.json``（UTF-8）。"""
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def resolve_image(name: str) -> Path:
    """fixture 里的图片文件名 → one-shot 目录下的实际路径。"""
    path = Path(__file__).parent / name
    if not path.is_file():
        raise SystemExit(f"探针图片不存在：{path}")
    return path


def load_config() -> Any:
    """真实 AI 配置（挂载字段 AI_*，读自 .env.prod）。"""
    from hoshino.ai.base import get_config

    return get_config()


def build_deps(config: Any, provider_id: str, model: str, scope_key: str) -> Any:
    """与 construct_chat_deps 同构的探针 deps（bot/event 为 None，无真实事件）。"""
    from nonebot_plugin_alconna.uniseg import Target

    from hoshino.ai.deps import AgentDeps, PermissionSnapshot, Telemetry

    return AgentDeps(
        surface="chat",
        scope_key=scope_key,
        target=Target(id="0", private=True, self_id="10000", adapter="milky"),
        config=config,
        permissions=PermissionSnapshot(),
        bot=None,
        event=None,
        telemetry=Telemetry(provider_id=provider_id, scope_key=scope_key, model=model),
    )


def build_agent(config: Any, provider_id: str, record: Any, model: str) -> Any:
    """与 chat 同构的 agent 构建（含生效代理与工具重试预算）。"""
    from hoshino.ai import provider, providers

    return providers.build_agent(
        provider_id,
        record,
        model,
        proxy=provider.resolve_effective_proxy(record, config.proxy),
        tool_max_retries=config.tool_max_retries,
    )


def make_probe_logger() -> Any:
    """实时打印每个图节点（与 chat.py stream_logger 同构）。

    节点事件在开始执行前触发，delta 是刚执行完的上一节点耗时。
    """
    from hoshino.ai import runner

    prev = time.monotonic()

    def on_event(ev: Any) -> None:
        nonlocal prev
        now = time.monotonic()
        delta = now - prev
        prev = now
        desc = runner.describe_node(ev.node, ev.ctx)
        if desc is None:
            return
        suffix = f" · 上一步 {delta:.1f}s" if delta >= 0.05 else ""
        print(f"  [{time.strftime('%H:%M:%S')}] {desc}{suffix}", flush=True)

    return on_event


def print_step_details(run_log: Any) -> None:
    """打印每个 model request 的上下文规模与 duration/delta/elapsed。"""
    for detail in run_log.step_details:
        print(
            f"  step {detail.step}: msgs={detail.msgs} parts={detail.parts} "
            f"text_chars={detail.text_chars:,} tool_ret_chars={detail.tool_return_chars:,} "
            f"duration={detail.duration:.1f}s delta={detail.delta:.1f}s elapsed={detail.elapsed:.1f}s"
        )


def enable_debug_logging() -> None:
    """打开 DEBUG 日志：runner 逐步观测（AI step N ...）与 AI payload dump 可见。"""
    from hoshino.core.config import config as hsn
    from hoshino.core.log import configure

    hsn.debug = True
    configure()


def write_report(name: str, lines: list[str]) -> Path:
    """把探针报告写入 agent-plan-report/（gitignored），返回路径。"""
    path = Path("agent-plan-report") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path

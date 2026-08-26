"""AI 模块配置数据模型与 hsnconfig 挂载机制。

``AIConfig`` 仍在本模块定义（不在 ``hoshino/core/config.py`` 写任何 AI 字段）；
通过 ``mount_into_hsnconfig`` 把字段动态挂载到 ``HoshinoConfig`` 上（字段名
``ai_<name>``、env 名 ``AI_<NAME>``，读自 ``.env.prod`` / ``.env.prod.example``），
挂载发生在 HoshinoConfig 实例化之前，因此 env 值正常生效。provider 数据存
SQLite（``hoshino/ai/store.py`` 的 ``ai_providers`` 等表），本模型只保留非
provider 的全局配置与默认 provider 指针（``default``，运行时可用
``ai provider default`` 覆盖到 DB）。
"""

import os
from collections.abc import Sequence
from dataclasses import dataclass, fields
from typing import Literal

from .prompts import DEFAULT_SYSTEM_PROMPT

ThemeKind = Literal["light", "dark"]


@dataclass(frozen=True, slots=True)
class AIConfig:
    default: str = ""
    # 默认人设取 prompts.DEFAULT_SYSTEM_PROMPT。
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_history_messages: int = 64
    render_timeout_seconds: float = 30.0
    render_theme: ThemeKind = "light"
    # Markdown 渲染主字体（CSS font-family 首项）。默认 Inter（拉丁），中文按字体栈
    # 回退到系统 CJK 字体；可配置为任意已安装字体的 family 名。
    render_font: str = "Inter"
    # computer 工具的工作根目录；空字符串 → data_dir / "ai_computer"。
    # 只作为冻结 workspace 的 cwd，不是完整 sandbox（见 computer/runtime.py）。
    computer_workdir: str = ""
    # 代理走显式配置而非环境变量：与 info-x 一致，避免读入无法解析的
    # ``ALL_PROXY=socks://...`` 环境变量导致 httpx 崩溃。支持 http(s):// 与
    # socks://（后者归一化为 socks5://）。
    proxy: str | None = None
    # 工具抓取请求（web_fetch/browser_use/image_view/web_search）是否走代理：
    # 默认 False 直连（既有解析类请求直连策略）；置 True 后与 LLM 请求一致，
    # 优先全局 OUTSIDE_PROXY、未配置回退本配置 proxy。
    tool_use_proxy: bool = False
    # Task 默认审批模式：auto（high-risk 工具 deferred approval）/
    # always（全部工具先审批）/ never（不审批）。创建 Task 时冻结进 capability snapshot。
    task_approval_mode: str = "auto"
    # 聊天执行护栏（持久化不替代超时）：
    # run 墙钟上限；run 内模型请求次数上限（UsageLimits.request_limit）。
    chat_run_timeout_seconds: float = 180.0
    chat_max_requests: int = 12
    # 上下文内存缓存（LRU）：驻留 scope 数与每 scope 驻留对话数，超限先 flush 再逐出。
    chat_memory_scopes: int = 256
    chat_memory_conversations: int = 4
    # 工具调用失败重试预算（pydantic-ai 默认 1）。web_fetch 等抓取工具偶发失败
    # 会触发 "exceeded max retries" 直接杀掉整轮 run，调高以容错。
    tool_max_retries: int = 3
    # web_fetch 抓取网页时的 HTTPS 证书校验开关。默认校验；个别证书异常的
    # 站点/代理环境可改为 False 关闭校验以恢复可用。
    web_fetch_verify_ssl: bool = True
    # web_fetch 超长正文的默认上限与是否生成轻量摘要。
    web_fetch_max_chars: int = 8_000
    web_fetch_summarize: bool = True
    # 单次 run 的软压缩：估算 token 阈值（约 200K window 的 60%）、触发比例、
    # 保留窗口、本地摘要模型（空值使用当前模型）。
    # compaction_threshold_chars 保留作兼容别名（按估算 token 计数）。
    compaction_threshold_chars: int = 120_000
    compaction_threshold_ratio: float = 0.82
    compaction_window_size: int = 4
    compaction_model: str = ""
    # 压缩优先尝试 provider 原生远程压缩（如 OpenAI Responses compact）；
    # 端点不支持/失败时回退本地 LLM 摘要压缩。
    compaction_remote_first: bool = True
    # 工具返回内容超过该估算字符数时溢出落盘（run 内替换为短预览+路径提示，
    # 模型需要细节可读文件）。激进策略：超过 1K 必落盘，避免大内容占用对话 token。
    tool_result_spill_max_chars: int = 1_000
    tool_result_spill_dir: str = ""
    # 模型请求重试的指数退避参数（秒）；429/5xx/网络错误重试前等待。
    retry_backoff_base: float = 0.5
    retry_backoff_max: float = 4.0
    # 启用时优先走 pydantic-ai 内部流式请求；部分 OpenAI 兼容端点不支持，默认关闭。
    stream_requests: bool = False
    # Markdown 渲染清晰度：Playwright 截图 device scale factor（2.0 = 2x）。
    render_device_scale: float = 2.0
    # 渲染时是否启用彩色 emoji 字体（部分系统无 emoji 字体时关掉可避免方框）。
    render_emoji: bool = True
    # 话题切换检测：当新提问与历史话题无关时截断旧历史，避免模型强行关联。
    # 基于关键词 Jaccard 相似度检测；threshold 越低越敏感（更容易判定为话题切换）。
    topic_shift_detection: bool = True
    topic_shift_threshold: float = 0.08
    topic_shift_window: int = 5
    # 压缩摘要是否标注话题边界（让模型知道历史中有多个话题）。
    compaction_topic_aware: bool = True


def mask_key(key: str) -> str:
    """脱敏 key：只保留前 4 位与后 4 位，中间以星号代替。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"


def mask_url(url: str) -> str:
    """脱敏 url：去掉 query/参数中可能的敏感信息，仅保留 scheme+host+path。"""
    if not url:
        return ""
    cleaned = url.split("?")[0].split("#")[0]
    if len(cleaned) <= 48:
        return cleaned
    return f"{cleaned[:44]}...{cleaned[-4:]}"


# ------------------------------------------------------------ hsnconfig 挂载
#
# 字段定义留在本模块（core/config 不写 AI 字段）：通过 ``mount_into_hsnconfig``
# 把 ``config.ai`` 挂为惰性属性——首次访问时从 ``AI_*`` 环境变量与
# ``.env.prod`` 构建 AIConfig（环境变量优先于文件）。不做 pydantic 动态字段：
# model_rebuild 后的动态字段对 pydantic-settings 的 env 读取不可靠。

AI_ENV_PREFIX = "AI_"
# AIConfig 字段 → env 名（default 用语义化命名）
_HSN_ENV_NAMES = {"default": "AI_DEFAULT_PROVIDER"}


def _env_name(field_name: str) -> str:
    return _HSN_ENV_NAMES.get(field_name, f"{AI_ENV_PREFIX}{field_name.upper()}")


def _coerce(field_type, raw: str):
    if field_type is bool:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if field_type is int:
        return int(raw)
    if field_type is float:
        return float(raw)
    return raw  # str / str | None / Literal


def _iter_env_file(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                yield key.strip(), value.strip().strip('"').strip("'")
    except OSError:
        return


def load_ai_config_from_env(
    env: dict[str, str] | None = None,
    env_file: str = ".env.prod",
) -> AIConfig:
    """从 AI_* 环境变量 + .env.prod 构建 AIConfig（env 变量优先于文件）。

    未配置的字段用 AIConfig 代码默认值；空值视为未设置。
    """
    values: dict[str, str] = {
        key: value for key, value in _iter_env_file(env_file) if key.startswith(AI_ENV_PREFIX)
    }
    source = env if env is not None else os.environ
    values.update({key: value for key, value in source.items() if key.startswith(AI_ENV_PREFIX)})

    kwargs: dict = {}
    for field in fields(AIConfig):
        raw = values.get(_env_name(field.name))
        if raw is None or raw == "":
            continue
        kwargs[field.name] = _coerce(field.type, raw)
    return AIConfig(**kwargs)


def mount_into_hsnconfig(hsn_cls) -> None:
    """把 ``ai`` 属性挂到 HoshinoConfig（惰性：``config.ai`` 从 env 构建 AIConfig）。

    幂等；不修改 pydantic 字段 schema，避免动态字段的 env 读取问题。
    """
    if "ai" in hsn_cls.__dict__:
        return
    hsn_cls.ai = property(lambda self: load_ai_config_from_env())


def write_ai_config_env(
    env_file: str,
    *,
    updates: dict[str, str] | None = None,
    removes: Sequence[str] | None = None,
) -> None:
    """把 ``AI_*`` 配置项写入 env 文件（供 ``ai config`` 在线修改写盘）。

    ``updates``：字段名 → 字符串值，写 ``AI_<NAME>=<value>`` 行（已有行就地替换
    值，否则追加到文件末尾）；``removes``：删除对应行（恢复代码默认）。文件不存在
    时新建；其余行（注释/其它配置）原样保留。值校验由调用方完成。
    """
    updates = updates or {}
    removes = {_env_name(name) for name in (removes or [])}
    wanted = {_env_name(name): value for name, value in updates.items()}
    lines: list[str] = []
    try:
        with open(env_file, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        pass  # 文件不存在 → 从空开始，按新增处理
    kept: list[str] = []
    for line in lines:
        key, _, _ = line.partition("=")
        if key in wanted:
            kept.append(f"{key}={wanted.pop(key)}")
        elif key in removes:
            continue  # 删除行
        else:
            kept.append(line)
    for key, value in wanted.items():
        kept.append(f"{key}={value}")
    if kept or lines:
        with open(env_file, "w", encoding="utf-8") as fh:
            fh.write("\n".join(kept) + "\n")

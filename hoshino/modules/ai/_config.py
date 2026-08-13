"""AI 模块配置数据模型。

配置由 ``hoshino/core/service.py`` 的 ``Service(config_type=AIConfig)`` 管理，
首次加载自动生成 ``hoshino/service_config/aichat.json``。
provider 的 key 明文落 JSON（用户明确要求），写入 ``hoshino/service_config/``
该目录已被 .gitignore 忽略；任何日志、命令输出都必须脱敏。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ._prompts import DEFAULT_SYSTEM_PROMPT

ProviderKind = Literal["openai_chat", "openai_responses", "anthropic"]
ThemeKind = Literal["light", "dark"]


@dataclass(frozen=True, slots=True)
class ProviderOptions:
    """单个 provider 的采样参数。None 表示沿用模型/网关默认值。"""

    kind: ProviderKind = "openai_chat"
    model: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """一个 provider 的接入配置。key/url 都是配置项，明文落 JSON。"""

    url: str = ""
    key: str = ""
    config: ProviderOptions = field(default_factory=ProviderOptions)


@dataclass(frozen=True, slots=True)
class AIConfig:
    default: str = ""
    # 默认人设取 prompts.DEFAULT_SYSTEM_PROMPT（plan「bot 默认人设」精修版）。
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_history_messages: int = 64
    render_timeout_seconds: float = 30.0
    render_theme: ThemeKind = "light"
    # computer 工具的工作根目录；空字符串 → data_dir / "ai_computer"。
    # 只作为冻结 workspace 的 cwd，不是完整 sandbox（见 computer/_runtime.py）。
    computer_workdir: str = ""
    # 代理走显式配置而非环境变量：与 info-x 一致，避免读入无法解析的
    # ``ALL_PROXY=socks://...`` 环境变量导致 httpx 崩溃。支持 http(s):// 与
    # socks://（后者归一化为 socks5://）。
    proxy: str | None = None
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    # Task 默认审批模式：auto（high-risk 工具 deferred approval）/
    # always（全部工具先审批）/ never（不审批）。创建 Task 时冻结进 capability snapshot。
    task_approval_mode: str = "auto"
    # 聊天执行护栏（plan aichat-context-timeout：持久化不替代超时）：
    # run 墙钟上限；run 内模型请求次数上限（UsageLimits.request_limit）。
    chat_run_timeout_seconds: float = 180.0
    chat_max_requests: int = 12
    # 上下文内存缓存（LRU）：驻留 scope 数与每 scope 驻留对话数，超限先 flush 再逐出。
    chat_memory_scopes: int = 256
    chat_memory_conversations: int = 4
    # 原生联网搜索：anthropic / openai_responses kind 的 provider 通过服务端
    # ``web_search_20250305`` 工具搜索（DeepSeek 的 ``/anthropic`` 端点支持），
    # 不依赖 duckduckgo/web_fetch 的客户端抓取；openai_chat 不支持时自动跳过。
    web_search_native: bool = True
    # 工具调用失败重试预算（pydantic-ai 默认 1）。web_fetch 等抓取工具偶发失败
    # 会触发 "exceeded max retries" 直接杀掉整轮 run，调高以容错。
    tool_max_retries: int = 3
    # web_fetch 抓取网页时的 HTTPS 证书校验开关。默认 False：与仓库其它下载路径
    # （hoshino/util/playwrights.py 已全局 ssl._create_unverified_context）一致，
    # 避免本环境证书链不完整导致抓取失败；可信环境可改为 True。
    web_fetch_verify_ssl: bool = False
    # Markdown 渲染清晰度：Playwright 截图 device scale factor（2.0 = 2x）。
    render_device_scale: float = 2.0
    # 渲染时是否启用彩色 emoji 字体（部分系统无 emoji 字体时关掉可避免方框）。
    render_emoji: bool = True

    def get_provider(self, provider_id: str) -> ProviderConfig | None:
        return self.providers.get(provider_id)

    def has_provider(self, provider_id: str) -> bool:
        return provider_id in self.providers


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

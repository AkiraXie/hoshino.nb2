"""Shared test fixtures for hoshino nonebug tests."""

from __future__ import annotations

import os
from dataclasses import fields as dataclass_fields
from itertools import count

import pytest
from nonebug import NONEBOT_INIT_KWARGS

from fake_ai_server import start_fake_server

#: 测试注入的全局超级用户（Milky 平台格式 ``milky:<user_id>``）。本机
#: ``.env.prod`` 的 SUPERUSERS 在 pytest_configure 中被显式覆盖，测试只认此值。
TEST_SUPERUSER = "milky:10086"

# 共享 message_seq 计数器：Alconna 的全局 unimsg_cache 按
# ``{message_seq}@{scene}:{peer_id}`` 键控，跨测试复用同一 seq 会串用解析结果。
# 各测试文件统一从 conftest 取号，保证本会话内全局唯一。起点取 1000000，高于
# 仓库既有硬编码 seq（7/1000/1001/7001）与旧计数器起点（100000~500000），
# 与尚未迁移的取值不重叠。
_seq = count(1_000_000)


def next_seq() -> int:
    """返回本 pytest 会话内全局唯一的 message_seq。"""
    return next(_seq)


# 确定性环境变量：pydantic-settings 的取值优先级为 init kwargs > 环境变量 >
# ``.env.prod``。nonebot.init 的 init kwargs 只影响 driver config；HoshinoConfig
# （hoshino/core/config.py 的模块级实例）与 milky adapter 的 get_plugin_config
# 各自直接读 ``.env.prod``，需用环境变量压过文件值（JSON 编码，含空 AI_*）。
_TEST_CONFIG_ENV = {
    "SUPERUSERS": '["milky:10086"]',
    "NICKNAME": "[]",
    "DATA": "data",
    "STATIC": "static",
    "MODULES": ('["information", "interactive", "develop", "tools", "entertainment", "ai"]'),
    "DEBUG": "false",
    "MILKY_CLIENTS": "[]",
    "MILKY_WEBHOOK": "null",
}


def pytest_configure(config):
    """Keep tests independent from an ignored local ``.env.prod`` file.

    ``NONEBOT_INIT_KWARGS`` 由 nonebug 的 session autouse fixture 传入
    ``nonebot.init(**kwargs)``；init kwargs 优先级高于 ``.env.prod``，因此这里
    显式给出全部会被 ``.env.prod`` 覆盖的全局字段（含注入的 superusers），
    保证 matcher 权限与 ``_superuser_id()`` 等不依赖本机配置。
    """
    config.stash[NONEBOT_INIT_KWARGS] = {
        "command_start": {"/", ""},
        "command_sep": {"."},
        "superusers": {TEST_SUPERUSER},
        "nickname": set(),
        "data": "data",
        "static": "static",
        "modules": [
            "information",
            "interactive",
            "develop",
            "tools",
            "entertainment",
            "ai",
        ],
        "debug": False,
    }
    # 环境变量兜底：先于任何 hoshino import 写入（pytest_configure 早于收集），
    # 压过 .env.prod 对 HoshinoConfig / milky adapter 的读取。
    for key, value in _TEST_CONFIG_ENV.items():
        os.environ[key] = value
    # AI_* 空值 = 未设置（hoshino/ai/config.py 约定 env 优先于文件），压过
    # .env.prod 的 AI_* 行。AIConfig 字段列表在 hook 内动态导入：若在 conftest
    # 模块级导入，hoshino/__init__ 会在 env 隔离前实例化 HoshinoConfig。
    from hoshino.ai.config import AIConfig

    for name in _ai_env_names(AIConfig):
        os.environ[name] = ""


def _ai_env_names(ai_config_cls) -> list[str]:
    return ["AI_DEFAULT_PROVIDER"] + [
        f"AI_{field.name.upper()}" for field in dataclass_fields(ai_config_cls)
    ]


@pytest.fixture
def _clear_uninfo_cache():
    """清空 nonebot-plugin-uninfo 的会话/成员缓存，保证测试隔离。

    milky 适配器的 ``get_session_id`` 为 ``{peer_id}_{sender_id}``，不含消息
    序号。跨测试复用同一（群、用户）组合时，前一个测试缓存的 Session（例如
    role=admin）会污染后一个测试（例如 role=member），使 uninfo 权限判断误判。

    仅由 AI 测试文件（``pytestmark = pytest.mark.usefixtures(...)``）使用：
    其他测试依赖 uninfo 缓存的热缓存行为，统一全局清空会破坏它们。
    """
    from nonebot_plugin_uninfo.adapters import INFO_FETCHER_MAPPING

    # 映射按 bot.adapter.get_name() 的显示名（如 "Milky"、"OneBot V11"）键控，
    # 由 nonebot-plugin-uninfo 在适配器注册时填充；get_session 找不到时会惰性
    # 注册。只需清空映射中已注册的 fetcher（含 milky）即可。
    for fetcher in INFO_FETCHER_MAPPING.values():
        fetcher.clean()
    yield


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    """把 ai store 指向临时 SQLite 库并建全表，隔离 DB 状态。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # 先导入 task store 以注册其表类（ai_task_*）到共享 Base.metadata，
    # 否则 create_all 不会建 task 表。task store 不 import providers 链。
    import hoshino.ai.task.store  # noqa: F401
    from hoshino.ai import store

    eng = create_engine(f"sqlite:///{tmp_path / 'aichat.db'}")
    store.Base.metadata.create_all(eng)
    monkeypatch.setattr(store, "engine", eng)
    monkeypatch.setattr(store, "Session", sessionmaker(bind=eng, expire_on_commit=False))
    return store


@pytest.fixture
def fake_ai_server():
    """本地 fake OpenAI/Anthropic HTTP 服务器，返回 (base_url, requests, stop)。

    每个测试独立服务器实例：base_url 直接作 provider 的 url；requests 记录每个
    到达的请求（路径/header/body），供断言；stop 在测试结束时关闭服务器。
    """
    base_url, requests, stop = start_fake_server()
    yield base_url, requests
    stop()


@pytest.fixture(scope="session")
def _nonebot_bootstrap():
    """One-time NoneBot init + full plugin load — session-scoped for speed.

    这里的 ``nonebot.init()`` 是 no-op：nonebug 的 session autouse fixture
    ``_nonebot_init`` 已用 ``NONEBOT_INIT_KWARGS`` 完成初始化（见 pytest_configure），
    本 fixture 只负责注册适配器并加载全部插件。依赖"session autouse 先于本
    fixture 实例化"的既有顺序，保持不动。
    """
    import nonebot

    nonebot.init()
    from nonebot.adapters.milky import Adapter as MilkyAdapter
    from nonebot.adapters.onebot.v11 import Adapter

    nonebot.get_driver().register_adapter(Adapter)
    nonebot.get_driver().register_adapter(MilkyAdapter)
    nonebot.load_plugin("nonebot_plugin_alconna")
    nonebot.load_plugin("nonebot_plugin_uninfo")
    import hoshino.bootstrap as b

    b.bootstrap()
    nonebot.load_plugins("hoshino/base")
    for cat in (
        "information",
        "interactive",
        "tools",
        "develop",
        "entertainment",
        "ai",
    ):
        nonebot.load_plugins(f"hoshino/modules/{cat}")
    # info-x is intentionally opt-in in production; load it explicitly for tests.
    nonebot.load_plugins("hoshino/modules/info-x")
    yield
    # 无 teardown：bootstrap 已在工作区 data/ 下创建运行目录（非只读）。

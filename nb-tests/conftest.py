"""Shared test fixtures for hoshino nonebug tests."""

import pytest
from nonebug import NONEBOT_INIT_KWARGS


def pytest_configure(config):
    """Keep tests independent from an ignored local ``.env.prod`` file."""

    config.stash[NONEBOT_INIT_KWARGS] = {
        "command_start": {"/", ""},
        "command_sep": {"."},
    }


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


@pytest.fixture(scope="session")
def _nonebot_bootstrap():
    """One-time NoneBot init + full plugin load — session-scoped for speed."""
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
    # No teardown needed — tests are read-only

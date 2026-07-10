"""Shared test fixtures for hoshino nonebug tests."""

import pytest


@pytest.fixture(scope="session")
def _nonebot_bootstrap():
    """One-time NoneBot init + full plugin load — session-scoped for speed."""
    import nonebot
    nonebot.init()
    from nonebot.adapters.onebot.v11 import Adapter
    nonebot.get_driver().register_adapter(Adapter)
    nonebot.load_plugin("nonebot_plugin_alconna")
    nonebot.load_plugin("nonebot_plugin_uninfo")
    import hoshino.bootstrap as b
    b.bootstrap()
    nonebot.load_plugins("hoshino/base")
    for cat in ("information", "interactive", "tools", "develop", "entertainment"):
        nonebot.load_plugins(f"hoshino/modules/{cat}")
    yield
    # No teardown needed — tests are read-only

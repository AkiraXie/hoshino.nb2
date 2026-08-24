"""AI 模块测试共享 fixture。

``_fresh_conversation_manager`` 和 ``_clear_uninfo_cache`` 由多数 AI 测试使用，
从原 test_ai_chat.py 下沉到此处，避免每个测试文件重复声明。
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fresh_conversation_manager(monkeypatch):
    """每个测试独立 ConversationManager：单例内存缓存会跨测试残留。"""
    from hoshino.ai import sessions

    manager = sessions.ConversationManager()
    monkeypatch.setattr(sessions, "conversation_manager", manager)
    return manager


@pytest.fixture(autouse=True)
def _auto_clear_uninfo_cache(_clear_uninfo_cache):
    """自动清空 uninfo 缓存：AI 测试复用同一（群、用户）组合做不同 role 断言。

    根 conftest 的 ``_clear_uninfo_cache`` 不是 autouse（其他测试依赖热缓存），
    AI 子目录通过此包装器使其 autouse。
    """

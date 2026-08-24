"""一次性探针：web_fetch 反爬站点抓取验证（联网，不进入常规测试）。

运行方式（必须显式开启）：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_web_fetch_live.py -s -q

覆盖两件事：
1. fetch_url_to_markdown + 默认浏览器 UA 能获取微信公众号正文（非反爬页面）；
2. extra_headers 参数可自定义请求头（User-Agent / Referer 等）。

只打印脱敏结果（长度、标题片段），不落敏感信息。
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="临时联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
]

WECHAT_URL = "https://mp.weixin.qq.com/s/8maraWkChNFu27tgRZiA_Q"


async def test_wechat_default_ua_fetches_content():
    """默认浏览器 UA 应能绕过微信公众号反爬，获取文章正文。"""
    from hoshino.ai.tools.web.web_fetch import _DEFAULT_UA, fetch_url_to_markdown

    result = await fetch_url_to_markdown(
        WECHAT_URL,
        extra_headers={"User-Agent": _DEFAULT_UA},
    )

    # 反爬页面特征：短文本 + "环境异常"
    assert "环境异常" not in result, f"仍命中反爬页面: {result[:200]}"
    assert len(result) > 200, f"内容过短 ({len(result)} chars): {result[:200]}"

    print(f"[web_fetch] WeChat OK: {len(result)} chars")
    print(f"[web_fetch] Title snippet: {result[:80]}")


async def test_wechat_custom_ua_and_referer():
    """extra_headers 支持自定义 UA + Referer。"""
    from hoshino.ai.tools.web.web_fetch import fetch_url_to_markdown

    result = await fetch_url_to_markdown(
        WECHAT_URL,
        extra_headers={
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 14) "
                "AppleWebKit/537.36 Chrome/125.0 Mobile Safari/537.36"
            ),
            "Referer": "https://mp.weixin.qq.com/",
        },
    )

    assert "环境异常" not in result, f"自定义头仍命中反爬: {result[:200]}"
    assert len(result) > 200, f"内容过短 ({len(result)} chars)"

    print(f"[web_fetch] Custom headers OK: {len(result)} chars")


async def test_no_ua_gets_blocked():
    """不带 UA 时应命中反爬（验证探针本身有效）。"""
    from hoshino.ai.tools.web.web_fetch import fetch_url_to_markdown

    result = await fetch_url_to_markdown(WECHAT_URL)

    # 这个断言验证"不加 UA 确实会被拦"——如果微信改了策略不再拦截，
    # 此测试会失败，提示我们更新探针逻辑。
    is_blocked = "环境异常" in result or len(result) < 200
    print(f"[web_fetch] No-UA blocked: {is_blocked} ({len(result)} chars)")
    assert is_blocked, "未加 UA 也能获取正文？反爬策略可能已变更，请更新探针。"

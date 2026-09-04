"""一次性探针：NGA / 小黑盒 解析器真实链路（联网，不进入常规测试）。

运行方式（必须显式开启）：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_nga_xiaoheihe_live.py -s -q

- NGA：tid=47380972（求手柄推荐），验证 guestJs 挑战 → __output=11 JSON → Post。
- 小黑盒：link_id=127801232，验证指纹注册 + 签名 API；当前匿名访问大概率被
  show_captcha 风控拦截（记录状态，断言不崩溃）。
"""

from __future__ import annotations

import os

import pytest
from _live import load_fixture

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
    pytest.mark.usefixtures("_nonebot_bootstrap"),
]

_NGA_FIXTURE = load_fixture("nga_xiaoheihe")
NGA_TID = _NGA_FIXTURE["nga_tid"]
XHH_LINK_ID = _NGA_FIXTURE["xiaoheihe_link_id"]


async def test_nga_live():
    from hoshino.modules.information.resolve import nga

    post = await nga.parse_nga(NGA_TID)
    print(f"\nNGA tid={NGA_TID}: {'Post' if post else 'None'}")
    if post:
        print(f"  标题: {post.title}")
        print(f"  作者: {post.nickname}")
        print(f"  正文前 80 字: {post.content[:80]!r}")
        print(f"  图片: {len(post.images)} 张，首图: {post.images[0] if post.images else '-'}")
        print(f"  链接: {post.url}")
    assert post is not None, "NGA 解析失败"
    assert post.title and post.content


async def test_xiaoheihe_live():
    from hoshino.modules.information.resolve import xiaoheihe

    post = await xiaoheihe.parse_xiaoheihe(XHH_LINK_ID)
    print(f"\n小黑盒 link_id={XHH_LINK_ID}: {'Post' if post else 'None'}")
    if post:
        print(f"  标题: {post.title}")
        print(f"  作者: {post.nickname}")
        print(f"  正文: {post.content[:80]!r}")
        print(f"  图片: {len(post.images)}，视频: {len(post.videos)}")
    else:
        print("  （大概率 show_captcha 匿名风控，属预期降级）")
    # 探针只断言"不崩溃"：解析结果取决于小黑盒风控状态。

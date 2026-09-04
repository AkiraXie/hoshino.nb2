"""一次性探针：抖音分享链接的页面状态（联网，不进入常规测试）。

运行方式（必须显式开启）：

    ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/test_douyin_page_live.py -s -q

被测 URL：https://v.douyin.com/LNTg1_fHEfo/

要点：分享页 SSR 是否内嵌 videoInfoRes 取决于请求带不带匿名 ttwid cookie
（实现移植自 https://github.com/Zhalslar/astrbot_plugin_parser）。本探针记录
无 cookie 与带 ttwid 两种页面状态，并跑当前解析器完整链路（ttwid 注册 →
分享页 → Post），原始 HTML / _ROUTER_DATA JSON 存档到 .agent-tmp/douyin_oneshot/。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from _live import load_fixture

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ONE_SHOT_LIVE"),
        reason="联网探针：设置 ONE_SHOT_LIVE=1 才运行",
    ),
    pytest.mark.usefixtures("_nonebot_bootstrap"),
]

SHARE_URL = load_fixture("douyin")["share_url"]
OUT_DIR = Path(".agent-tmp/douyin_oneshot")
ROUTER_PATTERN = re.compile(r"window\._ROUTER_DATA\s*=\s*(.*?)</script>", re.DOTALL)
SPIDER_HEADER = {
    "User-Agent": "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)"
}
# 关注这些 key 是否出现在 _ROUTER_DATA 里（出现=页面仍内嵌某类数据）。
INTERESTING_KEYS = (
    "videoInfoRes",
    "item_list",
    "aweme_detail",
    "awemeId",
    "play_addr",
    "url_list",
    "desc",
    "nickname",
    "video",
    "cover",
    "images",
)


def _count_keys(obj, counts: dict[str, int]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in INTERESTING_KEYS:
                counts[key] = counts.get(key, 0) + 1
            _count_keys(value, counts)
    elif isinstance(obj, list):
        for item in obj:
            _count_keys(item, counts)


async def _probe(aiohttpx, name: str, url: str, headers: dict) -> dict:
    resp = await aiohttpx.get(
        url,
        headers=headers,
        verify=True,
        follow_redirects=False,
        timeout=20.0,
    )
    info = {
        "name": name,
        "url": url,
        "status": resp.status_code,
        "len": len(resp.content),
        "ct": resp.headers.get("content-type", ""),
        "location": resp.headers.get("location", ""),
    }
    html = resp.text or ""
    (OUT_DIR / f"{name}.html").write_text(html, encoding="utf-8", errors="replace")

    matched = ROUTER_PATTERN.search(html)
    if not matched:
        info["router_data"] = False
        info["json_ld"] = '"@type"' in html and "ld+json" in html
        print(f"[{name}] status={info['status']} len={info['len']} 无 _ROUTER_DATA")
        return info

    info["router_data"] = True
    try:
        router = json.loads(matched.group(1).strip())
    except json.JSONDecodeError as exc:
        info["router_json_error"] = str(exc)[:200]
        print(f"[{name}] _ROUTER_DATA JSON 解析失败: {exc}")
        return info
    (OUT_DIR / f"{name}_router.json").write_text(
        json.dumps(router, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    loader = router.get("loaderData", {})
    info["loader_keys"] = list(loader)
    counts: dict[str, int] = {}
    _count_keys(router, counts)
    info["interesting_keys"] = counts

    page = None
    for slot in ("video_(id)/page", "note_(id)/page"):
        if isinstance(loader.get(slot), dict):
            page = loader[slot]
            info["data_slot"] = slot
            break
    if page is None:
        print(f"[{name}] loaderData 无 video/note page 槽: {info['loader_keys']}")
        return info

    info["slot_keys"] = list(page)
    info["slot_item_id"] = page.get("itemId", "")
    info["slot_last_path"] = page.get("lastPath", "")
    has_data = any(key in page for key in ("videoInfoRes", "aweme_detail", "item_list", "desc"))
    info["slot_has_video_data"] = has_data
    print(
        f"[{name}] status={info['status']} len={info['len']} slot={info['data_slot']} "
        f"槽内 key={len(info['slot_keys'])} 含视频数据={has_data} "
        f"全局有趣 key={counts or '无'}"
    )
    return info


async def _current_parser_result(douyin_module, aiohttpx, name: str, url: str) -> str:
    """跑当前解析器的完整路径（parse_share_url 或 _extract_data），记录结果。"""
    try:
        if name == "share":
            post = await douyin_module.DouyinParser().parse_share_url(url)
            return f"parse_share_url -> {'Post' if post else 'None'}"
        resp = await aiohttpx.get(url, headers=douyin_module.IOS_HEADER, verify=True, timeout=20.0)
        video_data = douyin_module.DouyinParser()._extract_data(resp.text or "")
        return f"_extract_data -> {'VideoData' if video_data else 'None'}"
    except Exception as exc:
        return f"异常: {type(exc).__name__}: {exc}"


async def test_douyin_page_state():
    from hoshino.modules.information.resolve import douyin
    from hoshino.util import aiohttpx
    from hoshino.util.network import get_redirect

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n探测分享链接: {SHARE_URL}")

    redirect_url = await get_redirect(SHARE_URL)
    print(f"短链重定向 -> {redirect_url}")
    matched = re.search(r"(slides|video|note)/(\d+)", redirect_url or "")
    assert matched, f"重定向 URL 不匹配 (slides|video|note)/id: {redirect_url}"
    kind, video_id = matched.group(1), matched.group(2)
    print(f"识别类型={kind} id={video_id}")

    # 无 cookie 的裸页面状态（记录旧行为）。
    probes = [
        ("m_douyin", f"https://m.douyin.com/share/{kind}/{video_id}", douyin.IOS_HEADER),
        ("iesdouyin", f"https://www.iesdouyin.com/share/{kind}/{video_id}", douyin.IOS_HEADER),
        ("www", f"https://www.douyin.com/{kind}/{video_id}", douyin.IOS_HEADER),
        ("www_spider", f"https://www.douyin.com/{kind}/{video_id}", SPIDER_HEADER),
    ]
    results = {}
    for name, url, headers in probes:
        results[name] = await _probe(aiohttpx, name, url, headers)

    # 带 ttwid cookie 的分享页（当前解析器的实际请求形态）。
    parser = douyin.DouyinParser()
    ttwid = await parser.ensure_ttwid()
    print(f"ttwid: {'已注册' if ttwid else '注册失败'}")
    ttwid_headers = {**douyin.IOS_HEADER, "Cookie": ttwid} if ttwid else douyin.IOS_HEADER
    for name, url in [
        ("m_douyin_ttwid", f"https://m.douyin.com/share/{kind}/{video_id}"),
        ("iesdouyin_ttwid", f"https://www.iesdouyin.com/share/{kind}/{video_id}"),
    ]:
        results[name] = await _probe(aiohttpx, name, url, ttwid_headers)

    # 当前解析器在真实页面上走一遍（必须优雅降级，不允许抛异常）。
    for name, url, _headers in probes:
        results[name]["parser"] = await _current_parser_result(douyin, aiohttpx, "raw", url)

    # 完整解析链路：ttwid 注册 → 分享页 → Post（含视频）。
    post = await parser.parse_share_url(SHARE_URL)
    results["parse_share_url"] = "Post" if post else "None"
    if post:
        print(
            f"parse_share_url({SHARE_URL}) -> Post: 作者={post.nickname} "
            f"desc={post.content[:40]!r} videos={len(post.videos)} images={len(post.images)}"
        )
    else:
        print(f"parse_share_url({SHARE_URL}) -> None")

    summary = {
        "share_url": SHARE_URL,
        "redirect": redirect_url,
        "kind": kind,
        "id": video_id,
        "probes": results,
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\n存档目录: {OUT_DIR}/")

    # 断言只锁定"当前逻辑"的契约：任何页面状态都不允许让解析器抛异常。
    assert "异常" not in results["m_douyin"]["parser"]
    # 带 ttwid 的分享页必须内嵌视频数据（这是解析成功的前提）。
    assert results["m_douyin_ttwid"]["slot_has_video_data"]
    # 完整链路必须解析出 Post 且带视频。
    assert post is not None and post.videos

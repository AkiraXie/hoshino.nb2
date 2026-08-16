"""NGA / 小黑盒 解析器单元测试：monkeypatch aiohttpx，不发真实网络请求。"""

from __future__ import annotations

import json

import httpx
import pytest

pytestmark = pytest.mark.usefixtures("_nonebot_bootstrap")

NGA_JSON = {
    "data": {
        "__GLOBAL": {"_ATTACH_BASE_VIEW": "img.nga.cn/attachments"},
        "__U": {"43207689": {"uid": 43207689, "username": "UID:43207689"}},
        "__T": {"tid": 47380972, "subject": "求手柄推荐，预算200-250"},
        "__R": [
            {
                "content": "请朋友帮了个忙，送他的礼物。<br/><br/>[img]/mon_202608/16/9aQ37-fxq3K2cT1kShs-13i.jpg[/img]",
                "authorid": 43207689,
                "postdatetimestamp": 1786839450,
                "lou": 0,
                "attachs": [
                    {
                        "attachurl": "mon_202608/16/9aQ37-fxq3K2cT1kShs-13i.jpg",
                        "type": "img",
                        "url_utf8_org_name": "temp.jpg",
                    }
                ],
            }
        ],
    },
    "time": 1786863100,
}
CHALLENGE_HTML = (
    "<html><script>document.cookie='guestJs=1786862966_1h2mn0k';"
    "location.replace('/read.php')</script></html>"
)


def _response(status_code: int, body: str, set_cookies: list[str] | None = None) -> httpx.Response:
    from hoshino.util.aiohttpx import Response

    headers = httpx.Headers(
        [("set-cookie", c) for c in (set_cookies or [])] + [("content-type", "text/html")]
    )
    return Response(
        httpx.URL("https://bbs.nga.cn/read.php"),
        body.encode(),
        status_code,
        headers,
        _resp=httpx.Response(status_code, content=body.encode(), headers=headers),
        text=body,
    )


def _nga_json_response() -> httpx.Response:
    body = "window.script_muti_get_var_store=" + json.dumps(NGA_JSON)
    return _response(200, body)


# ---------------------------------------------------------------- NGA


def test_clean_nga_text():
    from hoshino.modules.information.resolve.nga import clean_nga_text

    raw = (
        "[quote]引用内容[/quote]看这个 [url=https://example.com]链接[/url] 和 [b]加粗[/b]\n\n"
        "[img]/mon_1.jpg[/img]<br/><br/>第二行"
    )
    cleaned = clean_nga_text(raw)
    assert "引用内容" not in cleaned
    assert "链接" in cleaned
    assert "加粗" in cleaned
    assert "[img]" not in cleaned
    assert "example.com" not in cleaned
    assert "<br" not in cleaned
    assert "第二行" in cleaned


async def test_parse_nga_with_guestjs_challenge(monkeypatch):
    from hoshino.modules.information.resolve import nga
    from hoshino.util import aiohttpx

    calls: list[dict] = []

    async def fake_get(url, headers=None, timeout=None, **kwargs):
        calls.append({"url": url, "headers": headers})
        if len(calls) == 1:
            return _response(
                403,
                CHALLENGE_HTML,
                set_cookies=[
                    "ngaPassportUid=guest06a8; Max-Age=36000; domain=.nga.cn",
                    "lastvisit=1786862982; domain=bbs.nga.cn",
                ],
            )
        return _nga_json_response()

    monkeypatch.setattr(aiohttpx, "get", fake_get)

    post = await nga.parse_nga("47380972")
    assert post is not None
    assert post.title == "求手柄推荐，预算200-250"
    assert post.nickname == "UID:43207689"
    assert "送他的礼物" in post.content
    assert "[img]" not in post.content
    # 图片：attachs + [img] BBCode 去重后只有一张
    assert post.images == [
        "https://img.nga.178.com/attachments/mon_202608/16/9aQ37-fxq3K2cT1kShs-13i.jpg"
    ]
    assert post.timestamp == 1786839450.0
    # 挑战流程：第一次 403 后带 guestJs + Set-Cookie 重试，URL 带 rand
    assert len(calls) == 2
    cookie = calls[1]["headers"].get("Cookie", "")
    assert "guestJs=1786862966_1h2mn0k" in cookie
    assert "ngaPassportUid=guest06a8" in cookie
    assert "rand=" in calls[1]["url"]


async def test_parse_nga_direct_200(monkeypatch):
    from hoshino.modules.information.resolve import nga
    from hoshino.util import aiohttpx

    calls = []

    async def fake_get(url, headers=None, timeout=None, **kwargs):
        calls.append(url)
        return _nga_json_response()

    monkeypatch.setattr(aiohttpx, "get", fake_get)
    post = await nga.parse_nga("47380972")
    assert post is not None
    assert len(calls) == 1


async def test_parse_nga_garbage_response(monkeypatch):
    from hoshino.modules.information.resolve import nga
    from hoshino.util import aiohttpx

    async def fake_get(url, headers=None, timeout=None, **kwargs):
        return _response(200, "<html>风控页面</html>")

    monkeypatch.setattr(aiohttpx, "get", fake_get)
    assert await nga.parse_nga("47380972") is None


# ---------------------------------------------------------------- 小黑盒

XHH_LINK_TREE = {
    "status": "ok",
    "result": {
        "link": {
            "title": "荒野之地的隐藏机制",
            "has_video": True,
            "video_url": "https://example.com/video.mp4",
            "user": {"username": "测试玩家"},
            "text": json.dumps(
                [
                    {"type": "text", "text": "<p>第一段</p><br/><p>第二段</p>"},
                    {"type": "img", "url": "https://imgheybox.max-c.com/bbs/2024/01/01/a.jpg"},
                ]
            ),
        }
    },
}


@pytest.fixture(autouse=True)
def _reset_device_cache(monkeypatch):
    from hoshino.modules.information.resolve import xiaoheihe

    monkeypatch.setattr(xiaoheihe, "_device_id", None)


def test_sign_path_deterministic():
    from hoshino.modules.information.resolve.xiaoheihe import _sign_path

    assert _sign_path("/bbs/app/link/tree", 1786863113, "NONCE1") == _sign_path(
        "/bbs/app/link/tree", 1786863113, "NONCE1"
    )
    assert len(_sign_path("/bbs/app/link/tree", 1786863113, "NONCE1")) > 0
    # 同一 (ts, nonce) 结果稳定；nonce 变化会改变签名（原版算法对 path/ts 不敏感）。
    assert _sign_path("/bbs/app/link/tree", 1786863113, "NONCE1") != _sign_path(
        "/bbs/app/link/tree", 1786863113, "NONCE2"
    )


async def test_parse_xiaoheihe(monkeypatch):
    from hoshino.modules.information.resolve import xiaoheihe
    from hoshino.util import aiohttpx

    gets = []

    async def fake_post(url, json_body=None, headers=None, timeout=None, **kwargs):
        assert url == xiaoheihe.FP_URL
        return _response(200, json.dumps({"code": 1100, "detail": {"deviceId": "dev123"}}))

    async def fake_get(url, params=None, cookies=None, headers=None, timeout=None, **kwargs):
        gets.append({"params": params, "cookies": cookies})
        return _response(200, json.dumps(XHH_LINK_TREE))

    monkeypatch.setattr(aiohttpx, "post", fake_post)
    monkeypatch.setattr(aiohttpx, "get", fake_get)

    post = await xiaoheihe.parse_xiaoheihe("127801232")
    assert post is not None
    assert post.title == "荒野之地的隐藏机制"
    assert post.nickname == "测试玩家"
    assert "第一段" in post.content and "第二段" in post.content
    assert post.images == ["https://imgheybox.max-c.com/bbs/2024/01/01/a.jpg"]
    assert post.videos == ["https://example.com/video.mp4"]
    assert post.url == "https://www.xiaoheihe.cn/app/bbs/link/127801232"

    # 签名参数 + x_xhh_tokenid cookie
    params = gets[0]["params"]
    assert params["link_id"] == "127801232"
    assert params["hkey"] and params["_time"] and params["nonce"]
    assert gets[0]["cookies"] == {"x_xhh_tokenid": "Bdev123"}


async def test_parse_xiaoheihe_captcha_degrades(monkeypatch):
    from hoshino.modules.information.resolve import xiaoheihe
    from hoshino.util import aiohttpx

    async def fake_post(url, json_body=None, headers=None, timeout=None, **kwargs):
        return _response(200, json.dumps({"code": 1100, "detail": {"deviceId": "dev123"}}))

    async def fake_get(url, params=None, cookies=None, headers=None, timeout=None, **kwargs):
        # 风控：匿名设备被验证码拦截
        return _response(200, json.dumps({"status": "show_captcha", "result": {}}))

    monkeypatch.setattr(aiohttpx, "post", fake_post)
    monkeypatch.setattr(aiohttpx, "get", fake_get)

    assert await xiaoheihe.parse_xiaoheihe("127801232") is None

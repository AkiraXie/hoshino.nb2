"""douyin 解析模块单元测试：只测纯函数 _extract_data，不发起网络请求。

解析失败必须走“记日志 + 返回 None”的降级路径（反爬页/布局变化），
不允许向 handler 抛 pydantic ValidationError。
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.usefixtures("_nonebot_bootstrap")


def _html(router_data: dict) -> str:
    return f"<script>window._ROUTER_DATA = {json.dumps(router_data)}</script>"


def _router_data(video_page: dict | None = None, note_page: dict | None = None) -> dict:
    loader_data: dict = {}
    if video_page is not None:
        loader_data["video_(id)/page"] = video_page
    if note_page is not None:
        loader_data["note_(id)/page"] = note_page
    return {"loaderData": loader_data}


def _valid_video_page() -> dict:
    return {
        "videoInfoRes": {
            "item_list": [
                {
                    "desc": "测试视频描述",
                    "author": {"nickname": "测试作者"},
                    "video": {
                        "play_addr": {"url_list": ["https://example.com/playwm/v.mp4"]},
                        "cover": {"url_list": ["https://example.com/cover.jpg"]},
                    },
                }
            ]
        }
    }


def _extract(text: str):
    from hoshino.modules.information.resolve.douyin import DouyinParser

    return DouyinParser()._extract_data(text)


def test_extract_valid_video_page():
    video_data = _extract(_html(_router_data(video_page=_valid_video_page())))
    assert video_data is not None
    assert video_data.desc == "测试视频描述"
    assert video_data.author.nickname == "测试作者"
    assert video_data.video_url == "https://example.com/play/v.mp4"
    assert video_data.cover_url == "https://example.com/cover.jpg"


def test_extract_valid_note_page():
    video_data = _extract(_html(_router_data(note_page=_valid_video_page())))
    assert video_data is not None
    assert video_data.desc == "测试视频描述"


def test_extract_no_router_data():
    assert _extract("<html><body>verify</body></html>") is None


def test_extract_changed_layout_no_video_info_res():
    """抖音改版：video_(id)/page 存在但不带 videoInfoRes（如 ua/is_use_ulink 配置）时，
    必须返回 None 而不是抛 pydantic ValidationError。"""
    changed = _router_data(
        video_page={
            "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)",
            "is_use_ulink": False,
        }
    )
    assert _extract(_html(changed)) is None


def test_extract_changed_layout_empty_item_list():
    """videoInfoRes 存在但 item_list 为空（反爬/无数据页）→ None。"""
    page = {"videoInfoRes": {"item_list": []}}
    assert _extract(_html(_router_data(video_page=page))) is None


def test_play_token_from_uri():
    """play_token 优先取 play_addr.uri（分享页带 ttwid 时的标准形态）。"""
    video_data = _extract(
        _html(
            _router_data(
                video_page={
                    "videoInfoRes": {
                        "item_list": [
                            {
                                "desc": "t",
                                "author": {"nickname": "a"},
                                "video": {
                                    "play_addr": {
                                        "uri": "v2700fgi0000d9usjo7og65opgh7ad6g",
                                        "url_list": [
                                            "https://aweme.snssdk.com/aweme/v1/playwm/?video_id=v2700fgi0000d9usjo7og65opgh7ad6g"
                                        ],
                                    },
                                    "cover": {"url_list": ["https://example.com/c.jpg"]},
                                },
                            }
                        ]
                    }
                }
            )
        )
    )
    assert video_data is not None
    assert video_data.play_token == "v2700fgi0000d9usjo7og65opgh7ad6g"


def test_play_token_fallback_to_query():
    """无 uri 时从 url_list 的 video_id 查询参数提取。"""
    video_data = _extract(
        _html(
            _router_data(
                video_page={
                    "videoInfoRes": {
                        "item_list": [
                            {
                                "desc": "t",
                                "author": {"nickname": "a"},
                                "video": {
                                    "play_addr": {
                                        "url_list": [
                                            "https://aweme.snssdk.com/aweme/v1/playwm/?ratio=720p&video_id=abc123"
                                        ],
                                    },
                                    "cover": {"url_list": ["https://example.com/c.jpg"]},
                                },
                            }
                        ]
                    }
                }
            )
        )
    )
    assert video_data is not None
    assert video_data.play_token == "abc123"


def test_response_size_from_headers():
    """从 Content-Range 优先、Content-Length 兜底取文件大小。"""
    from hoshino.modules.information.resolve.douyin import DouyinParser

    parser = DouyinParser()

    class _Headers:
        def __init__(self, values: dict[str, str]) -> None:
            self._values = values

        def get(self, key: str) -> str | None:
            return self._values.get(key)

    assert parser._response_size(_Headers({"Content-Range": "bytes 0-1/20614334"})) == 20614334
    assert parser._response_size(_Headers({"Content-Length": "9376249"})) == 9376249
    assert parser._response_size(_Headers({"Content-Range": "invalid"})) == 0
    assert parser._response_size(_Headers({})) == 0


def test_ttwid_from_cookies():
    """Set-Cookie 提取 ttwid（保留 %7C 原始编码），无则 None。"""
    from hoshino.modules.information.resolve.douyin import DouyinParser

    class _Headers:
        def __init__(self, values: list[str]) -> None:
            self._values = values

        def get_list(self, key: str) -> list[str]:
            assert key == "set-cookie"
            return self._values

    ttwid = "ttwid=1%7CTm3bf76DQSGhvLoEOCMxx2aetm_xr_nDG6DoMpXo4qo%7C1786862614%7Csig"
    assert (
        DouyinParser._ttwid_from_cookies(
            _Headers([f"{ttwid}; Max-Age=86400; Path=/; Domain=.douyin.com"])
        )
        == ttwid
    )
    assert DouyinParser._ttwid_from_cookies(_Headers(["foo=bar"])) is None

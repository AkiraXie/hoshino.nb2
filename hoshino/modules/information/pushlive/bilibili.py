from datetime import datetime

from hoshino.util import aiohttpx
from .model import LiveInfo

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


async def _get_room_init(room_id: str) -> dict:
    resp = await aiohttpx.get(
        f"https://api.live.bilibili.com/room/v1/Room/room_init?id={room_id}",
        headers={**HEADERS, "Referer": f"https://live.bilibili.com/{room_id}"},
        timeout=10,
    )
    return resp.json["data"]


async def _get_anchor_info(real_room_id: int) -> dict:
    resp = await aiohttpx.get(
        f"https://api.live.bilibili.com/live_user/v1/UserInfo/get_anchor_in_room?roomid={real_room_id}",
        headers={**HEADERS, "Referer": f"https://live.bilibili.com/{real_room_id}"},
        timeout=10,
    )
    return resp.json["data"]["info"]


async def _get_room_info(real_room_id: int) -> dict:
    resp = await aiohttpx.get(
        f"https://api.live.bilibili.com/room/v1/Room/get_info?room_id={real_room_id}&from=room",
        headers={**HEADERS, "Referer": f"https://live.bilibili.com/{real_room_id}"},
        timeout=10,
    )
    return resp.json["data"]


async def get_room_status(room_id: str) -> LiveInfo:
    init_data = await _get_room_init(room_id)
    real_id = init_data["room_id"]
    live_status = init_data.get("live_status", 0)

    anchor_info = await _get_anchor_info(real_id)
    uname = anchor_info.get("uname", "")

    if live_status == 1:
        room_info = await _get_room_info(real_id)
        live_time_str = room_info.get("live_time", "")
        show_time = None
        if live_time_str:
            try:
                show_time = datetime.strptime(live_time_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        return LiveInfo(
            title=room_info.get("title", ""),
            cover=room_info.get("keyframe", ""),
            url=f"https://live.bilibili.com/{real_id}",
            anchor=uname,
            show_time=show_time,
            show_status=1,
            platform="bilibili",
        )
    else:
        return LiveInfo(
            url=f"https://live.bilibili.com/{real_id}",
            anchor=uname,
            show_status=0,
            platform="bilibili",
        )

import contextlib
from datetime import datetime

from hoshino.util import aiohttpx

from .model import LiveInfo


async def get_room_status(room_id: str) -> LiveInfo:
    url = f"https://www.douyu.com/betard/{room_id}"
    resp = await aiohttpx.get(url, headers={"Referer": f"https://www.douyu.com/{room_id}"})
    data = resp.json
    roomdata = data.get("room", {})
    if roomdata.get("show_status", 0) != 1 or roomdata.get("videoLoop", 0) == 1:
        return LiveInfo(
            url=f"https://www.douyu.com/{room_id}",
            anchor=roomdata.get("owner_name", ""),
            show_status=0,
            platform="douyu",
        )
    show_time_raw = roomdata.get("show_time", "")
    show_time = None
    if show_time_raw:
        # 时间戳异常时保持 None（无开播时间），不阻塞开播判断。
        with contextlib.suppress(ValueError, OSError):
            show_time = datetime.fromtimestamp(int(show_time_raw))
    return LiveInfo(
        title=roomdata.get("room_name", ""),
        cover=roomdata.get("room_pic", ""),
        url=f"https://www.douyu.com/{room_id}",
        anchor=roomdata.get("owner_name", ""),
        show_time=show_time,
        show_status=roomdata.get("show_status", 0),
        platform="douyu",
    )

from hoshino import MessageSegment, Message
from hoshino.util import aiohttpx, get_cookies
from time import strftime, localtime
import re
from ..bilireq.utils import BiliBiliDynamic
from hoshino.util import get_redirect

bili_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
}
bili_video_pat = re.compile(r"bilibili.com/video/(BV[A-Za-z0-9]{10})")

dyn_url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail"


async def get_dynamic_from_url(url: str) -> BiliBiliDynamic | None:
    if "t.bilibili.com" in url or "/opus" in url:
        matched = re.search(r"/(\d+)", url)
        if matched:
            uid = matched.group(1)
            params = {
                "timezone_offset": -480,
                "id": uid,
                "features": "itemOpusStyle,opusBigCover,onlyfansVote,endFooterHidden,decorationCard,onlyfansAssetsV2,ugcDelete,onlyfansQaCard,commentsNewVersion",
            }
            resp = await aiohttpx.get(
                dyn_url,
                params=params,
                cookies=await get_cookies("bilibili"),
                headers=bili_headers,
            )
            if resp.ok:
                data = resp.json.get("data", {})
                if not data:
                    return None
                card = data.get("item", {})
                if not card:
                    return None
                dyn = BiliBiliDynamic.from_dict(card)
                return dyn
    return None


async def get_bvid(url: str) -> str | None:
    if loc := await get_redirect(url):
        if mat := bili_video_pat.search(loc):
            return mat.group(1)
        else:
            return None
    return None


# 处理超过一万的数字
def handle_num(num: int) -> str:
    if num > 10000:
        s = f"{(num / 10000.0):.2f}万"
    else:
        s = str(num)
    return s


async def get_bili_video_resp(bvid: str = "", avid: str = "") -> Message | None:
    url = "https://api.bilibili.com/x/web-interface/view"
    if avid:
        url = f"https://api.bilibili.com/x/web-interface/view?aid={avid}"
    else:
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    try:
        resp = await aiohttpx.get(url, headers=bili_headers)
    except Exception:
        return None
    js = resp.json
    res = js.get("data")
    if not res:
        return None

    pubdate = strftime("%Y-%m-%d %H:%M:%S", localtime(res["pubdate"]))
    msg = []
    msg.append(str(MessageSegment.image(res["pic"])))
    msg.append(f"标题：{res['title']}")
    msg.append(f"类型：{res['tname']} | UP: {res['owner']['name']} | 日期：{pubdate}")
    msg.append(
        f"播放：{handle_num(res['stat']['view'])} | 弹幕：{handle_num(res['stat']['danmaku'])} | 收藏：{handle_num(res['stat']['favorite'])}"
    )
    msg.append(f"链接: https://www.bilibili.com/video/av{res['aid']}")
    return Message("\n".join(msg))

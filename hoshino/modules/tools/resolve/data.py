import json
from hoshino import MessageSegment, Message, on_startup
from hoshino.service import Service
from hoshino.util import aiohttpx, get_cookies, send_to_superuser
from time import strftime, localtime
import re
from urllib.parse import parse_qs, urlparse
from functools import partial

sv = Service("resolve")

bili_headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.bilibili.com/",
}
bili_pat = re.compile(r"https://www.bilibili.com/video/(.{12})")

get_xhscookies = partial(get_cookies, "xhs")


async def get_redirect(url: str, headers={}) -> str:
    resp = await aiohttpx.head(url, follow_redirects=False)
    loc = resp.headers["Location"]
    return loc


async def get_bvid(url: str) -> str:
    loc = await get_redirect(url, headers=bili_headers)
    if mat := bili_pat.match(loc):
        return mat.group(1)
    else:
        return None


# 处理超过一万的数字
def handle_num(num: int) -> str:
    if num > 10000:
        s = f"{(num / 10000.0):.2f}万"
    else:
        s = str(num)
    return s


async def get_bv_resp(bvid: str) -> Message:
    url = "https://api.bilibili.com/x/web-interface/view?bvid=" + bvid
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
    msg.append(f"类型：{res['tname']} | UP：{res['owner']['name']} | 日期：{pubdate}")
    msg.append(
        f"播放：{handle_num(res['stat']['view'])} | 弹幕：{handle_num(res['stat']['danmaku'])} | 收藏：{handle_num(res['stat']['favorite'])}"
    )
    msg.append(f"链接: https://www.bilibili.com/video/av{res['aid']}")
    return Message("\n".join(msg))


xhs_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
    "Accept": "text/html,application/signed-exchange;v=b3;q=0.9,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,",
}


async def parse_xhs(url: str) -> list[Message | MessageSegment | str] | None:
    if "xhslink" in url:
        url = await get_redirect(url, xhs_headers)
    pattern = r"(?:/explore/|/discovery/item/|source=note&noteId=)(\w+)"
    matched = re.search(pattern, url)
    if not matched:
        return None
    xhs_id = matched.group(1)
    parsed_url = urlparse(url)
    params = parse_qs(parsed_url.query)
    xsec_source = params.get("xsec_source", [None])[0] or "pc_feed"
    xsec_token = params.get("xsec_token", [None])[0]
    try:
        resp = await aiohttpx.get(
            f"https://www.xiaohongshu.com/explore/{xhs_id}?xsec_source={xsec_source}&xsec_token={xsec_token}",
            headers=xhs_headers,
            cookies=await get_xhscookies(),
        )
    except Exception as e:
        sv.logger.error(f"Error fetching Xiaohongshu data: {e}")
        return None
    if not resp.ok:
        sv.logger.error("Error fetching Xiaohongshu data")
        return None
    data = resp.text
    pattern = r"window.__INITIAL_STATE__=(.*?)</script>"
    matched = re.search(pattern, data)
    if not matched:
        sv.logger.error("Xiaohongshu cookies may be invalid")
        return None
    json_str = matched.group(1)
    json_str = json_str.replace("undefined", "null")
    json_obj = json.loads(json_str)
    try:
        note_data = json_obj["note"]["noteDetailMap"][xhs_id]["note"]
    except KeyError:
        sv.logger.error("Xiaohongshu cookies may be invalid")
        return None
    resource_type = note_data["type"]
    note_title = note_data["title"]
    note_desc = note_data["desc"]
    title_desc = f"{note_title}\n--------\n{note_desc}"
    img_urls = []
    video_url = ""
    if resource_type == "normal":
        image_list = note_data["imageList"]
        img_urls = [item["urlDefault"] for item in image_list]
        msg = [title_desc, f"笔记链接: {resp.url}"]
        for img_url in img_urls:
            msg.append(MessageSegment.image(img_url))
        return msg
    elif resource_type == "video":
        video_url = note_data["video"]["media"]["stream"]["h264"][0]["masterUrl"]
        msg = [title_desc, f"笔记链接: {resp.url}"]
        msg.append(MessageSegment.video(video_url))
        return msg
    else:
        sv.logger.error(
            "Unsupported Xiaohongshu resource type {}".format(resource_type)
        )
        return None

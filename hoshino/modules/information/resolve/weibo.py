from ..weibo.utils import (
    parse_mapp_weibo,
    parse_weibo_with_id,
)
from hoshino.util import send_segments,send
from .sv import sv

async def resolve_weibo(name: str, url: str, bid: str = None) -> bool:
    post = None
    if name == "mappweibo":
        post = await parse_mapp_weibo(url)
    elif bid:
        post = await parse_weibo_with_id(bid)
    if not post:
        sv.logger.error(f"{name} {url} parse error")
        return False
    post_message = await post.get_message(full=True)
    post_message = await post.save(post_message)
    if not post_message:
        sv.logger.error(f"{name} {url} save error")
        return False
    ms = post.render_message(post_message)
    if len(ms) >1:
        await send(ms[0])
        await send_segments(ms[1:])
    else:
        await send(ms)
    return True
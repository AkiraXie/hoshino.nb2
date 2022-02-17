"""
Author: AkiraXie
LastEditTime: 2021-05-16 18:07:32
LastEditors: AkiraXie
GitHub: https://github.com/AkiraXie
"""
from hoshino import Service, R, permission, scheduled_job, MessageSegment, Bot

video = R + "video/yincha.mp4"
videomsg = MessageSegment.video(f"file:///{video}")

sv = Service(
    "yincha", manage_perm=permission.SUPERUSER, visible=False, enable_on_default=False
)


@scheduled_job("cron", hour="15", minute="00", jitter=20, id="yincha")
async def _():
    await sv.broadcast(videomsg, "yincha", 0.2)


yinchacmd = sv.on_fullmatch(keywords={"饮茶", "yincha"})


@yinchacmd
async def _(bot: Bot):
    await yinchacmd.send(videomsg)

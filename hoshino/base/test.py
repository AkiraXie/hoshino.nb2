from nonebot.adapters.onebot.v11.message import MessageSegment as OneBotV11MessageSegment
from nonebot.adapters.onebot.v11.event import GroupMessageEvent as OneBotV11GroupMessageEvent
from hoshino.platform.ob11.types import Event
from hoshino.platform.ob11.event import get_event
from nonebot.adapters import Bot
from hoshino.util import get_bot_list, sucmd
from nonebot.matcher import matchers

test1 = sucmd("testgetbot", True)
test2 = sucmd("testmatchers", True)
test3 = sucmd("testevent", True)
test4 = sucmd("forward")


def get_matchers() -> list:
    return list(matchers.items())


@test1.handle()
async def _(bot: Bot):
    await test1.finish(str(get_bot_list()))


@test2.handle()
async def _(bot: Bot):
    await test2.finish(str(get_matchers()))


@test3.handle()
async def _(bot: Bot, event: Event):
    await test3.finish(get_event(event))


@test4.handle()
async def _(bot: Bot, event: OneBotV11GroupMessageEvent):
    ms = OneBotV11MessageSegment(
        "node",
        {
            "user_id": event.get_user_id(),
            "name": "test",
            "content": "testtest" + OneBotV11MessageSegment.face(233),
        },
    )
    await bot.send_group_forward_msg(group_id=event.group_id, messages=[ms])

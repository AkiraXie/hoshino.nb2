from hoshino.matcher import get_matchers
from nonebot.adapters.onebot.v11.message import MessageSegment
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from hoshino.event import Event, get_event
from hoshino import Bot, get_bot_list, sucmd

test1 = sucmd("testgetbot", True)
test2 = sucmd("testmatchers", True)
test3 = sucmd("testevent", True)
test4 = sucmd("forward")


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
async def _(bot: Bot, event: GroupMessageEvent):
    ms = MessageSegment(
        "node",
        {
            "user_id": event.get_user_id(),
            "name": "test",
            "content": "testtest" + MessageSegment.face(233),
        },
    )
    await bot.send_group_forward_msg(group_id=event.group_id, messages=[ms])

from nonebot.adapters import Bot
from nonebot.matcher import matchers

from hoshino.command import UniMessage
from hoshino.platform import send_group_forward, send_private_forward
from hoshino.platform.depends import GroupID, SenderID
from hoshino.platform.ob11.event import get_event
from hoshino.platform.ob11.types import Event
from hoshino.util import get_bot_list, sucmd

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
async def _(
    bot: Bot,
    group_id: int | None = GroupID(),
    user_id: int | None = SenderID(),
):
    messages = [UniMessage.text("testtest") + UniMessage.emoji("233")]
    if group_id is not None:
        await send_group_forward(
            bot,
            group_id,
            messages,
            user_id=user_id,
            nickname="test",
        )
    elif user_id is not None:
        await send_private_forward(
            bot,
            user_id,
            messages,
            node_user_id=user_id,
            nickname="test",
        )

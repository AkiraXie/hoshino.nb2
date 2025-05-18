from typing import Literal
from nonebot.adapters.onebot.v11 import Event, Adapter
from nonebot.adapters.onebot.v11.event import (
    MessageEvent,
    GroupMessageEvent,
    PrivateMessageEvent,
    LifecycleMetaEvent,
    NoticeEvent,
)
from typing_extensions import override


class GroupReactionEvent(NoticeEvent):
    """
    Lagrange GroupReactionEvent
    """

    group_id: int
    notice_type: Literal["reaction"]
    sub_type: Literal["add", "remove"]
    message_id: int
    operator_id: int
    code: str
    count: int

    @override
    def get_user_id(self) -> str:
        return str(self.operator_id)

    @override
    def get_session_id(self) -> str:
        return f"group_{self.group_id}_{self.operator_id}"

    @override
    def is_tome(self):
        return super().is_tome()

    def is_add(self) -> bool:
        return self.sub_type == "add"


Adapter.add_custom_model(GroupReactionEvent)


def get_event(event: Event) -> str:
    return str(event.__dict__)

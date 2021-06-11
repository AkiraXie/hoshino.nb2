'''
Author: AkiraXie
Date: 2021-01-29 23:48:51
LastEditors: AkiraXie
LastEditTime: 2021-06-09 01:57:24
Description: 
Github: http://github.com/AkiraXie/
'''
from nonebot.adapters.cqhttp.message import MessageSegment, Message
from typing import Any, Optional, Union, Mapping, Iterable


class MessageBuilder:
    """
    `MessageBuilder` 可以用于链式创建消息,`.message` 或者 `get_message()`可以获得创建后的消息，
    实现了 `MessageSegment` 的常见静态方法,可能会覆盖消息的方法，比如 `record()`,`video()`等不予支持。
    """

    def __init__(self, message: Union[str, None, Mapping, Iterable[Mapping],
                                      MessageSegment, Message, Any] = None) -> None:
        self.message = Message(message)

    def __add__(self, message):
        self.message+message
        return self

    def __iadd__(self, message):
        self.message.__iadd__(message)
        return self

    def __radd__(self, message):
        message+self.message
        return self

    def __str__(self) -> str:
        return f"<MessageBuilder, message:{str(self.message)}>"

    def append(self, obj: Union[str, MessageSegment]):
        self.message.append(obj)
        return self

    def extend(self, obj: Union[Message, Iterable[MessageSegment]]):
        self.message.extend(obj)
        return self

    def extract_plain_text(self) -> str:
        return self.message.extract_plain_text()

    def get_message(self) -> Message:
        return self.message

    def at(self, user_id: Union[int, str]):
        self.message+MessageSegment("at", {"qq": str(user_id)})
        return self

    def face(self, id_: int):
        self.message+MessageSegment("face", {"id": str(id_)})
        return self

    def image(self, file: str,
              type_: Optional[str] = None,
              cache: bool = True,
              proxy: bool = True,
              timeout: Optional[int] = None):
        self.message+MessageSegment(
            "image", {
                "file": file,
                "type": type_,
                "cache": cache,
                "proxy": proxy,
                "timeout": timeout
            })
        return self

    def text(self, text: str) -> "MessageSegment":
        self.message+MessageSegment("text", {"text": text})
        return self

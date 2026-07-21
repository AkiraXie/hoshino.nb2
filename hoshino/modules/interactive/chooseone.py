import random
import re

from nonebot.params import RegexMatched
from nonebot.rule import regex

from hoshino.command import UniMessage
from hoshino.service import Service

sv = Service("chooseone")

CHOICE_PATTERN = (
    r"^(?:选(?:择|一下|一个|一)?|choose|pick)\s*"
    r".+?\s*(?:还是|\s+or\s+)\s*"
    r".+[?？]?$"
)
PREFIX = re.compile(r"^(?:选(?:择|一下|一个|一)?|choose|pick)\s*", re.IGNORECASE)
SEPARATORS = re.compile(r"\s*还是\s*|\s+or\s+", re.IGNORECASE)

co = sv.on_message(
    rule=regex(CHOICE_PATTERN, flags=re.IGNORECASE),
    only_group=False,
    priority=2,
)


@co.handle()
async def _(match_result: re.Match[str] = RegexMatched()):
    rng = random.SystemRandom()
    text = match_result.group(0).strip().rstrip("?").rstrip("？")
    text = PREFIX.sub("", text, count=1)

    parts = SEPARATORS.split(text)
    choices = [p.strip() for p in parts if p.strip()]

    if len(choices) < 2:
        return

    msgs = ["让我看看选什么好呢："]
    idchoices = list(f"{i + 1}. {choice}" for i, choice in enumerate(choices))
    msgs.extend(idchoices)

    if rng.randint(0, 1000) <= 66:
        msgs.append('中大奖了，最终选择： "我全都要"')
    else:
        final = rng.randint(0, len(choices) - 1)
        msgs.append(f"最终选择: {choices[final]}")

    await UniMessage.text("\n".join(msgs)).send()

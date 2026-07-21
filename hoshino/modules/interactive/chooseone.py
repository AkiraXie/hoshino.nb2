import re
import random

from hoshino.command import AlconnaResult, UniMessage
from hoshino.service import Service

sv = Service("chooseone")

# 匹配：选A还是B / 选择A还是B / choose A or B / 选A or B
# 更通顺的语义：支持"选"、"选择"、"choose"、"pick"等前缀
SEPARATORS = re.compile(r"\s*还是\s*|\s+or\s+", re.IGNORECASE)

co = sv.on_regex(
    r"(?:选(?:择|一下|一个|一)?|choose|pick)\s*"
    r".+?\s*(?:还是|\s+or\s+)\s*"
    r".+[?？]?$",
    flags=re.IGNORECASE,
    only_group=False,
    priority=2,
)


@co.handle()
async def _(result: AlconnaResult):
    rng = random.SystemRandom()
    match_result = result.result.header_match.result
    text = match_result.group(0).strip().rstrip("?").rstrip("？")

    # Strip leading prefix (选/选择/choose/pick)
    text = re.sub(
        r"^(?:选(?:择|一下|一个|一)?\s*|(?:choose|pick)\s*)",
        "",
        text,
        flags=re.IGNORECASE,
    )

    parts = SEPARATORS.split(text)
    choices = [p.strip() for p in parts if p.strip()]

    if len(choices) < 2:
        return

    msgs = ["让我看看选什么好呢："]
    idchoices = list(f"{i + 1}. {choice}" for i, choice in enumerate(choices))
    msgs.extend(idchoices)

    if rng.randint(0, 1000) <= 66:
        msgs.append("中大奖了，最终选择： \"我全都要\"")
    else:
        final = rng.randint(0, len(choices) - 1)
        msgs.append(f"最终选择: {choices[final]}")

    await UniMessage.text("\n".join(msgs)).send()

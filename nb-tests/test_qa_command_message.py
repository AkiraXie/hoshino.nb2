"""QA command argument preservation tests."""

import pytest

from nonebot_plugin_alconna.uniseg import UniMessage


@pytest.mark.usefixtures("_nonebot_bootstrap")
@pytest.mark.asyncio
async def test_qa_command_argument_keeps_image_segments():
    from hoshino.modules.interactive import QA

    message = (
        UniMessage.text("问题你答答案")
        + UniMessage.image(url="https://example.com/answer.png")
        + UniMessage.text("尾部")
    )

    parsed = QA._split_question_and_answer(message)

    assert parsed is not None
    question, answer = parsed
    assert question == "问题"
    assert [segment.type for segment in answer] == ["text", "image", "text"]

    restored = await QA._parse_answer(answer.dump(json=True))
    assert [segment.type for segment in restored] == ["text", "image", "text"]

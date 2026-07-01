from io import BytesIO
from nonebot.typing import T_State
from nonebot.params import Depends
from .data import Question, Session
from hoshino.platform.ob11.permission import ADMIN
from hoshino.service import Service
from nonebot.adapters import Event
from nonebot.matcher import Matcher
from hoshino.command import UniMessage, uni_image
from hoshino.platform import (
    get_event_message,
    get_session_id,
)
from hoshino.platform.ob11.depends import GroupID, PlainText, SenderID
from hoshino.config import config
from hoshino.util.aiohttpx import get
from PIL import Image
from sqlalchemy import select

img_dir = config.static_dir / "img" / "QA"
img_dir.mkdir(parents=True, exist_ok=True)


async def _parse_answer(answer: str) -> UniMessage:
    return await UniMessage.generate(message=answer)


async def _finish_answer(answer: str) -> None:
    await (await _parse_answer(answer)).send()
    await ans.finish()


async def event_image_in_local(
    matcher: Matcher,
    event: Event,
    gid: int = GroupID(),
) -> tuple[str, str]:
    msg = get_event_message(event).copy()
    msgs = str(msg).split("你答", 1)
    if len(msgs) != 2:
        await matcher.finish()
    if len(msgs[0]) == 0 or len(msgs[1]) == 0:
        await matcher.finish()
    question, answer = msgs
    question = question.lstrip()
    answer = answer.lstrip()
    if answer == question:
        await matcher.finish()
    sid = get_session_id(event, "")
    answer_msg = await _parse_answer(answer)
    for i, seg in enumerate(answer_msg):
        if seg.type == "image":
            url = str(getattr(seg, "url", None) or seg.data.get("url", ""))
            url = url.replace("https://", "http://")
            img = await get(url, timeout=120, verify=False)
            im = Image.open(BytesIO(img.content))
            fmt = im.get_format_mimetype()
            ext = ""
            if fmt == "image/webp":
                ext = ".webp"
            elif fmt == "image/jpeg":
                ext = ".jpg"
            elif fmt == "image/png":
                ext = ".png"
            s = "{}-{}{}".format(sid, (url.split("/")[-2]).split("-")[-1], ext)
            f = img_dir / s
            f.write_bytes(img.content)
            answer_msg[i] = uni_image(f)
    return (question, str(answer_msg))


set_qa_dep = Depends(event_image_in_local)


async def answer_qa_rule(
    gid: int = GroupID(),
    uid: int = SenderID(),
    text: str = PlainText(),
    state: T_State | None = None,
) -> bool:
    gid = gid or 0
    question = text.lower()
    with Session() as session:
        stmt = select(Question).where(
            Question.question.ilike(question),
            Question.group == gid,
            Question.user == uid,
        )
        answer = session.execute(stmt).scalar_one_or_none()

        if not answer:
            stmt = select(Question).where(
                Question.question.ilike(question),
                Question.group == gid,
                Question.user == 0,
            )
            answer = session.execute(stmt).scalar_one_or_none()

        if answer and state is not None:
            state["answer"] = answer.answer
            return True
        elif answer:
            return True
        else:
            return False


sv = Service("QA")

group_ques = sv.on_command("有人问", aliases={"大家问"}, permission=ADMIN)
person_ques = sv.on_command("我问", only_group=False)
del_gqa = sv.on_command("删除有人问", aliases={"删除大家问"}, permission=ADMIN)
del_qa = sv.on_command("不要回答", aliases={"不再回答"}, only_group=False)
lookqa = sv.on_command("看看我问", aliases={"查看我问"}, only_group=False)
lookgqa = sv.on_command("看看有人问", aliases={"看看大家问", "查看有人问"})
ans = sv.on_message(only_group=False, rule=answer_qa_rule, priority=5, log=True)
del_pqa = sv.on_command("删除我问", permission=ADMIN)
del_allqa = sv.on_command("删除所有问答", aliases={"delallqa"}, permission=ADMIN)


@group_ques.handle()
async def _(msg: tuple[str, str] = set_qa_dep, gid: int = GroupID()):
    question, answer = msg
    with Session() as session:
        stmt = select(Question).where(
            Question.question == question,
            Question.group == gid,
            Question.user == 0,
        )
        obj = session.execute(stmt).scalar_one_or_none()
        if obj:
            obj.answer = answer
        else:
            obj = Question(
                question=question, answer=answer, group=gid, user=0
            )
            session.add(obj)
        session.commit()
    await group_ques.finish(f"好的我记住{question}了")


@person_ques.handle()
async def _(msg: tuple[str, str] = set_qa_dep, gid: int = GroupID(), uid: int = SenderID()):
    question, answer = msg
    gid = gid or 0
    with Session() as session:
        stmt = select(Question).where(
            Question.question == question,
            Question.group == gid,
            Question.user == uid,
        )
        obj = session.execute(stmt).scalar_one_or_none()
        if obj:
            obj.answer = answer
        else:
            obj = Question(question=question, answer=answer, group=gid, user=uid)
            session.add(obj)
        session.commit()
    await person_ques.finish(f"好的我记住{question}了")


@del_gqa.handle()
async def _(text: str = PlainText(), gid: int = GroupID()):
    lquestion = text.lower()
    with Session() as session:
        stmt = select(Question).where(
            Question.question.ilike(lquestion),
            Question.group == gid,
            Question.user == 0,
        )
        questions = session.execute(stmt).scalars().all()
        for q in questions:
            session.delete(q)
        num = len(questions)
        session.commit()
    if num == 0:
        await del_gqa.finish('我不记得"{}"这个问题'.format(text))
    else:
        await del_gqa.finish('我不再回答"{}"了'.format(text))


@del_qa.handle()
async def _(text: str = PlainText(), gid: int = GroupID(), uid: int = SenderID()):
    lquestion = text.lower()
    gid = gid or 0
    with Session() as session:
        stmt = select(Question).where(
            Question.question.ilike(lquestion),
            Question.group == gid,
            Question.user == uid,
        )
        questions = session.execute(stmt).scalars().all()
        for q in questions:
            session.delete(q)
        num = len(questions)
        session.commit()
    if num == 0:
        await del_qa.finish('我不记得"{}"这个问题'.format(text))
    else:
        await del_qa.finish('我不再回答"{}"了'.format(text))


async def parse_question(state: T_State, text: str = PlainText()):
    state["question"] = text


async def parse_sin_qq(event: Event, state: T_State):
    for m in get_event_message(event, []):
        if m.type == "at" and m.data["qq"] != "all":
            state["user_id"] = int(m.data["qq"])
            break
        elif m.type == "text" and m.data["text"].isdigit():
            state["user_id"] = int(m.data["text"])
            break


@del_pqa.got("question", "请输入要删除的问题")
async def _(state: T_State, text: str = PlainText()):
    state["question"] = text


@del_pqa.got("user_id", "请输入要删除问题的id,支持at")
async def _(event: Event, state: T_State):
    await parse_sin_qq(event, state)


@del_pqa.handle()
async def _(state: T_State, gid: int = GroupID()):
    if not state.get("user_id", None):
        return
    lquestion = state["question"].lower()
    with Session() as session:
        stmt = select(Question).where(
            Question.question.ilike(lquestion),
            Question.group == gid,
            Question.user == state["user_id"],
        )
        questions = session.execute(stmt).scalars().all()
        for q in questions:
            session.delete(q)
        num = len(questions)
        session.commit()
    if num == 0:
        await del_pqa.finish('我不记得"{}"这个问题'.format(state["question"]))
    else:
        await del_pqa.finish(
            '我不再回答"{}"这个问题了'.format(state["question"])
        )


@lookqa.handle()
async def _(gid: int = GroupID(), uid: int = SenderID()):
    gid = gid or 0
    with Session() as session:
        stmt = select(Question).where(Question.group == gid, Question.user == uid)
        result = session.execute(stmt).scalars().all()
        msg = [res.question for res in result]
    await lookqa.finish("您设置的问题有: " + " | ".join(msg), call_header=True)


@lookgqa.handle()
async def _(gid: int = GroupID()):
    with Session() as session:
        stmt = select(Question).where(Question.group == gid, Question.user == 0)
        result = session.execute(stmt).scalars().all()
        msg = [res.question for res in result]
    await lookgqa.finish(
        '该群设置的"有人问"有: ' + " | ".join(msg), call_header=True
    )


@ans.handle()
async def _(state: T_State):
    if answer := state["answer"]:
        await _finish_answer(answer)


@del_allqa.handle()
async def _(gid: int = GroupID()):
    with Session() as session:
        stmt = select(Question).where(Question.group == gid)
        questions = session.execute(stmt).scalars().all()
        for q in questions:
            session.delete(q)
        num = len(questions)
        session.commit()
    if num == 0:
        await del_allqa.finish("该群没有设置任何问答")
    else:
        await del_allqa.finish("已删除该群的所有问答")

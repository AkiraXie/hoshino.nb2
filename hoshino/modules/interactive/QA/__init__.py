from io import BytesIO
from nonebot.typing import T_State
from nonebot.params import Depends
from .data import Question
from hoshino.permission import ADMIN
from hoshino import Service, Bot, Event, Message, MessageSegment, Matcher
from hoshino.event import MessageEvent
from hoshino.config import config
from peewee import fn
from hoshino.util.aiohttpx import get
from PIL import Image

img_dir = config.static_dir / "img" / "QA"
img_dir.mkdir(parents=True, exist_ok=True)


async def event_image_in_local(
    matcher: Matcher, event: MessageEvent
) -> tuple[str, str]:
    msg = event.message.copy()
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
    sid = event.get_session_id()
    answer_msg = Message(answer)
    for i, s in enumerate(answer_msg):
        if s.type == "image":
            url = s.data.get("file", s.data.get("url"))
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
            answer_msg[i] = MessageSegment.image(f)
    return (question, str(answer_msg))


set_qa_dep = Depends(event_image_in_local)


async def answer_qa_rule(event: Event, state: T_State):
    gid = event.group_id if "group_id" in event.__dict__ else 0
    uid = event.user_id
    msg = str(event.get_message())
    question = msg.lower()
    answer = Question.get_or_none(
        fn.Lower(Question.question) == question, group=gid, user=uid
    ) or Question.get_or_none(
        fn.Lower(Question.question) == question, group=gid, user=0
    )
    if answer:
        state["answer"] = answer.answer
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
async def _(event: Event, msg: tuple[str, str] = set_qa_dep):
    question, answer = msg
    Question.replace(
        question=question, answer=answer, group=event.group_id, user=0
    ).execute()
    await group_ques.finish(Message(f"好的我记住{question}了"))


@person_ques.handle()
async def _(event: Event, msg: tuple[str, str] = set_qa_dep):
    question, answer = msg
    Question.replace(
        question=question,
        answer=answer,
        group=event.group_id if "group_id" in event.__dict__ else 0,
        user=event.user_id,
    ).execute()
    await person_ques.finish(Message(f"好的我记住{question}了"))


@del_gqa.handle()
async def _(bot: Bot, event: Event):
    question = str(event.get_message())
    lquestion = question.lower()
    num = (
        Question.delete()
        .where(
            fn.Lower(Question.question) == lquestion,
            Question.group == event.group_id,
            Question.user == 0,
        )
        .execute()
    )
    if num == 0:
        await del_gqa.finish(Message('我不记得"{}"这个问题'.format(question)))
    else:
        await del_gqa.finish(Message('我不再回答"{}"了'.format(question)))


@del_qa.handle()
async def _(bot: Bot, event: Event):
    question = str(event.get_message())
    lquestion = question.lower()
    gid = event.group_id if "group_id" in event.__dict__ else 0
    num = (
        Question.delete()
        .where(
            fn.Lower(Question.question) == lquestion,
            Question.group == gid,
            Question.user == event.user_id,
        )
        .execute()
    )
    if num == 0:
        await del_qa.finish(Message('我不记得"{}"这个问题'.format(question)))
    else:
        await del_qa.finish(Message('我不再回答"{}"了'.format(question)))


async def parse_question(state: T_State, event: Event):
    state["question"] = str(event.get_message())


async def parse_sin_qq(bot: Bot, event: Event, state: T_State):
    for m in event.get_message():
        if m.type == "at" and m.data["qq"] != "all":
            state["user_id"] = int(m.data["qq"])
            break
        elif m.type == "text" and m.data["text"].isdigit():
            state["user_id"] = int(m.data["text"])
            break


@del_pqa.got("question", "请输入要删除的问题", args_parser=parse_question)
@del_pqa.got("user_id", "请输入要删除问题的id,支持at", args_parser=parse_sin_qq)
async def _(bot: Bot, event: Event, state: T_State):
    if not state.get("user_id", None):
        return
    state["gid"] = event.group_id
    lquestion = state["question"].lower()
    num = (
        Question.delete()
        .where(
            fn.Lower(Question.question) == lquestion,
            Question.group == state["gid"],
            Question.user == state["user_id"],
        )
        .execute()
    )
    if num == 0:
        await del_pqa.finish(Message('我不记得"{}"这个问题'.format(state["question"])))
    else:
        await del_pqa.finish(
            Message('我不再回答"{}"这个问题了'.format(state["question"]))
        )


@lookqa.handle()
async def _(bot: Bot, event: Event):
    uid = event.user_id
    gid = event.group_id if "group_id" in event.__dict__ else 0
    result = Question.select(Question.question).where(
        Question.group == gid, Question.user == uid
    )
    msg = []
    for res in result:
        msg.append(res.question)
    await lookqa.finish(Message("您设置的问题有: " + " | ".join(msg)), at_sender=True)


@lookgqa.handle()
async def _(bot: Bot, event: Event):
    uid = 0
    gid = event.group_id
    result = Question.select(Question.question).where(
        Question.group == gid, Question.user == uid
    )
    msg = []
    for res in result:
        msg.append(res.question)
    await lookgqa.finish(
        Message('该群设置的"有人问"有: ' + " | ".join(msg)), at_sender=True
    )


@ans.handle()
async def _(state: T_State):
    if answer := state["answer"]:
        msg = Message(answer)
        await ans.finish(msg)


@del_allqa.handle()
async def _(event: Event):
    gid = event.group_id
    num = Question.delete().where(Question.group == gid).execute()
    if num == 0:
        await del_allqa.finish(Message("该群没有设置任何问答"))
    else:
        await del_allqa.finish(Message("已删除该群的所有问答"))

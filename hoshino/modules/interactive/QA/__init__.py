from json import JSONDecodeError

from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.typing import T_State
from sqlalchemy import select

from hoshino.command import UniMessage
from hoshino.platform import (
    get_event_message,
)
from hoshino.platform.depends import GroupID, ParamMessage, ParamText, PlainText, SenderID
from hoshino.platform.permission import ADMIN
from hoshino.service import Service

from .data import Question, Session


async def _parse_answer(answer: str) -> UniMessage:
    try:
        return UniMessage.load(answer)
    except (KeyError, TypeError, ValueError, JSONDecodeError):
        return UniMessage.text(answer)


async def _finish_answer(answer: str) -> None:
    await (await _parse_answer(answer)).send()
    await ans.finish()


def _split_question_and_answer(message: UniMessage) -> tuple[str, UniMessage] | None:
    question_parts: list[str] = []
    answer = UniMessage()
    found_separator = False

    for segment in message:
        if not found_separator and segment.type == "text":
            question, separator, remaining = segment.text.partition("你答")
            question_parts.append(question)
            if separator:
                found_separator = True
                if remaining:
                    answer.append(UniMessage.text(remaining)[0])
            continue
        if found_separator:
            answer.append(segment)
        else:
            question_parts.append(str(segment))

    question = "".join(question_parts).lstrip()
    if not found_separator or not question or not answer:
        return None

    if answer[0].type == "text":
        answer[0].text = answer[0].text.lstrip()
        if not answer[0].text:
            answer.pop(0)
    if not answer or answer.extract_plain_text() == question:
        return None
    return question, answer


async def parse_qa(
    matcher: Matcher,
    msg: UniMessage = ParamMessage(),
) -> tuple[str, str]:
    parsed = _split_question_and_answer(msg)
    if parsed is None:
        await matcher.finish()
    question, answer_msg = parsed
    return question, answer_msg.dump(json=True)


set_qa_dep = Depends(parse_qa)


async def answer_qa_rule(
    state: T_State,
    gid: int = GroupID(),
    uid: int = SenderID(),
    text: str = PlainText(),
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

        if answer:
            state["answer"] = answer.answer
            return True
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
            obj = Question(question=question, answer=answer, group=gid, user=0)
            session.add(obj)
        session.commit()
    await group_ques.finish(f"好的我记住'{question}'了")


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
    await person_ques.finish(f"好的我记住'{question}'了")


@del_gqa.handle()
async def _(text: str = ParamText(), gid: int = GroupID()):
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
        await del_gqa.finish(f'我不记得"{text}"这个问题')
    else:
        await del_gqa.finish(f'我不再回答"{text}"了')


@del_qa.handle()
async def _(text: str = ParamText(), gid: int = GroupID(), uid: int = SenderID()):
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
        await del_qa.finish(f'我不记得"{text}"这个问题')
    else:
        await del_qa.finish(f'我不再回答"{text}"了')


async def parse_question(state: T_State, text: str = PlainText()):
    state["question"] = text


async def parse_single_qq(event: Event, state: T_State):
    for m in get_event_message(event, []):
        if m.type == "at" and m.data["qq"] != "all":
            state["user_id"] = int(m.data["qq"])
            break
        if m.type == "text" and m.data["text"].isdigit():
            state["user_id"] = int(m.data["text"])
            break


@del_pqa.got("question", "请输入要删除的问题")
async def _(state: T_State, text: str = PlainText()):
    state["question"] = text


@del_pqa.got("user_id", "请输入要删除问题的id,支持at")
async def _(event: Event, state: T_State):
    await parse_single_qq(event, state)


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
        await del_pqa.finish(f'我不记得"{state["question"]}"这个问题')
    else:
        await del_pqa.finish(f'我不再回答"{state["question"]}"这个问题了')


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
    await lookgqa.finish('该群设置的"有人问"有: ' + " | ".join(msg), call_header=True)


@ans.handle()
async def _(state: T_State):
    if answer := state.get("answer"):
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

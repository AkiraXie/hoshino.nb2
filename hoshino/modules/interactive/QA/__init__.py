"""
Author: AkiraXie
Date: 2021-02-02 23:57:37
LastEditors: AkiraXie
LastEditTime: 2021-04-07 22:07:05
Description: 
Github: http://github.com/AkiraXie/
"""
from nonebot.typing import T_State
import re
from .data import Question
from hoshino.permission import ADMIN
from hoshino import Service, Bot, Event, Message
from peewee import fn

sv = Service("QA")

group_ques = sv.on_command("有人问", aliases={"大家问"}, permission=ADMIN)
person_ques = sv.on_command("我问", only_group=False)
del_gqa = sv.on_command("删除有人问", aliases={"删除大家问"}, permission=ADMIN)
del_qa = sv.on_command("不要回答", aliases={"不再回答"}, only_group=False)
lookqa = sv.on_command("看看我问", aliases={"查看我问"}, only_group=False)
lookgqa = sv.on_command("看看有人问", aliases={"看看大家问", "查看有人问"})
ans = sv.on_message(only_group=False, priority=5)
del_pqa = sv.on_command("删除我问", permission=ADMIN)


@group_ques.handle()
async def _(bot: Bot, event: Event):
    msg = event.raw_message
    msg = re.sub(r".*(有人问|大家问)", "", msg, 1)
    msgs = msg.split("你答", 1)
    if len(msgs) != 2:
        await group_ques.finish()
    if len(msgs[0]) == 0 or len(msgs[1]) == 0:
        await group_ques.finish("提问和回答都不可以是空!", at_sender=True)
    question, answer = msgs
    question = question.lstrip()
    Question.replace(
        question=question, answer=answer, group=event.group_id, user=0
    ).execute()
    await group_ques.finish(Message(f"好的我记住{question}了"))


@person_ques.handle()
async def _(bot: Bot, event: Event):
    msg = event.raw_message
    msg = re.sub(r".*我问", "", msg, 1)
    msgs = msg.split("你答", 1)
    if len(msgs) != 2:
        await person_ques.finish()
    if len(msgs[0]) == 0 or len(msgs[1]) == 0:
        await person_ques.finish("提问和回答都不可以是空!", at_sender=True)
    question, answer = msgs
    question = question.lstrip()
    Question.replace(
        question=question,
        answer=answer,
        group=event.group_id if "group_id" in event.__dict__ else 0,
        user=event.user_id,
    ).execute()
    await person_ques.finish(Message(f"好的我记住{question}了"))


@del_gqa.handle()
async def _(bot: Bot, event: Event):
    msg = event.raw_message
    question = re.sub(r".*删除(有人问|大家问)", "", msg, 1)
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
    question = re.sub(r".*不[要再]回答", "", event.raw_message, 1)
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


async def parse_question(bot: Bot, event: Event, state: T_State):
    state["question"] = event.raw_message.strip()


async def parse_sin_qq(bot: Bot, event: Event, state: T_State):
    for m in event.get_message():
        if m.type == "at" and m.data["qq"] != "all":
            state["user_id"] = int(m.data["qq"])
            break
        elif m.type == "text" and m.data["text"].isdigit():
            state["user_id"] = int(m.data["text"])
            break


@del_pqa.got("question", "请输入要删除的问题", parse_question)
@del_pqa.got("user_id", "请输入要删除问题的id，支持at", parse_sin_qq)
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
        await del_pqa.finish(Message('我不再回答"{}"这个问题了'.format(state["question"])))


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
    await lookgqa.finish(Message('该群设置的"有人问"有: ' + " | ".join(msg)), at_sender=True)


@ans.handle()
async def _(bot: Bot, event: Event):
    gid = event.group_id if "group_id" in event.__dict__ else 0
    uid = event.user_id
    question = event.raw_message.lower()
    answer = Question.get_or_none(
        fn.Lower(Question.question) == question, group=gid, user=uid
    ) or Question.get_or_none(
        fn.Lower(Question.question) == question, group=gid, user=0
    )
    if answer:
        await ans.finish(Message(answer.answer))

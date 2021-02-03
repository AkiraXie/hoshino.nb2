'''
Author: AkiraXie
Date: 2021-02-02 23:57:37
LastEditors: AkiraXie
LastEditTime: 2021-02-03 21:14:55
Description: 
Github: http://github.com/AkiraXie/
'''
from nonebot.typing import T_State
from .data import Question
from hoshino.permission import ADMIN
from argparse import Namespace
from hoshino import Service, Bot, Event, Message
from nonebot.rule import ArgumentParser


sv = Service('QA')

group_ques = sv.on_command('有人问', aliases={'大家问'}, permission=ADMIN)
person_ques = sv.on_command('我问', only_group=False)
del_gqa = sv.on_command('删除有人问', aliases={'删除大家问'}, permission=ADMIN)
del_qa = sv.on_command('不要回答', aliases={'不再回答'}, only_group=False)
lookqa = sv.on_command('看看我问', aliases={'查看我问'}, only_group=False)
lookgqa = sv.on_command('看看有人问', aliases={'看看大家问', '查看有人问'})
ans = sv.on_message(only_group=False, priority=5)
parser = ArgumentParser()
parser.add_argument('question', type=str)
parser.add_argument('user_id', type=int)
del_pqa = sv.on_shell_command('删除我问', parser=parser, permission=ADMIN)


@group_ques.handle()
async def _(bot: Bot, event: Event):
    msg = str(event.get_message())
    msgs = msg.split('你答', 1)
    if len(msgs) != 2:
        await group_ques.finish()
    if len(msgs[0]) == 0 or len(msgs[1]) == 0:
        await group_ques.finish('提问和回答都不可以是空!', at_sender=True)
    question, answer = msgs
    Question.replace(
        question=question,
        answer=answer,
        group=event.group_id
    ).execute()
    await group_ques.finish('好的我记住了')


@person_ques.handle()
async def _(bot: Bot, event: Event):
    msg = str(event.get_message())
    msgs = msg.split('你答', 1)
    if len(msgs) != 2:
        await group_ques.finish()
    if len(msgs[0]) == 0 or len(msgs[1]) == 0:
        await person_ques.finish('提问和回答都不可以是空!', at_sender=True)
    question, answer = msgs
    Question.replace(
        question=question,
        answer=answer,
        group=event.group_id if 'group_id' in event.__dict__ else 0,
        user=event.user_id
    ).execute()
    await person_ques.finish('好的我记住了')





@del_gqa.handle()
async def _(bot: Bot, event: Event):
    question = str(event.get_message())
    num = Question.delete().where(
        Question.question == question,
        Question.group == event.group_id,
        Question.user == 0
    ).execute()
    if num == 0:
        await del_gqa.finish('我不记得"{}"这个问题'.format(question))
    else:
        await del_gqa.finish('我不再回答"{}"这个问题了'.format(question))


@del_qa.handle()
async def _(bot: Bot, event: Event):
    question = str(event.get_message())
    gid=event.group_id if 'group_id' in event.__dict__ else 0
    num = Question.delete().where(
        Question.question == question,
        Question.group == gid,
        Question.user == event.user_id
    ).execute()
    if num == 0:
        await del_qa.finish('我不记得"{}"这个问题'.format(question))
    else:
        await del_qa.finish('我不再回答"{}"这个问题了'.format(question))


@del_pqa.handle()
async def _(bot: Bot, event: Event, state: T_State):
    state['gid'] = event.group_id
    if isinstance(state['args'],Namespace):
        state.update(**state['args'].__dict__)


@del_pqa.got('question', '请输入要删除的问题')
@del_pqa.got('user_id', '请输入要删除的人的id,在群聊中支持at哦')
async def _(bot: Bot, event: Event, state: T_State):
    for m in event.get_message():
        if m.type == 'at' and m.data['qq'] != 'all':
            state['user_id'] = int(m.data['qq'])
            break
        elif m.type == 'text' and m.data['text'].isdigit():
            state['user_id'] = (int(m.data['text']))
            break
    num = Question.delete().where(
        Question.question == state['question'],
        Question.group == state['gid'],
        Question.user == state['user_id']
    ).execute()
    if num == 0:
        await del_pqa.finish('我不记得"{}"这个问题'.format(state['question']))
    else:
        await del_pqa.finish('我不再回答"{}"这个问题了'.format(state['question']))


@lookqa.handle()
async def _(bot: Bot, event: Event):
    uid = event.user_id
    gid = event.group_id if 'group_id' in event.__dict__ else 0
    result = Question.select(Question.question).where(
        Question.group == gid, Question.user == uid)
    msg = []
    for res in result:
        msg.append(res.question)
    await lookqa.finish(Message('您设置的问题有: '+' | '.join(msg)), at_sender=True)


@lookgqa.handle()
async def _(bot: Bot, event: Event):
    uid = 0
    gid = event.group_id
    result = Question.select(Question.question).where(
        Question.group == gid, Question.user == uid)
    msg = []
    for res in result:
        msg.append(res.question)
    await lookgqa.finish(Message('该群设置的"有人问"有: '+' | '.join(msg)), at_sender=True)


@ans.handle()
async def _(bot: Bot, event: Event):
    gid = event.group_id if 'group_id' in event.__dict__ else 0
    uid = event.user_id
    question = str(event.get_message())
    answer =  Question.get_or_none(group=gid, user=uid,question=question) or Question.get_or_none(group=gid, user=0,question=question)
    if answer:
        await ans.finish(Message(answer.answer))

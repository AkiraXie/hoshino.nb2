'''
Author: AkiraXie
Date: 2021-02-09 23:34:47
LastEditors: AkiraXie
LastEditTime: 2021-03-16 22:53:09
Description: 
Github: http://github.com/AkiraXie/
'''
import asyncio
from hoshino.typing import List, T_State
from hoshino import Service, aiohttpx, Bot, Event, scheduled_job, Message, sucmd
from hoshino.util import text2Seg,get_bitly_url
from hoshino.rule import ArgumentParser
from .data import Rss, Rssdata, BASE_URL, pw,timezone
sv = Service('rss', enable_on_default=False)
parser = ArgumentParser()
parser.add_argument('name')
parser.add_argument('-u', '--url', type=str)
parser.add_argument('-r', '--rsshub', action='store_true')


def infos2pic(infos: List[dict]) -> str:
    texts = []
    for info in infos:
        text = f"标题: {info['标题']}\n时间: {info['时间']}\n======"
        texts.append(text)
    texts = '\n'.join(texts)
    return str(text2Seg(texts))


def info2pic(info: dict) -> str:
    text = f"标题: {info['标题']}\n\n正文:\n{info['正文']}\n时间: {info['时间']}"
    return str(text2Seg(text))


addrss = sv.on_shell_command('添加订阅', aliases=('addrss', '增加订阅'), parser=parser)


@addrss.handle()
async def _(bot: Bot, event: Event, state: T_State):
    args = state['args']
    name = args.name
    if not args.url:
        ret = Rssdata.get_or_none(name=name)
        if ret:
            url = ret.url
        else:
            await addrss.finish(f'订阅{name}不存在，请后跟 -u 路由 重新输入')
    else:
        url: str = BASE_URL+args.url.lstrip('/') if args.rsshub else args.url
    if r'/twitter/' in url.lower():
        await addrss.finish('推特路由请用 添加推特')
    try:
        stats = await aiohttpx.head(url, timeout=5, allow_redirects=True)
    except Exception as e:
        sv.logger.exception(e)
        await addrss.finish('请求路由失败,请稍后再试')
    if stats.status_code != 200:
        await addrss.finish('请求路由失败,请检查路由状态')
    rss = await Rss.new(url, 1)
    if not rss.has_entries:
        await addrss.finish('暂不支持该RSS')
    try:
        Rssdata.replace(url=rss.url, name=name,
                        group=event.group_id, date=rss.last_update).execute()
    except Exception as e:
        sv.logger.exception(e)
        await addrss.finish('订阅添加失败')
    await addrss.finish(f'订阅 {name} 添加成功')

delrss = sv.on_command('删除订阅', aliases=('delrss', '取消订阅'))


@delrss.handle()
async def del_rss(bot: Bot, event: Event, state: T_State):
    name = event.get_plaintext().strip()
    try:
        Rssdata.delete().where(Rssdata.name == name, Rssdata.group ==
                               event.group_id).execute()
    except Exception as e:
        sv.logger.exception(e)
        await delrss.finish('删除订阅失败')
    await delrss.finish(f'删除订阅{name}成功')

lookrss = sv.on_command('订阅列表', aliases=('查看本群订阅',))


@lookrss.handle()
async def lookrsslist(bot: Bot, event: Event, state: T_State):
    try:
        res = Rssdata.select(Rssdata.url, Rssdata.name).where(Rssdata.group ==
                                                              event.group_id,)
        reslen = len(res)
        for i in range(0, reslen, 5):
            j = min(reslen, i+5)
            if i == 0:
                msg = [f'本群{reslen}个订阅如下:']
            else:
                msg = []
            for ij in range(i, j):
                r = res[ij]
                rss = await Rss.new(r.url, 1)
                msg.append(f'订阅标题:{r.name}\n订阅链接:{rss.link}\n=====')
            await lookrss.send(Message('\n'.join(msg)))
    except Exception as e:
        sv.logger.exception(e)
        await lookrss.finish('查询订阅列表失败')

parser1 = ArgumentParser()
parser1.add_argument('name')
parser1.add_argument('-l', '--limit', default=5, type=int)

queryrss = sv.on_shell_command('看订阅', aliases=('查订阅', '查看订阅'), parser=parser1)


@queryrss.handle()
async def _(bot: Bot, event: Event, state: T_State):
    args = state['args']
    limit = args.limit
    name = args.name
    try:
        res = Rssdata.select(Rssdata.url).where(Rssdata.name == name, Rssdata.group ==
                                                event.group_id)
        r = res[0]
        rss = await Rss.new(r.url, limit)
        infos = await rss.get_all_entry_info()
    except Exception as e:
        sv.logger.exception(e)
        await queryrss.finish(f'查订阅{name}失败')
    msg = [f'{name}的最近记录:']
    msg.append(infos2pic(infos))
    msg.append('详情可看: '+rss.link)
    await queryrss.finish(Message('\n'.join(msg)))


@scheduled_job('interval', minutes=3, jitter=20, id='推送rss')
async def push_rss():
    glist = await sv.get_enable_groups()
    for gid in glist.keys():
        for bot in glist[gid]:
            res = Rssdata.select(Rssdata.url, Rssdata.name,
                                 Rssdata.date).where(Rssdata.group == gid)
            for r in res:
                flag = r'/twitter/' in r.url.lower()
                rss = await Rss.new(r.url)
                if not (rss.has_entries):
                    continue
                await asyncio.sleep(0.5)
                newinfos = await rss.get_interval_entry_info(r.date)
                if not newinfos:
                    continue
                for newinfo in newinfos:
                    msg = [f'{r.name} 更新啦！']
                    if not flag:
                        msg.append(info2pic(newinfo))
                        msg.append(f'{newinfo["链接"]}')
                    else:
                        infostr = f"正文:\n{newinfo['正文']}\n时间: {newinfo['时间']}"
                        msg.append(infostr)
                        msg.append(f'{await get_bitly_url(newinfo["链接"])}')
                    msg.extend(newinfo['图片'])
                    Rssdata.update(date=rss.last_update).where(
                        Rssdata.group == gid, Rssdata.name == r.name, Rssdata.url == r.url).execute()
                    await bot.send_group_msg(message=Message('\n'.join(msg)), group_id=gid)
                    if videos := newinfo['视频']:
                        for v in videos:
                            await bot.send_group_msg(message=v, group_id=gid)

querynewrss = sv.on_command('看最新订阅', aliases=('查最新订阅', '查看最新订阅','看最新'))


@querynewrss.handle()
async def _(bot: Bot, event: Event, state: T_State):
    name = event.get_plaintext().strip()
    res = Rssdata.select(Rssdata.url).where(Rssdata.name == name, Rssdata.group ==
                                            event.group_id)
    r = res[0]
    rss = await Rss.new(r.url, 1)
    newinfo = await rss.get_new_entry_info()
    msg = [f'{name} 最新消息']
    if not r'/twitter/' in r.url.lower():
        msg.append(info2pic(newinfo))
        msg.append(f'{newinfo["链接"]}')
    else:
        infostr = f"正文:\n{newinfo['正文']}\n时间: {newinfo['时间']}"
        msg.append(infostr)
        msg.append(f'{await get_bitly_url(newinfo["链接"])}')
    msg.extend(newinfo['图片'])
    await querynewrss.send(Message('\n'.join(msg)))
    if videos := newinfo['视频']:
        for v in videos:
            await querynewrss.send(v)


updaterss = sucmd('更新rss')


@updaterss.handle()
async def _(bot: Bot, event: Event, state: T_State):
    Rssdata.update(url=pw.fn.replace(
        Rssdata.url, r'rsshub.akiraxie.me', r'rsshub.akiraxie.cc')).execute()
    await updaterss.finish('update ok')

parser2 = ArgumentParser()
parser2.add_argument('-n', '--name', type=str)
parser2.add_argument('id')
addtwi = sv.on_shell_command(
    '添加推特', aliases={'订阅推特', '添加twitter'}, parser=parser2)


@addtwi
async def _(bot: Bot, event: Event, state: T_State):
    args = state['args']
    id = args.id.lstrip('@')
    name = id if not args.name else args.name
    url = BASE_URL+f'twitter/user/{id}/excludeReplies=1&readable=1'
    try:
        stats = await aiohttpx.head(url, timeout=5, allow_redirects=True)
    except Exception as e:
        sv.logger.exception(e)
        await addtwi.finish('请求推特路由失败,请稍后再试')
    if stats.status_code != 200:
        await addtwi.finish('请求推特路由失败,请检查路由状态')
    rss = await Rss.new(url, 1)
    try:
        Rssdata.replace(url=rss.url, name=name,
                        group=event.group_id, date=rss.last_update).execute()
    except Exception as e:
        sv.logger.exception(e)
        await addtwi.finish('推特添加失败')
    await addtwi.finish(f'推特 {name}(@{id}) 添加成功')

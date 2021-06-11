'''
Author: AkiraXie
Date: 2021-02-11 00:00:55
LastEditors: AkiraXie
LastEditTime: 2021-04-15 15:10:41
Description: 
Github: http://github.com/AkiraXie/
'''
from hoshino.service import MatcherWrapper
from hoshino import Service, Bot, scheduled_job, T_State
from hoshino.rule import ArgumentParser
from .spider import BaseSpider, BiliSpider, SonetSpider

svtw = Service('pcr-news-tw', enable_on_default=False)
svbl = Service('pcr-news-bili', enable_on_default=False)


async def news_poller(spider: BaseSpider, sv: Service, TAG):
    if not spider.item_cache:
        await spider.get_update()
        sv.logger.info(f'{TAG}新闻缓存为空，已加载至最新')
        return
    news = await spider.get_update()
    if not news:
        sv.logger.info(f'未检索到{TAG}新闻更新')
        return
    sv.logger.info(f'检索到{len(news)}条{TAG}新闻更新！')
    await sv.broadcast(await spider.format_items(news), TAG, interval_time=0.5)


@scheduled_job('interval', id='推送新闻', minutes=5, jitter=20)
async def biso_news_poller():
    await news_poller(SonetSpider, svtw, '台服官网')
    await news_poller(BiliSpider, svbl, 'B服官网')


async def send_news(matcher: MatcherWrapper, spider: BaseSpider, max_num=8):
    if not spider.item_cache:
        await spider.get_update()
    news = spider.item_cache
    news = news[:min(max_num, len(news))]
    await matcher.send(await spider.format_items(news), at_sender=True)

parser = ArgumentParser()
parser.add_argument('-l', '--limit', default=8, type=int)
twnews = svtw.on_shell_command('台服新闻',  only_group=False, parser=parser)


@twnews.handle()
async def send_sonet_news(bot: Bot, state: T_State):
    args = state['args']
    await send_news(twnews, SonetSpider,args.limit)

blnews = svbl.on_shell_command('B服新闻', aliases=(
    'b服新闻', '国服新闻'), only_group=False, parser=parser)


@blnews.handle()
async def send_bili_news(bot: Bot, state: T_State):
    args = state['args']
    await send_news(blnews, BiliSpider,args.limit)

'''
Author: AkiraXie
Date: 2021-02-11 00:00:55
LastEditors: AkiraXie
LastEditTime: 2021-03-16 15:00:37
Description: 
Github: http://github.com/AkiraXie/
'''
from typing import Type
from hoshino.matcher import Matcher
from hoshino import Service, Bot,scheduled_job
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


@scheduled_job('interval', id='推送新闻',minutes=5, jitter=20)
async def biso_news_poller():
    await news_poller(SonetSpider, svtw, '台服官网')
    await news_poller(BiliSpider, svbl, 'B服官网')


async def send_news(matcher: Type[Matcher], spider: BaseSpider, max_num=5):
    if not spider.item_cache:
        await spider.get_update()
    news = spider.item_cache
    news = news[:min(max_num, len(news))]
    await matcher.send(await spider.format_items(news), at_sender=True)


twnews = svtw.on_command('台服新闻', aliases=('台服活动',), only_group=False)


@twnews.handle()
async def send_sonet_news(bot: Bot):
    await send_news(twnews, SonetSpider)

blnews = svbl.on_command('B服新闻', aliases=('b服新闻', '国服新闻'), only_group=False)


@blnews.handle()
async def send_bili_news(bot: Bot):
    await send_news(blnews, BiliSpider)

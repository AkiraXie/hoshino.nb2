"""
Author: AkiraXie
Date: 2021-03-05 00:03:27
LastEditors: AkiraXie
LastEditTime: 2021-03-05 00:21:43
Description: 
Github: http://github.com/AkiraXie/
"""
from hoshino import Service, Bot, Event
from hoshino.util import get_event_image

sv = Service("ocr", visible=False, enable_on_default=False)
ocrm = sv.on_command("ocr", aliases=("识字", "文字识别"), only_group=False)


@ocrm
async def _(bot: Bot, event: Event):
    imgs = get_event_image(event)
    if not imgs:
        await ocrm.finish()
    for i, img in enumerate(imgs):
        try:
            res = await bot.ocr_image(image=img)
        except:
            sv.logger.error("Failed to call ocr-api")
            await ocrm.finish("请求ocrAPI失败")
        reply = [f"第{i+1}张图片的ocr结果是:"]
        texts = res["texts"]
        for t in texts:
            reply.append(t["text"])
        await ocrm.finish(" | ".join(reply), call_header=True)

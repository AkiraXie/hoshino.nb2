# from hoshino.util import aiohttpx
# from io import BytesIO
# import skia
# from PIL import Image
# from hoshino import MessageSegment
# from typing import Optional
# from nonebot.log import logger
# from dynrender_skia.Core import DynRender
# from dynamicadaptor.DynamicConversion import formate_message,RenderMessage
# url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail?timezone_offset=-480&id={dyn_id}&features=itemOpusStyle"
# headers = {
#     "referer": "https://t.bilibili.com/{dyn_id}",
#     "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36"
# }

# async def get_http_msg(id) -> Optional[dict]:
   
#     h = headers.copy()
#     h["referer"] = h["referer"].format(dyn_id=id)
#     resp = await aiohttpx.get(url.format(dyn_id=id),headers=h)
#     if not resp.ok:
#         logger.exception('get data from nav failed')
#         return None
#     if not resp.json["data"]:
#         logger.exception('get data from nav failed')
#         return None
#     return resp.json["data"]["item"]

# async def get_dynamic(id) -> Optional[RenderMessage]:
    
#     msg = await get_http_msg(id)
#     if not msg:
#         return None
#     msg["modules"]["module_dynamic"]["major"]["opus"]["title"] = str(msg["modules"]["module_dynamic"]["major"]["opus"]["title"])
#     return await formate_message('web',msg)

# async def get_dynamic_img(id) -> Optional[MessageSegment]:
   
#     msg = await get_dynamic(id)
#     print(msg)
#     if not msg:
#         return None
#     arr =  await DynRender().run(msg)
#     img =  skia.Image.fromarray(arr)
#     logger.info("get dynamic img",img)
#     pil_img = Image.fromarray(img,"RGBa")
#     bio = BytesIO()
#     pil_img.save(bio,format="PNG")
#     logger.info("get dynamic img",MessageSegment.image(bio.getvalue()))
#     return MessageSegment.image(bio.getvalue())

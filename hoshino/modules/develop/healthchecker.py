import nonebot
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loguru import logger
from nonebot.adapters import Bot

from hoshino.platform import get_group_list

# FastAPI 路由注册需要模块级 app 实例，get_app() 只能在 import 期调用。
app: FastAPI = nonebot.get_app()


@app.get("/bot_health")
async def bot_check(bot_id: str | None = None):
    try:
        bot: Bot = nonebot.get_bot(bot_id)
        await get_group_list(bot)
        logger.info(f"get bot ok: {bot_id}")
        return JSONResponse({"status": "ok", "message": f"get bot ok: {bot_id}"}, status_code=200)
    except Exception:
        logger.exception("bot health check failed")
        return JSONResponse({"status": "error", "message": "internal error"}, status_code=500)

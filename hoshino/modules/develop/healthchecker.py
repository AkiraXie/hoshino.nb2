from loguru import logger

import nonebot
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from hoshino.types import Bot
from hoshino.platform import get_group_list

app: FastAPI = nonebot.get_app()


@app.get("/bot_health")
async def bot_check(bot_id: str | None = None):
    try:
        bot: Bot = nonebot.get_bot(bot_id)
        await get_group_list(bot)
        logger.info(f"get bot ok: {bot_id}")
        return JSONResponse(
            {"status": "ok", "message": f"get bot ok: {bot_id}"}, status_code=200
        )
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Failed to get bot: {e!s}"},
            status_code=500,
        )

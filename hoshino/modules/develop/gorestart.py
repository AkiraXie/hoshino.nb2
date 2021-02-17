from loguru import logger
from hoshino import sucmd, aiohttpx, Bot, hsn_config
import json

gore = sucmd('restart', True, {'重启go', '重启gocq'})


@gore.handle()
async def gorestart(bot: Bot):
    params = {
        'access_token': hsn_config.access_token} if hsn_config.access_token else None
    go_port = hsn_config.admin_port if 'admin_port' in hsn_config.dict() else 9999
    try:
        res = await aiohttpx.post(f'http://127.0.0.1:{go_port}/admin/do_process_restart', params=params)
        if res.status_code != 200:
            resj = res.json
            await gore.finish(f'重启go-cqhttp失败,请前往服务器查看,出错如下:\n{json.dumps(resj)}')
    except Exception as e:
        logger.exception(e)
        await gore.finish(f'重启go-cqhttp失败,请前往服务器查看,出错如下:\n{e}')

'''
Author: AkiraXie
Date: 2021-03-06 00:37:42
LastEditors: AkiraXie
LastEditTime: 2021-03-06 14:14:17
Description: 
Github: http://github.com/AkiraXie/
'''
import asyncio
from hoshino import Service, Bot, Event
import websockets
from brotli import decompress
from json import loads
from numpy import mean
sv = Service('arc', visible=False, enable_on_default=False)
aarc = sv.on_command('arc', aliases={'arcaea', 'ARC'})

clear_list = ['Track Lost', 'Normal Clear', 'Full Recall',
              'Pure Memory', 'Easy Clear', 'Hard Clear']
diff_list = ['PST', 'PRS', 'FTR', 'BYD']


async def _lookup(nickname: str):
    ws = await websockets.connect("wss://arc.estertion.win:616/")
    await ws.send("lookup " + nickname)
    buffer = ""
    while buffer != "bye":
        buffer = await ws.recv()
        if isinstance(buffer, bytes):
            obj = loads(decompress(buffer))
            id = obj['data'][0]['code']
            return id


async def _query(id: str) -> tuple:
    data = ''
    scores = []
    ws = await websockets.connect('wss://arc.estertion.win:616', ping_interval=None)
    await ws.send(id)
    while data != 'bye':
        try:
            data = await ws.recv()
        except:
            try:
                id = await _lookup(id)
                if isinstance(id, str):
                    ws = await websockets.connect('wss://arc.estertion.win:616', ping_interval=None)
                    await ws.send(id)
                else:
                    return None
            except:
                sv.logger.error('Query arc failed')
                return None
        if isinstance(data, bytes):
            de_data = loads(decompress(data))
            if de_data['cmd'] == 'songtitle':
                song_title = de_data['data']
            if de_data['cmd'] == 'scores':
                scores.extend(de_data['data'])
            if de_data['cmd'] == 'userinfo':
                userinfo = de_data['data']
    scores.sort(key=lambda x: x['rating'], reverse=True)
    return song_title, scores, userinfo


async def _calc_30_10(ptt: float, scores: list) -> tuple:
    len_s = min(len(scores), 30)
    scores = [score['rating'] for score in scores[:len_s]]
    b30 = mean(scores)
    r10 = 4 * (ptt - b30 * 0.75)
    return b30, r10


async def query(id: str) -> str:
    reply = list()
    res = await _query(id)
    if not res:
        return f'Failed to query {id}'
    song_title, scores, userinfo = res
    ptt = userinfo['rating']/100
    b30, r10 = await _calc_30_10(ptt, scores)
    reply.append(f'Player: {userinfo["name"]}')
    reply.append(f'Potential: {ptt}')
    reply.append(f'Best 30: {b30:.3f}')
    reply.append(f'Recent top 10: {r10:.3f}')
    score = userinfo['recent_score'][0]
    reply.append(f'Recent play:\n{song_title[score["song_id"]]["en"]}  ' +
                 diff_list[score['difficulty']]+f'  {score["constant"]:.2f}')
    reply.append(f'~Clear type: {clear_list[score["clear_type"]]}')
    reply.append(f'~Score: {score["score"]}')
    reply.append(f'~Rating: {score["rating"]:.3f}')
    return '\n'.join(reply)


@aarc
async def _(bot: Bot, event: Event):
    id = event.get_plaintext()
    await aarc.send(f'Querying {id}...', call_header=True)
    await aarc.finish(await query(id), call_header=True)

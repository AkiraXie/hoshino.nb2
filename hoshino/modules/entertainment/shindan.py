'''
Author: AkiraXie
LastEditTime: 2021-04-21 19:17:50
LastEditors: AkiraXie
GitHub: https://github.com/AkiraXie
'''
from hoshino import Service, aiohttpx, Bot, Event, T_State
from hoshino.rule import ArgumentParser
from bs4 import BeautifulSoup
from datetime import datetime
sv = Service('shindan', visible=False, enable_on_default=False)
parser = ArgumentParser()
parser.add_argument('-n', '--name', type=str)
url = "https://en.shindanmaker.com/587874"


@sv.on_shell_command('shindan', parser=parser)
async def _(bot: Bot, event: Event, state: T_State):
    if state['args'].name:
        name = state['args'].name
    else:
        name = event.sender.card or event.sender.nickname
    now = datetime.now()
    fname = name+now.strftime("%Y-%m-%d")
    data = {}
    data['_token'] = 'gSQah1yVg6ZJAQZYhlKU3lCgglDgDRR7r7TNMKI8'
    data['name'] = fname
    data['hiddenName'] = '名無しのY'
    headers = {}
    headers['content-type'] = "application/x-www-form-urlencoded"
    headers['cookie'] = r"_session=48UfdQxjglAS2EL8wBJvYbEY9udOsz7YlKpZXAAV; dui=eyJpdiI6IkFWNU05a3MxQ2lKL2wxQVMrL3NDQmc9PSIsInZhbHVlIjoib05BM2hrYXZVam5adzdxOXYyZjRObkZBNHBTSkwrM0taQzMreFp6allFUEhtckhOWTNRbGVVVWFGR1FDRGNqa1NKV1dYVTh5VjRTcVI1MmgrdnZkdmx5KzdETXRNOFltdUt1djhldlVkWEVBTTVyN3UzMmpnWU5BR250UE9uYXMvMHR1SGlieWZPMGJReUg5UEQ3QW53PT0iLCJtYWMiOiI5MzIwNGVkNWJiYjJmYmViMmQ5Y2Q5NWI3MGMxYWU4ZGViMjUzYWQ1OWVkZDIzOTVkZjJhODU0ZTVmOTA4MGYwIn0%3D; _ga=GA1.2.80399894.1618935648; _gid=GA1.2.451561004.1618935648; cto_bundle=CC8qrl9KalJqc2ZldXhRYUduUjRwQjRMTllsZFolMkZBOGR0UVpibWhZNGxHd1IwdXBVUWg4WHZZTW8zeGt1ZCUyQiUyRkpURVJHRk8xZHh4NjMxdmREWWFZcVZ4TjhqYXR2YWklMkJqeUlVNFZOSHp6YzZhOVdOcXRyaXhPNndxTmRpc1IwJTJGRWRaN09aYkxkTWRudVBkcWtjMUFIV0V5WFBRJTNEJTNE; _cc_id=59f12f0dda794ea5b7691b1d740bc7dd; panoramaId_expiry=1619540492639; panoramaId=0c5c571f309e57cb5f4b797f4e1e16d5393855001ca6537d33cb40de2f712179; dsr=eyJpdiI6IkUyclRwL3JHMzhheXJmMHZFc0NIVHc9PSIsInZhbHVlIjoiZzl2UUxMM1YrdGE0b05zS21qcW9pSjhrQjRTeEdyQUVzSEZJNC95TmFkdmZNQklSODFyN2tjV1NSd0o2K0hKWVI4SmNmdGxVazFNK05KY3g0MFgrcXc9PSIsIm1hYyI6IjU0NmZhYjAxMGQzYzZjNGJjZTJjYjM2OTIxM2JlMmM5NDYyY2JlNWJjOTljNTA2NDEyYjg5NjIxZTA3NTIyZTgifQ%3D%3D; name=eyJpdiI6InZNSWRMdWduQW9Mb2VHRXpVRU9kdGc9PSIsInZhbHVlIjoidHBsL2RKc3ZYRERDeDBUUWR4Z3ZVZmppYUNnUlpJaCtaMEpVOXB6WGhGbXBBUlNtRzQvb1BLVmt6RFkzd3pxdDNPSkZ5V2R1enRwQkxEdEhxeFIzQmc9PSIsIm1hYyI6ImE1NmI3MGQxNTIyNTZhNjUxZDM5ZGIyOWJiMzc5YTU3NjAwY2M4MjM2OGZkODUzZDYzMTI4ODJmMzk2NmFhOGQifQ%3D%3D; XSRF-TOKEN=eyJpdiI6IkM5bUw3MVAzNXVHUEt3K0VyM1JDR1E9PSIsInZhbHVlIjoiNkx3TkRINkJCSUIrTlg3d1VvSmJLeWZ0WTlsczJxZ2pZeWFON0c0Ty8vQkRqMVh3MHJMN0pGb0VoUGtjVHVQenZYemVvcStER2k5NTA2MFkrYTd3K1BZT2owbFpHOWpBVDRKaHZ5bjBvU2NRNWh5cU1UTnhQMklGYkVsV3FIckEiLCJtYWMiOiJjMzYxOTdkYTkwNjRhODgxZmExNDQ2YzA1MGQ0YzYwMjIwNzlmZTM3N2U0YmQ3ZGViNTE1ZDhlZTI2ZTMxMjE1In0%3D; trc_cookie_storage=taboola%2520global%253Auser-id%3Db1b10b6b-fb9a-4877-b210-c75e74a7044c-tuct69af028"
    resp = await aiohttpx.post(url, data=data, headers=headers)
    cnt = resp.content
    soup = BeautifulSoup(cnt, 'lxml')
    span = soup.find(id='shindanResult')
    res = str(span).split('<br/>', 1)
    res = res[1]
    res = res.replace('<br/>', '\n').replace('&amp;',
                                             '&').replace('</span>', '')
    msg = [f'今日 {name} 的转生诊断结果为:']
    msg.append(res)
    msg = "\n".join(msg)
    await bot.send(event, msg)

"""小黑盒（xiaoheihe）BBS 帖子解析：bbs/link 分享链接。

实现移植自 https://github.com/Zhalslar/astrbot_plugin_parser 的 xiaoheihe
解析器，但按 hoshino 的 Post 体系重写（仅 BBS link 路径，游戏分享暂不覆盖）。

流程：设备指纹注册（fp-it.portal101.cn，匿名 deviceId）→ 签名
``/bbs/app/link/tree``（hkey/_time/nonce）→ 带 ``x_xhh_tokenid`` cookie 拉取
帖子数据。

注意：小黑盒对匿名设备的风控（status=show_captcha）目前会拦截数据接口，此时
按解析失败降级（记日志返回 None），不影响其他平台。
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import random
import re
import time
from pathlib import Path

from hoshino import data_dir
from hoshino.command import uni_image, uni_text, uni_video
from hoshino.types import MessageLike
from hoshino.util import aiohttpx
from hoshino.util.media import save_img_by_path, save_video_by_path
from hoshino.util.message import send_segments

from ..utils import Post as BasePost
from ..utils import PostMessage, clean_filename
from .sv import sv

# 设备指纹注册常量（来自 astrbot_plugin_parser，需与官网 web 端保持一致）。
FP_URL = "https://fp-it.portal101.cn/deviceprofile/v4"
FP_APP_ID = "heybox_website"
FP_ORGANIZATION = "0yD85BjYvGFAvHaSQ1mc"
FP_EP = (
    "V1ZCERzVgMWrKv+VcTl5QmS9JuPWLOQ8A0mACeTyYXtTbiguOrHhwaqnagZ6zdAgF"
    "4WpAYBvUH3EDnPRlNWut4CTDU1tCa80BSnvTMC9X1j9Kh6IMlGmzPIqpBzzx9r7Nt"
    "9XtUhv2WiQ2BgPnUwOFe7gN9r8Yj3184qxn1btJL8="
)
FP_DATA = (
    "abbbe96a1579aa6fe4fa84e875851b7d7a843a14c5c9573c771d9c1443c9b3a"
    "d7603a8d9d67dbc9bd001bf42702ac82e4a6979323ff305eecd74b9620ee140"
    "0c135f840b35d9402ec3e3a93fcb3d0d3d6b3e740f5176b72225b6fb8a0d483"
    "cab753aa71062dc9b59bc8de950628f23607301c6cd94e75f680b86485a11ac"
    "36eba1413e9f14b274eadff30114dfb1cedadc4bd08ef83c5b2d048970d07d3"
    "943afef809b44e3b9fee602c91e274fee1523a8beee7e7cec85680b279d616d"
    "da15e98b1b0aa718276bcdb05d4ac3e44e72da220e0ea798ad7452aec01d0db"
    "c31ad6bf147eab7f7e539d35fe5149110aae5c7069a67eba4aae638505819f8"
    "9e2a58bc3b5001c8a5045334121ef04a8e442d7dbb7776bd6013674d2c0028a"
    "f131bf6bde47b90dce5c8b9463c9f83d0e7264145c2f6f259d70c4d63a4996b"
    "b7c0074e8a59fa298ad144ec139cb29bc94074fbe2f4a88400d85c003793e2b"
    "e2077184c3ba2e792926fce25f24d3a764a7c2667446173c74aa704d0d517f2"
    "10926aaef05376230b43c3a676dad6ff1c9603553d66eadfb492445eac44745"
    "acc620b325560d4941c10e05f3099a17a553fd763a1b7d6ef29f512e436bdfa"
    "9fa7c5a70b6a5f91bbcb21946fc2ce92db0c92930008b0fc82e90c3c73f9265"
    "2ca388f77b262a918cf59160fa88e481138ee7fe9a9b51d7949a74d22d1dab4"
    "e865c12325bfb5b9e748526afb6d8a05c543fd6dc72e81b06a4ebbf8149fca5"
    "37a19330da2011eec0229e2302babe239397aa1c2292ab3807cf0aa129d078a"
    "a9da010003eac5bb2c06435fbbe9bee7543290c1224745bb485d78f42ee4e82"
    "afb27a38befc60a688fb2514795064926bf205357bd46b7c14dd15aea2cab48"
    "5c993f0df5a20811d0a7b3bfb1fcb0737c8305675e9bdac396ef8cffb0b6bc4"
    "700c3d881c1945329b721b9080bed46b18105b7c9fea4f8276f0fcd09fe99ec"
    "52fa50b11e12a19eb9d091ecde701ab2879e2d7727386b28bbde8d62832e1ad"
    "822ea57b383cdd3767e8ee64e201bf00fe9cc8428ece3262550764fea47c69e"
    "e4339de98767f034d8852993fdefa315d9dcda71a74b665804706d4f9a8c139"
    "3670c2220e4ceac833620e0dc8175eb7a77b8b37c1a9d9940c67d44c8bc6b5f"
    "9e46273e2f5149d3d3148e8f7a02c4a4c3c998924b7d0e93528952034adc20d"
    "c342404a8606f0c07cb2b98c4a5434e69b69282daf952f586b9eed4b4f1ef0c"
    "fe5c6d156d14fb5057c8c32a355d07e2f56737d1ccfad573d42c840bbe8b750"
    "388211f2c0c5d6a1e34e7741389a742dff58bb0b9f339707a349a09519ca78d"
    "5e4f1baaf2598ab9001c15824494eecc17735e69a193e5437cbe44c6f156a0b"
    "b8df4fed5edefd4f56f4ef0b4d8cc40fe623836da3c5e662005825c9d344074"
    "be2306d6241c163fe92a6ce40ff60538d7464f5a06b6bb9ca1e6f18491ca3c7"
    "d6c00e299cbb1ca1c525a981fc6c6f2bb05f709101099b8bd0d2c2a628d94c6"
    "1aa97fdd58c9f357359fbd5be9e8f0f534f4481fb780d58e3e599e01fdd5a7f"
    "c5fb7e01b76fd58b2f264947d2149fefa57577ef326e264fc827939329031d9"
    "01be7579ecf5fccdab11c615c1a053f198297c0723faf8b17ea3335d49df2bf"
    "dd17271c2b64745b1f412d87297edd4404a4ae5312debf73b66afcc3d884b93"
    "8de41b6ee87265ce624897f3557ebe2d97e6fb17f1dc6a893e48dfa16ef2bff"
    "d8f3e06f0a1fcf44c7f2efa372e0ff61344c93f4a2a66538fcc134cd0bf94d5"
    "4c969cda4392af70608cbab6cfa340b674ba3a59385c0ed9bb236ff6ed10e1e"
    "5a9d4b6529c075dc1ac23cfdae18ab1651a5ee747322e51e3cc6035ca929789"
    "00924e661a2694a47873569baa95fd821711dc53a1e0299ed707e337b570591"
    "a3f61a5e39f8a75771da1613e8236c9b1b94cb5617fdaf2424d68a7fbd83ebf"
    "356fc87e8a805bee5bbd20a55a70881394d7624b1dcf5a135f1cf40b842eca3"
    "3d46b72447e0a2e85adf6c26efa6cc73b63573840f7b6229fb03ab45a8b639b"
    "5a66bbd6f63d10e59db49d7a9c9af3e3aeb79b7b756e24d5002917e7e788018"
    "4f80fcc605a1ba825c779e6083fd7fb0920bbcee021ec8e35427391b871b149"
    "c306c2dbda602044cd53ec424dd70cfd1c14a23c9964c039258cff4b75112f8"
    "15d9717433c1989ec398cd2acd67c89be82a409e0ef8f3e9ea8ec8b51b5ea5a"
    "005b5e735978d9a2987a76d62a2af230e30dc6327f7c0d153add27c7e8a320e"
    "4df6c05ab91fe0b9f6f9e13c50f39454066776503eb2ec84b74b4b2d5228627"
    "d81c938f7201610c9b703e4fd283a94835b7387db2880443a050d3eb0859aa1"
    "efd0f9bb7613b6b918ec2f7b5bb3e7722105b595e7973a93e3de8153a0f8e5b"
    "fd1aa6cefc6285fea85e8381ddcce98b31dda33db2a3c80ac04df14b872c805"
    "15373f231c3653fb2db799b32e83e59fb0f5763febca3d291b49bf83dd7ebd6"
    "1229300b65d44964d9e679f6061a0b2ea1bcd9f5af9bf710047237d87d13394"
    "ea8b4627c6997589d0b58379d025b076460eab88d6615ee92b0aa6c47f721f9"
    "7e0b5bbe721f06544d0a1bb81402697f2d72ad32c791dab45064b4d18460602"
    "9494b268feaebb268e7f92352dc3482f857c14885aabbad98a43e5f8fa5d77d"
    "61dc22f23080b9e6403c76f5fb862d7520ab85ae7c1d0e339729f664e7d668f"
    "4b9d1301acabb62fda5940db236ea9d2ca896cbb6a13eda6120fa5881453cb4"
    "490438460c00db4cd4bdf5df993d3a8d5726c756015eed542e0a4b910570f39"
    "7211c3f84f6a0d038e82270f94543e8da1e8d0cffd8f4f561daaf6003ad1fad"
    "fdd89c50f057a79225d8647aead74b33216e328c4204686b4ae93ce5f7ee25e"
    "1c83fe2cb72c67589aa4865d278ff7a112d09c16707de8acd61b49b901a3266"
    "e8ef55f1351fdc3013154635e51e649cbf31fc9b32f6956800834ca73e0b75b"
    "2b54d7125257eb6c24ebff52b741109be6da99bb6e0ffab85c3c219550ec3fc"
    "b12e2e4d0234627b061193c290baa1be73241be70925c08d33e6efdd44eca9a"
    "5160bdc5b47bd1f9d3f2cbf38848cf1aaa2a4827f86e43e06246b3bf94cb0b9"
    "f050c89533a3be9ffecefebd1a92e04197f18d7fadc0bfc8664de18425d5c03"
    "59b58049267934756f513bd68ea427b38f15213f42cce05cd59f5ea502967ec"
    "6a096daaa5e5d2a373227f2fe4514e27dfa012d708f7e94a286452972b5fab4"
    "581ecee3df40bad802cbb50b1a5d9dd3323a5f7c61ab893b16782a0ba64fd42"
    "10c30ac00f9d21b9124e5e5b323f43badf56761e1eea5c86ff61f19ce1485f4"
    "2cf6cadd751bbfb2ef87229eee5068ef6e209f123d29a571a374974ceac2e77"
    "f143faba60fc5d16f88d801fa01d879420b5d1393ad5b2bc913e3b0ba7155a6"
    "7648196573126273cccc79f2eac32ab68d72cc0f7170feca9c9726af9d65962"
    "663d5281372386ec88bd2fa82316f687535ecd39f00658523708ca4785529f5"
    "93baf100597ed00c15ae8ff87baa295871680b4096ac03a550f0f015297198b"
    "1a93f38cfefbeceabc099c1026664d77f616b4f069cf8bf53d2684b9a4d933c"
    "3c65a3aef21559527bfc6586e0247efa244a0a355b43751bc09be8012699468"
    "a8c332d60b11bb4881bf56b92ead10e059ac40f83a4d6725cacbc1bb307c839"
    "c4edc8b5484b9e2935842e867e739223f2eaaaff04d9701cfa49e3f80be4f2d"
    "1b7e8eb76fd7f33dfa79831f75ee65a75b7c7fff98254818f1ab77bca856656"
    "4d48e0012733dd426bf841f27f960394b1bacb8a3e36b96c41d751584cd580f"
    "ef1b6a8bf990487268348f682a27549ecbb9674b14f2fc97f203f3468f248ec"
    "3cf5171aa5e8a8d31a9a433c4f7644736aaf6695b28771fe66b4736e3afb322"
    "11ad534b05641600d2cdc79a251fc4c4e5540df9a40aaad329fedd49a429b20"
    "70e1345a4146c297ee2a03f056675054e83207d17de21242032c30398259440"
    "84e60cbd70eb4c469859824cd7d04340de0d19e614a0826a63c63e15c3372b1"
    "7515d4b6951ff6c612f65c3e6538fd0515bcb4814bb641fca5a45c7dae9"
)
# 签名字符表（hkey 算法，来源同 astrbot_plugin_parser）。
CHAR_TABLE = "AB45STUVWZEFGJ6CH01D237IXYPQRKLMN89"
XHH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
LINK_TREE_URL = "https://api.xiaoheihe.cn/bbs/app/link/tree"
xhh_img_dir = data_dir / "xiaoheiheimages"
xhh_video_dir = data_dir / "xiaoheihevideos"
xhh_img_dir.mkdir(exist_ok=True)
xhh_video_dir.mkdir(exist_ok=True)

# 匿名设备指纹（进程内缓存，复用 astrbot 的 fp-it 注册流程）。
_device_id: str | None = None


# ---------------------------------------------------------------- 签名算法


def _av(text: str, cut: int) -> str:
    table = CHAR_TABLE[:cut]
    return "".join(table[ord(c) % len(table)] for c in text)


def _sv(text: str) -> str:
    return "".join(CHAR_TABLE[ord(c) % len(CHAR_TABLE)] for c in text)


def _interleave(parts: list[str]) -> str:
    result: list[str] = []
    max_len = max(len(part) for part in parts)
    for i in range(max_len):
        result.extend(part[i] for part in parts if i < len(part))
    return "".join(result)


def _xtime(value: int) -> int:
    return ((value << 1) ^ 27) & 0xFF if value & 128 else value << 1


def _mul3(value: int) -> int:
    return _xtime(value) ^ value


def _mul6(value: int) -> int:
    return _mul3(_xtime(value))


def _mul12(value: int) -> int:
    return _mul6(_mul3(_xtime(value)))


def _mul14(value: int) -> int:
    return _mul12(value) ^ _mul6(value) ^ _mul3(value)


def _mix_columns(col: list[int]) -> list[int]:
    values = list(col)
    while len(values) < 4:
        values.append(0)
    mixed = [
        _mul14(values[0]) ^ _mul12(values[1]) ^ _mul6(values[2]) ^ _mul3(values[3]),
        _mul3(values[0]) ^ _mul14(values[1]) ^ _mul12(values[2]) ^ _mul6(values[3]),
        _mul6(values[0]) ^ _mul3(values[1]) ^ _mul14(values[2]) ^ _mul12(values[3]),
        _mul12(values[0]) ^ _mul6(values[1]) ^ _mul3(values[2]) ^ _mul14(values[3]),
    ]
    if len(values) > 4:
        mixed.extend(values[4:])
    return mixed


def _sign_path(path: str, ts: int, nonce: str) -> str:
    path = "/" + "/".join(part for part in path.split("/") if part) + "/"
    interleaved = _interleave([_av(str(ts), -2), _sv(path), _sv(nonce)])[:20]
    md5_hex = hashlib.md5(interleaved.encode(), usedforsecurity=False).hexdigest()
    prefix = _av(md5_hex[:5], -4)
    suffix = str(sum(_mix_columns([ord(c) for c in md5_hex[-6:]])) % 100).zfill(2)
    return prefix + suffix


# ---------------------------------------------------------------- 请求


async def _get_device_id() -> str | None:
    """注册匿名设备指纹，返回 deviceId（进程内缓存）。"""
    global _device_id
    if _device_id:
        return _device_id
    payload = {
        "appId": FP_APP_ID,
        "organization": FP_ORGANIZATION,
        "ep": FP_EP,
        "data": FP_DATA,
        "os": "web",
        "encode": 5,
        "compress": 2,
    }
    try:
        response = await aiohttpx.post(
            FP_URL,
            json=payload,
            headers={"accept": "application/json, text/plain, */*"},
            timeout=10.0,
        )
    except Exception as exc:
        sv.logger.error(f"xiaoheihe: 设备指纹注册失败: {type(exc).__name__}")
        return None
    if response.status_code >= 400:
        sv.logger.error(f"xiaoheihe: 设备指纹注册失败，状态码 {response.status_code}")
        return None
    body = response.json
    detail = body.get("detail") if isinstance(body, dict) else None
    device_id = detail.get("deviceId") if isinstance(detail, dict) else None
    if not device_id:
        sv.logger.error("xiaoheihe: 设备指纹响应缺少 deviceId")
        return None
    _device_id = str(device_id)
    return _device_id


async def _fetch_link_tree(link_id: str, device_id: str) -> dict | None:
    """签名拉取 link/tree；status 非 ok（含风控 show_captcha）返回 None。"""
    now = int(time.time())
    nonce = (
        hashlib.md5((str(now) + str(random.random())).encode(), usedforsecurity=False)
        .hexdigest()
        .upper()
    )
    params = {
        "os_type": "web",
        "app": "heybox",
        "client_type": "web",
        "version": "999.0.4",
        "web_version": "2.5",
        "x_client_type": "web",
        "x_app": "heybox_website",
        "heybox_id": "",
        "x_os_type": "Windows",
        "device_info": "Chrome",
        "device_id": device_id,
        "link_id": link_id,
        "owner_only": "1",
        "hkey": _sign_path("/bbs/app/link/tree", now + 1, nonce),
        "_time": now,
        "nonce": nonce,
    }
    try:
        response = await aiohttpx.get(
            LINK_TREE_URL,
            params=params,
            cookies={"x_xhh_tokenid": f"B{device_id}"},
            headers={
                "accept": "application/json, text/plain, */*",
                "referer": "https://www.xiaoheihe.cn/",
                "origin": "https://www.xiaoheihe.cn",
            },
            timeout=15.0,
        )
    except Exception as exc:
        sv.logger.error(f"xiaoheihe: link/tree 请求失败: {type(exc).__name__}")
        return None
    if response.status_code >= 400:
        sv.logger.error(f"xiaoheihe: link/tree 请求失败，状态码 {response.status_code}")
        return None
    payload = response.json
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        status = payload.get("status") if isinstance(payload, dict) else "?"
        sv.logger.warning(f"xiaoheihe: link/tree 返回 {status}（匿名访问可能被风控）")
        return None
    result = payload.get("result")
    return result if isinstance(result, dict) else None


# ---------------------------------------------------------------- 解析


def _clean_text(text: str) -> str:
    text = html.unescape(text.replace("\xa0", " "))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _html_block_to_text(html_block: str) -> str:
    fragment = html.unescape(html_block)
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"</p>\s*<p[^>]*>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<img[^>]*>", "", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    lines = [_clean_text(line) for line in fragment.splitlines()]
    return "\n\n".join(line for line in lines if line).strip()


def _parse_text_and_images(link: dict) -> tuple[str, list[str]]:
    """正文 text 是 JSON 块数组（img 块 / html 文本块），拆成纯文本 + 图片 URL。"""
    raw_text = link.get("text")
    if not isinstance(raw_text, str) or not raw_text.strip():
        return "", []
    try:
        blocks = json.loads(raw_text)
    except json.JSONDecodeError:
        return _clean_text(raw_text), []
    if not isinstance(blocks, list):
        return _clean_text(raw_text), []

    text_parts: list[str] = []
    image_urls: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if str(block.get("type") or "") == "img":
            url = str(block.get("url") or "").strip()
            if url.startswith("http") and "/bbs/" in url and url not in seen:
                seen.add(url)
                image_urls.append(url)
            continue
        if block_html := str(block.get("text") or ""):
            cleaned = _html_block_to_text(block_html)
            if cleaned:
                text_parts.append(cleaned)
            for matched in re.finditer(r'data-original="([^"]+)"|src="([^"]+)"', block_html, re.I):
                url = (matched.group(1) or matched.group(2) or "").strip()
                if url.startswith("http") and "/bbs/" in url and url not in seen:
                    seen.add(url)
                    image_urls.append(url)
    return "\n\n".join(text_parts).strip(), image_urls


def _build_post(link_id: str, link: dict) -> Post | None:
    user = link.get("user")
    nickname = ""
    if isinstance(user, dict):
        nickname = _clean_text(str(user.get("username") or user.get("nickname") or ""))
    title = _clean_text(str(link.get("title") or ""))
    content, images = _parse_text_and_images(link)
    videos: list[str] = []
    if link.get("has_video") and (video_url := str(link.get("video_url") or "").strip()):
        videos.append(video_url)
    return Post(
        uid=nickname or link_id,
        id=link_id,
        content=content,
        title=title,
        images=images,
        videos=videos,
        nickname=nickname,
        url=f"https://www.xiaoheihe.cn/app/bbs/link/{link_id}",
    )


class Post(BasePost):
    async def download_images(self) -> list[Path]:
        async def download_single_image(i: int, img_url: str) -> Path | None:
            try:
                content_part = clean_filename(self.content[:20])
                nickname_part = clean_filename(self.nickname)
                filename = f"{content_part}_{nickname_part}_{self.id}_{i}.jpg"
                filepath = xhh_img_dir / filename
                result_path = await save_img_by_path(
                    img_url,
                    filepath,
                    True,
                    headers={
                        "referer": "https://www.xiaoheihe.cn/",
                        "user-agent": XHH_UA,
                    },
                )
                if result_path:
                    return result_path
                sv.logger.error(f"Failed to save image {img_url}")
                return None
            except Exception:
                sv.logger.exception(f"Error downloading image {img_url}", exception=True)
                return None

        tasks = [download_single_image(i, img_url) for i, img_url in enumerate(self.images)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        saved: list[Path] = []
        for result in results:
            if isinstance(result, Path):
                saved.append(result)
            elif isinstance(result, Exception):
                sv.logger.error(f"Error in download task: {result}")
        return saved

    async def download_videos(self) -> list[Path]:
        async def download_single_video(i: int, video_url: str) -> Path | None:
            try:
                content_part = clean_filename(self.content[:12])
                nickname_part = clean_filename(self.nickname)
                filename = f"{content_part}_{nickname_part}_{self.id}_{i}.mp4"
                filepath = xhh_video_dir / filename
                result_path = await save_video_by_path(video_url, filepath, True)
                if result_path:
                    return result_path
                sv.logger.error(f"Failed to save video {video_url}")
                return None
            except Exception:
                sv.logger.exception(f"Error downloading video {video_url}", exception=True)
                return None

        tasks = [download_single_video(i, video_url) for i, video_url in enumerate(self.videos)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        saved: list[Path] = []
        for result in results:
            if isinstance(result, Path):
                saved.append(result)
            elif isinstance(result, Exception):
                sv.logger.error(f"Error in download task: {result}")
        return saved

    async def get_message(self, full: bool = False) -> PostMessage:
        imgs = await self.download_images()
        vids: list[Path] = []
        if full:
            vids = await self.download_videos()
        return PostMessage(
            text=self._build_text(),
            images=imgs,
            videos=vids,
        )

    def render_message(self, post_message: PostMessage) -> list[MessageLike]:
        messages: list[MessageLike] = []
        if post_message.text:
            messages.append(uni_text(post_message.text))
        messages.extend(uni_image(img) for img in post_message.images)
        messages.extend(uni_video(vid) for vid in post_message.videos)
        return messages

    def get_referer(self) -> str:
        return "https://www.xiaoheihe.cn/"

    def _build_text(self) -> str:
        title = f"\n标题：{self.title}" if self.title else ""
        return f"{self.nickname or '小黑盒'} 小黑盒~{title}\n----------\n{self.content}\n链接: {self.url}"


async def parse_xiaoheihe(link_id: str) -> Post | None:
    device_id = await _get_device_id()
    if not device_id:
        return None
    result = await _fetch_link_tree(link_id, device_id)
    if not result:
        return None
    link = result.get("link")
    if not isinstance(link, dict):
        sv.logger.error("xiaoheihe: link/tree 缺少 link 节点")
        return None
    return _build_post(link_id, link)


async def resolve_xiaoheihe(name: str, url: str) -> bool:
    matched = re.search(r"link_id=([0-9a-z]+)|/app/bbs/link/([0-9a-z]+)", url)
    if not matched:
        return False
    link_id = matched.group(1) or matched.group(2)
    post = await parse_xiaoheihe(link_id)
    if not post:
        sv.logger.error(f"{name} {url} parse error")
        return False
    post_message = await post.get_message(full=True)
    msgs = post.render_message(post_message)
    if not msgs:
        return False
    await asyncio.sleep(0.3)
    await send_segments(msgs)
    return True

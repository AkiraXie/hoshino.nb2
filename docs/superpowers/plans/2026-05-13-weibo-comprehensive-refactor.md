# 微博模块全面重构实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 完成 post/sub runtime 收尾 + `__init__.py` 拆分为 `fav.py`/`resolve.py`

**架构：** Phase 1 将 `post_runtime.py` 剩余导出移入 `internal/post_runtime.py`，删除顶层旧 runtime 文件。Phase 2 从 `__init__.py` 提取收藏系统和 URL 解析到独立文件。

**技术栈：** Python、asyncio、nonebot2、pytest、dataclasses、pathlib

---

## 前置分析

### 当前导入拓扑（需要修复的链路）

```
post.py → post_runtime.py (旧, 614行)     ← 需要改为 → post_helper.py
post.py → post_helper.py (新, 已有)       ← 部分迁移完成
sub_helper.py → post.py                    ← 正常（仅取 WeiboDispatchTask）
internal/sub_runtime.py → post.py          ← 正常（仅取 WeiboDispatchTask, cache_weibo_msg_id）

sub_runtime.py (旧, 299行)                 ← 零外部导入者，可安全删除

tests/test_weibo_post_runtime.py → post_runtime.py  ← 需要更新导入
tests/test_weibo_request_sub_runtime.py → sub_runtime.py, post_runtime.py ← 需要更新导入
```

### 符号归属目标

| 符号 | 当前位置 | 目标位置 |
|---|---|---|
| `WeiboDispatchTask` | `post_runtime.py:592` | `internal/post_runtime.py` |
| `adapt_message` | `post_runtime.py:602` | `post_helper.py` (已有 `adapt_post_message`) |
| `cache_weibo_msg_id` | `post_runtime.py:527` | `internal/post_runtime.py` |
| `get_cached_weibo_uid_id` | `post_runtime.py:531` | `internal/post_runtime.py` |
| `post_msg_from_uid_id` | `post_runtime.py:610` | `internal/post_runtime.py` (已有) |
| `render_messages` | `post_runtime.py:556` | `internal/post_runtime.py` (已有 via helper) |
| `weibo_img_dir` | `post_runtime.py:27` | `internal/post_runtime.py` |
| `weibo_video_dir` | `post_runtime.py:29` | `internal/post_runtime.py` |
| `weibo_msg_dir` | `post_runtime.py:31` | `internal/post_runtime.py` |

---

### 任务 1：将 `post_runtime.py` 剩余符号迁入 `internal/post_runtime.py`

**文件：**
- 修改：`hoshino/modules/information/weibo/internal/post_runtime.py`
- 修改：`hoshino/modules/information/weibo/post_helper.py`

- [ ] **步骤 1：向 `internal/post_runtime.py` 追加 `WeiboDispatchTask`、目录常量、缓存函数**

在 `hoshino/modules/information/weibo/internal/post_runtime.py` 文件末尾追加以下代码：

```python
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from hoshino import Bot, Message, MessageSegment, config

if TYPE_CHECKING:
    from ..post import WeiboPost


weibo_img_dir = config.data_dir / "weiboimages"
weibo_img_dir.mkdir(parents=True, exist_ok=True)
weibo_video_dir = config.data_dir / "weibovideos"
weibo_video_dir.mkdir(parents=True, exist_ok=True)
weibo_msg_dir = config.data_dir / "weibomsgs"
weibo_msg_dir.mkdir(parents=True, exist_ok=True)

WEIBO_MSG_CACHE_TTL = 3 * 60 * 60
CACHE_FILE_CLEANUP_DELAY = 3 * 60 * 60


class _TimedHandleRegistry:
    def __init__(self) -> None:
        self._handles: dict[str, asyncio.Handle] = {}

    def replace(self, key: str, delay: float, callback, *args) -> None:
        handle = self._handles.pop(key, None)
        if handle and not handle.cancelled():
            handle.cancel()
        loop = asyncio.get_running_loop()
        self._handles[key] = loop.call_later(delay, callback, *args)

    def pop(self, key: str) -> asyncio.Handle | None:
        return self._handles.pop(key, None)


class _MessageIdCache:
    def __init__(self, ttl: float) -> None:
        self._ttl = ttl
        self._values: dict[str, str] = {}
        self._registry = _TimedHandleRegistry()

    def remember(self, msg_id: int | str, uid: str, post_id: str) -> None:
        key = str(msg_id)
        self._values[key] = f"{uid}_{post_id}"
        self._registry.replace(key, self._ttl, self._expire, key)

    def get(self, msg_id: int | str) -> str:
        return self._values.get(str(msg_id), "")

    def _expire(self, key: str) -> None:
        self._values.pop(key, None)
        handle = self._registry.pop(key)
        if handle and not handle.cancelled():
            handle.cancel()


class _TempFileCleaner:
    def __init__(self, delay: float) -> None:
        self._delay = delay
        self._registry = _TimedHandleRegistry()

    def schedule(self, paths: list[Path]) -> None:
        for path in paths:
            self._registry.replace(str(path), self._delay, self._delete, str(path))

    def _delete(self, filepath_str: str) -> None:
        self._registry.pop(filepath_str)
        try:
            path = Path(filepath_str)
            if path.exists():
                path.unlink()
        except Exception:
            pass


@dataclass
class WeiboDispatchTask:
    post: "WeiboPost"
    message: "PostMessage"
    group_id: int

    def get_id(self) -> str:
        return f"{self.group_id}_{self.post.id}"


_message_id_cache = _MessageIdCache(WEIBO_MSG_CACHE_TTL)
_file_cleaner = _TempFileCleaner(CACHE_FILE_CLEANUP_DELAY)


def schedule_file_cleanup(paths: list[Path]) -> None:
    _file_cleaner.schedule(paths)


def cache_weibo_msg_id(msg_id: int | str, uid: str, post_id: str) -> None:
    _message_id_cache.remember(msg_id, uid, post_id)


def get_cached_weibo_uid_id(msg_id: int | str) -> str:
    return _message_id_cache.get(msg_id)
```

- [ ] **步骤 2：向 `post_helper.py` 追加目录常量和缓存函数的薄代理**

在 `hoshino/modules/information/weibo/post_helper.py` 末尾追加：

```python
from .internal.post_runtime import (
    weibo_img_dir,
    weibo_msg_dir,
    weibo_video_dir,
    cache_weibo_msg_id,
    get_cached_weibo_uid_id,
    post_msg_from_uid_id,
    WeiboDispatchTask,
)
```

并在 `__all__` 中不重新导出（这些符号由调用方从 helper 直接 import 即可）。

- [ ] **步骤 3：Commit**

```bash
git add hoshino/modules/information/weibo/internal/post_runtime.py \
  hoshino/modules/information/weibo/post_helper.py
git commit -m "refactor: consolidate remaining post runtime symbols into internal"
```

---

### 任务 2：更新 `post.py` 的导入路径

**文件：**
- 修改：`hoshino/modules/information/weibo/post.py`

- [ ] **步骤 1：将 `post.py` 中的 `from .post_runtime import` 替换为 `from .post_helper import`**

在 `hoshino/modules/information/weibo/post.py` 第 29-39 行，将：

```python
from .post_runtime import (
    WeiboDispatchTask,
    adapt_message,
    cache_weibo_msg_id,
    get_cached_weibo_uid_id,
    post_msg_from_uid_id,
    render_messages,
    weibo_img_dir,
    weibo_msg_dir,
    weibo_video_dir,
)
```

替换为：

```python
from .post_helper import (
    WeiboDispatchTask,
    cache_weibo_msg_id,
    get_cached_weibo_uid_id,
    post_msg_from_uid_id,
    render_messages,
    weibo_img_dir,
    weibo_msg_dir,
    weibo_video_dir,
)
```

注意：`adapt_message` 不再从此处导入。`post.py` 本身不直接使用 `adapt_message`，它只是用于 re-export。

- [ ] **步骤 2：检查 `post.py` 中 `adapt_message` 的实际使用**

运行以下命令确认 `adapt_message` 在 `post.py` 中没有被使用：

```bash
rg "adapt_message" hoshino/modules/information/weibo/post.py
```

如果只在 import 行出现，则安全移除。

- [ ] **步骤 3：Commit**

```bash
git add hoshino/modules/information/weibo/post.py
git commit -m "refactor: switch post.py imports from post_runtime to post_helper"
```

---

### 任务 3：删除顶层旧 runtime 文件

**文件：**
- 删除：`hoshino/modules/information/weibo/post_runtime.py`
- 删除：`hoshino/modules/information/weibo/sub_runtime.py`
- 修改：`hoshino/modules/information/weibo/sub_helper.py`（如果引用了 sub_runtime）

- [ ] **步骤 1：确认 `sub_runtime.py` 无外部导入者**

```bash
rg "from.*weibo.*sub_runtime|from.*weibo.*import.*sub_runtime" hoshino/ --no-heading | grep -v __pycache__ | grep -v "internal/sub_runtime"
```

预期输出为空。

- [ ] **步骤 2：确认 `post_runtime.py` 仅被 `post.py` 和测试导入（已在上一步修复）**

```bash
rg "from.*weibo.*post_runtime|from.*weibo.*import.*post_runtime" hoshino/ --no-heading | grep -v __pycache__ | grep -v "internal/post_runtime" | grep -v tests/
```

预期输出为空（测试文件将在任务 5 更新）。

- [ ] **步骤 3：删除旧文件**

```bash
git rm hoshino/modules/information/weibo/post_runtime.py
git rm hoshino/modules/information/weibo/sub_runtime.py
```

- [ ] **步骤 4：Commit**

```bash
git commit -m "refactor: remove legacy post_runtime.py and sub_runtime.py"
```

---

### 任务 4：移除 `full` 参数

**文件：**
- 修改：`hoshino/modules/information/utils.py`
- 修改：`hoshino/modules/information/bilireq/utils.py`

- [ ] **步骤 1：从 `Post.get_message` 基类移除 `full` 参数**

`hoshino/modules/information/utils.py` 第 106 行，将：

```python
async def get_message(self, **kwargs) -> PostMessage: ...
```

保持不变（已经是无 `full` 的签名）。检查 `resolve_full_fetch` 函数是否仍在被使用：

```bash
rg "resolve_full_fetch" hoshino/modules/information/ --no-heading | grep -v __pycache__
```

- [ ] **步骤 2：更新 `BiliBiliDynamic.get_message` 移除 `full` 参数**

在 `hoshino/modules/information/bilireq/utils.py` 中找到 `BiliBiliDynamic.get_message`，将：

```python
async def get_message(self, **kwargs) -> PostMessage:
    full = resolve_full_fetch(kwargs, default=True)
    if full:
        ...
```

替换为直接获取完整消息（去掉 `full` 条件分支）：

```python
async def get_message(self) -> PostMessage:
    screenshot = await get_bili_dynamic_screenshot(
        self.url,
        cookies=await get_bilicookies(),
    )
    return PostMessage(
        text=self._build_text(include_content=screenshot is None),
        screenshot=screenshot,
        images=list(self.images),
    )
```

并从文件顶部移除 `resolve_full_fetch` 的 import。

- [ ] **步骤 3：检查 `resolve_full_fetch` 是否还有调用者**

```bash
rg "resolve_full_fetch" hoshino/ --no-heading | grep -v __pycache__ | grep -v tests/
```

如果没有其他调用者，从 `hoshino/modules/information/utils.py` 中移除该函数。

- [ ] **步骤 4：Commit**

```bash
git add hoshino/modules/information/bilireq/utils.py hoshino/modules/information/utils.py
git commit -m "refactor: remove full parameter from Post.get_message and BiliBiliDynamic"
```

---

### 任务 5：更新测试导入路径

**文件：**
- 修改：`tests/test_weibo_post_runtime.py`
- 修改：`tests/test_weibo_request_sub_runtime.py`

- [ ] **步骤 1：更新 `test_weibo_post_runtime.py` 的导入**

将 `tests/test_weibo_post_runtime.py` 第 22-26 行的：

```python
from hoshino.modules.information.weibo.post_runtime import (
    adapt_message,
    post_msg_from_uid_id,
    render_messages,
)
```

替换为：

```python
from hoshino.modules.information.weibo.post_helper import (
    adapt_post_message,
    post_msg_from_uid_id,
    render_post_message,
)
```

并将测试函数中对 `adapt_message` 的调用替换为 `adapt_post_message`（参数签名相同），对 `render_messages` 的调用替换为 `render_post_message`。

- [ ] **步骤 2：更新 `test_weibo_request_sub_runtime.py` 的导入**

将 `tests/test_weibo_request_sub_runtime.py` 第 10-16 行的：

```python
from hoshino.modules.information.weibo.post import WeiboDispatchTask, WeiboPost
from hoshino.modules.information.weibo.post_runtime import get_cached_weibo_uid_id
from hoshino.modules.information.weibo.request import WeiboRequestError
from hoshino.modules.information.weibo.request_runtime import WeiboPostParser
from hoshino.modules.information.weibo.sub_runtime import WeiboDispatchRuntime
from hoshino.modules.information.weibo.sub_helper import build_runtime_state
import hoshino.modules.information.weibo.sub_runtime as sub_runtime
```

替换为：

```python
from hoshino.modules.information.weibo.post import WeiboDispatchTask, WeiboPost
from hoshino.modules.information.weibo.post_helper import get_cached_weibo_uid_id
from hoshino.modules.information.weibo.request import WeiboRequestError
from hoshino.modules.information.weibo.request_runtime import WeiboPostParser
from hoshino.modules.information.weibo.internal.sub_runtime import WeiboDispatchRuntime
from hoshino.modules.information.weibo.sub_helper import build_runtime_state
```

如果测试中 `sub_runtime` 模块级引用（如 `sub_runtime.WEIBO_COLD_UID_THRESHOLD`）被使用，改为：

```python
import hoshino.modules.information.weibo.internal.sub_runtime as sub_runtime
```

- [ ] **步骤 3：运行测试验证**

```bash
python -m pytest tests/test_weibo_post_runtime.py tests/test_weibo_request_sub_runtime.py -v
```

- [ ] **步骤 4：Commit**

```bash
git add tests/test_weibo_post_runtime.py tests/test_weibo_request_sub_runtime.py
git commit -m "test: update test imports after runtime consolidation"
```

---

### 任务 6：创建 `fav.py` 收藏夹系统

**文件：**
- 创建：`hoshino/modules/information/weibo/fav.py`

- [ ] **步骤 1：创建 `fav.py` 文件**

从 `__init__.py` 提取以下内容到 `hoshino/modules/information/weibo/fav.py`：

```python
import json
import random
import re
from typing import TYPE_CHECKING

from hoshino import Bot, Event, Message
from hoshino.util import send_segments

from .sv import sv
from .post import weibo_img_dir, weibo_msg_dir, weibo_video_dir, post_msg_from_uid_id, render_messages
from .db import _load_weibo_favs, _save_weibo_favs

if TYPE_CHECKING:
    pass


weibo_fav_json = None  # 将在模块初始化时设置


def _load_weibo_favs() -> dict[str, list[str]]:
    from hoshino import data_dir
    fav_json = data_dir / "weibofavorite.json"
    if not fav_json.exists():
        return {}
    try:
        data = json.loads(fav_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}

    favorites: dict[str, list[str]] = {}
    for uid, ids in data.items():
        if not isinstance(uid, str) or not isinstance(ids, list):
            continue
        favorites[uid] = [str(post_id) for post_id in ids if post_id]
    return favorites


def _save_weibo_favs(favorites: dict[str, list[str]]) -> None:
    from hoshino import data_dir
    fav_json = data_dir / "weibofavorite.json"
    fav_json.write_text(
        json.dumps(favorites, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_fav(uid: str, id: str) -> bool:
    uid = str(uid)
    id = str(id)
    favorites = _load_weibo_favs()
    ids = favorites.get(uid, [])
    if id in ids:
        return False
    ids.append(id)
    favorites[uid] = ids
    _save_weibo_favs(favorites)
    return True


def _list_favorite_uid_ids(target_uid: str | None = None) -> list[str]:
    favorites = _load_weibo_favs()
    uid_ids: list[str] = []
    for uid, ids in favorites.items():
        if target_uid and uid != target_uid:
            continue
        uid_ids.extend(f"{uid}_{post_id}" for post_id in ids)
    return uid_ids


def _load_favorite_post_metadata(uid: str, post_id: str) -> dict[str, str] | None:
    metadata_path = weibo_msg_dir / uid / post_id / "message.json"
    if not metadata_path.exists():
        return None

    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    content = str(data.get("content") or data.get("text") or "").strip()
    if not content:
        return None

    return {
        "uid": str(data.get("uid") or uid),
        "id": str(data.get("id") or post_id),
        "content": content,
    }


def _summarize_favorite_content(content: str, limit: int = 80) -> str:
    content = re.sub(r"\s+", " ", content).strip()
    if len(content) <= limit:
        return content
    return content[: limit - 3] + "\n..."


def _search_favorite_posts(
    keyword: str,
    target_uid: str | None = None,
) -> list[dict[str, str]]:
    keyword = keyword.strip()
    if not keyword:
        return []

    needle = keyword.casefold()
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for uid_id in _list_favorite_uid_ids(target_uid):
        uid, post_id = uid_id.split("_", 1)
        metadata = _load_favorite_post_metadata(uid, post_id)
        if not metadata:
            continue

        if needle not in metadata["content"].casefold():
            continue

        unique_key = f"{metadata['uid']}_{metadata['id']}"
        if unique_key in seen:
            continue

        seen.add(unique_key)
        results.append(metadata)
    return results


def _resolve_favorite_uid_ids(post_ref: str) -> list[str]:
    post_ref = post_ref.strip()
    if not post_ref:
        return []

    favorites = _load_weibo_favs()
    if "_" in post_ref:
        uid, post_id = post_ref.split("_", 1)
        if post_id in favorites.get(uid, []):
            return [f"{uid}_{post_id}"]
        return []

    matched: list[str] = []
    for uid, ids in favorites.items():
        if post_ref in ids:
            matched.append(f"{uid}_{post_ref}")
    return matched


def _build_favorite_search_messages(
    keyword: str,
    results: list[dict[str, str]],
    target_uid: str | None = None,
) -> list[Message]:
    lines = []
    for item in results:
        summary = _summarize_favorite_content(item["content"])
        lines.append(f"UID: {item['uid']} ID: {item['id']} 内容: {summary}")

    chunks = [lines[index : index + 10] for index in range(0, len(lines), 10)]
    messages: list[Message] = []
    total = len(results)
    scope = f" UID: {target_uid}" if target_uid else ""
    for index, chunk in enumerate(chunks, start=1):
        header = f"微博收藏搜索结果{scope}: 关键词 {keyword}，共 {total} 条，第 {index}/{len(chunks)} 组"
        text = "\n".join([header, *chunk])
        if index == len(chunks):
            text += "\n使用 查看微博收藏 ID"
            text += "\n或 查看微博收藏 UID_ID"
        messages.append(Message(text))
    return messages


# 命令 handlers


async def random_weibo_favorite(bot: Bot, event: Event):
    target_uid = event.get_plaintext().strip() or None
    uid_ids = _list_favorite_uid_ids(target_uid)
    if not uid_ids:
        if target_uid:
            await bot.send(event, f"没有找到 UID {target_uid} 的微博收藏")
        else:
            await bot.send(event, "当前没有微博收藏")
        return
    uid_id = random.choice(uid_ids)
    uid, id = uid_id.split("_", 1)
    post_message = await post_msg_from_uid_id(uid, id)
    if not post_message:
        await bot.send(event, f"无法还原微博收藏: {uid_id}")
        return
    msgs = render_messages(post_message)
    if not msgs:
        await bot.send(event, f"微博收藏为空: {uid_id}")
        return
    await send_segments(msgs)


async def search_weibo_favorite(bot: Bot, event: Event):
    arg = event.get_plaintext().strip()
    if not arg:
        await bot.send(event, "用法: 搜索微博收藏 关键词\n或: 搜索微博收藏 UID 关键词")
        return

    target_uid = None
    keyword = arg
    parts = arg.split(maxsplit=1)
    if len(parts) == 2 and parts[0].isdecimal():
        target_uid, keyword = parts

    results = _search_favorite_posts(keyword, target_uid=target_uid)
    if not results:
        if target_uid:
            await bot.send(event, f"没有找到 UID {target_uid} 中包含 {keyword} 的微博收藏")
        else:
            await bot.send(event, f"没有找到包含 {keyword} 的微博收藏")
        return

    messages = _build_favorite_search_messages(keyword, results, target_uid=target_uid)
    await send_segments(messages)


async def show_weibo_favorite(bot: Bot, event: Event):
    post_ref = event.get_plaintext().strip()
    if not post_ref:
        await bot.send(event, "用法: 查看微博收藏 ID\n或: 查看微博收藏 UID_ID")
        return

    matched = _resolve_favorite_uid_ids(post_ref)
    if not matched:
        await bot.send(event, f"没有找到微博收藏: {post_ref}")
        return

    if len(matched) > 1:
        lines = ["找到多个同名收藏，请改用 UID_ID:", *matched[:10]]
        if len(matched) > 10:
            lines.append(f"还有 {len(matched) - 10} 条未展示")
        await bot.send(event, "\n".join(lines))
        return

    uid_id = matched[0]
    uid, post_id = uid_id.split("_", 1)
    post_message = await post_msg_from_uid_id(uid, post_id)
    if not post_message:
        await bot.send(event, f"无法还原微博收藏: {uid_id}")
        return

    msgs = render_messages(post_message)
    if not msgs:
        await bot.send(event, f"微博收藏为空: {uid_id}")
        return

    await send_segments(msgs)


__all__ = [
    "append_fav",
    "random_weibo_favorite",
    "search_weibo_favorite",
    "show_weibo_favorite",
]
```

- [ ] **步骤 2：Commit**

```bash
git add hoshino/modules/information/weibo/fav.py
git commit -m "refactor: extract fav system from __init__.py into fav.py"
```

---

### 任务 7：创建 `resolve.py` URL 解析 + Reaction

**文件：**
- 创建：`hoshino/modules/information/weibo/resolve.py`

- [ ] **步骤 1：创建 `resolve.py` 文件**

```python
import re

from hoshino import Bot
from hoshino.event import GroupMsgEmojiLikeEvent
from hoshino.util import send_to_superuser
from nonebot.typing import T_State
from nonebot.compat import type_validate_python
from hoshino import Message

from .sv import sv
from .post import get_cached_weibo_uid_id
from .fav import append_fav


weibo_regexs = {
    "weibo": re.compile(r"(http:|https:)\/\/weibo\.com\/(\d+)\/(\w+)"),
    "mweibo": re.compile(r"(http:|https:)\/\/m\.weibo\.cn\/(detail|status)\/(\w+)"),
    "mappweibo": re.compile(r"(http:|https:)\/\/mapp\.api\.weibo\.cn\/fx\/(\w+)\.html"),
}


async def reaction_weibo_rule(
    bot: Bot,
    event: GroupMsgEmojiLikeEvent,
    state: T_State,
) -> bool:
    if event.get_emoji() != "319":
        return False
    msg_id = event.message_id
    msg = await bot.get_msg(message_id=msg_id)
    sender = msg.get("sender", {}).get("user_id")
    sender = str(sender)
    if sender != bot.self_id and sender not in bot.config.superusers:
        return False
    msg = msg.get("message")
    if msg:
        msg = type_validate_python(Message, msg)
        text = msg.extract_plain_text()
        text = text.strip()
        for name, regex in weibo_regexs.items():
            matched = regex.search(text)
            if matched:
                state["__weibo_name"] = name
                state["__weibo_url"] = matched.group(0)
                state["__weibo_matched"] = matched
                state["__weibo_msg_id"] = msg_id
                sv.logger.info(f"Matched weibo URL in reaction: {state['__weibo_url']}")
                return True
    return False


async def handle_weibo_reaction(state: T_State):
    if not (name := state.get("__weibo_name")):
        return
    if not (matched := state.get("__weibo_matched")):
        return
    if not (url := state.get("__weibo_url")):
        return
    if not (msg_id := state.get("__weibo_msg_id")):
        return
    if cached := get_cached_weibo_uid_id(msg_id):
        uid, id = cached.split("_", 1)
        appended = append_fav(uid, id)
        if appended:
            sv.logger.info(f"Added weibo to fav by cache: {uid} {id}")
            await send_to_superuser(f"微博收藏新增: UID {uid} ID {id} URL {url} (from cache)")

    else:
        try:
            from .request import parse_weibo_with_id, parse_mapp_weibo

            if name == "weibo":
                _, _, post_id = matched.groups()
                post = await parse_weibo_with_id(post_id)
            elif name == "mweibo":
                _, _, post_id = matched.groups()
                post = await parse_weibo_with_id(post_id)
            elif name == "mappweibo":
                post = await parse_mapp_weibo(url)
            else:
                sv.logger.error(f"Unknown weibo type: {name}")
                return
            if post:
                appended = append_fav(post.uid, post.id)
                if appended:
                    sv.logger.info(f"Added weibo to fav: {post.uid} {post.id}")
                    await send_to_superuser(f"微博收藏新增: UID {post.uid} ID {post.id} URL {post.url}")
            else:
                sv.logger.error(f"Failed to parse weibo URL: {url}")
        except Exception as e:
            sv.logger.error(f"Error handling weibo reaction: {e} url: {url}")


__all__ = [
    "weibo_regexs",
    "reaction_weibo_rule",
    "handle_weibo_reaction",
]
```

- [ ] **步骤 2：Commit**

```bash
git add hoshino/modules/information/weibo/resolve.py
git commit -m "refactor: extract URL resolve and reaction from __init__.py into resolve.py"
```

---

### 任务 8：更新 `__init__.py` 最终形态

**文件：**
- 修改：`hoshino/modules/information/weibo/__init__.py`

- [ ] **步骤 1：重写 `__init__.py` 的 import 区域和收藏系统引用**

从 `hoshino/modules/information/weibo/__init__.py` 中：

1. 删除收藏系统相关的函数定义（`_load_weibo_favs` 到 `_build_favorite_search_messages`，约 200 行）
2. 删除 reaction 相关代码（`weibo_regexs`, `reaction_weibo_rule`, `handle_weibo_reaction`, `svpost_notice` 注册，约 80 行）
3. 删除收藏命令 handlers（`random_weibo_favorite`, `search_weibo_favorite`, `show_weibo_favorite`，约 100 行）
4. 添加新的 import：

```python
from .fav import (
    append_fav,
    random_weibo_favorite,
    search_weibo_favorite,
    show_weibo_favorite,
)
from .resolve import (
    weibo_regexs,
    reaction_weibo_rule,
    handle_weibo_reaction,
)
```

5. 保留 `svpost_notice` 注册代码，但 handler 改为调用 `handle_weibo_reaction`：

```python
svpost_notice = sv.on_notice(
    rule=reaction_weibo_rule,
    permission=SUPERUSER,
    priority=5,
    block=True,
)

@svpost_notice.handle()
async def _handle_weibo_reaction(state: T_State):
    await handle_weibo_reaction(state)
```

6. 保留收藏命令注册，但 handler 改为从 `fav.py` import：

```python
@sv.on_command(
    "随机微博收藏",
    aliases=("微博随机收藏", "收藏微博", "randwbfav", "rwbfav"),
    only_group=False,
    only_to_me=True,
    permission=SUPERUSER,
    priority=5,
)
async def _random_weibo_favorite(bot: Bot, event: Event):
    await random_weibo_favorite(bot, event)


@sv.on_command(
    "搜索微博收藏",
    aliases=("搜微博收藏", "微博收藏搜索", "wbfavsearch", "searchwbfav"),
    only_group=False,
    permission=SUPERUSER,
    priority=5,
)
async def _search_weibo_favorite(bot: Bot, event: Event):
    await search_weibo_favorite(bot, event)


@sv.on_command(
    "查看微博收藏",
    aliases=("重现微博收藏", "显示微博收藏", "showwbfav", "getwbfav"),
    only_group=False,
    permission=SUPERUSER,
    priority=5,
)
async def _show_weibo_favorite(bot: Bot, event: Event):
    await show_weibo_favorite(bot, event)
```

- [ ] **步骤 2：验证 `__init__.py` 行数显著减少**

```bash
wc -l hoshino/modules/information/weibo/__init__.py
```

预期从 656 行减少到约 350 行。

- [ ] **步骤 3：Commit**

```bash
git add hoshino/modules/information/weibo/__init__.py
git commit -m "refactor: slim __init__.py using fav.py and resolve.py"
```

---

### 任务 9：最终验证

- [ ] **步骤 1：运行全部 weibo 测试**

```bash
python -m pytest tests/test_weibo_*.py -v 2>&1 | head -100
```

- [ ] **步骤 2：检查无残留的旧 import 引用**

```bash
rg "from.*post_runtime|from.*sub_runtime" hoshino/ --no-heading | grep -v __pycache__ | grep -v "internal/"
```

预期输出为空（如果测试尚未更新，可在此步骤更新）。

- [ ] **步骤 3：验证模块可以正常导入**

```bash
python -c "from hoshino.modules.information.weibo import sv; print('OK')"
```

- [ ] **步骤 4：Commit 最终修复**

```bash
git add -A
git commit -m "chore: final verification and cleanup after weibo refactor"
```

---

## 自检

**1. 规格覆盖度：**

| 规格需求 | 任务 |
|---|---|
| post runtime 符号迁入 internal | 任务 1 |
| post.py 导入路径更新 | 任务 2 |
| 删除旧 runtime 文件 | 任务 3 |
| 移除 full 参数 | 任务 4 |
| 测试更新 | 任务 5 |
| 创建 fav.py | 任务 6 |
| 创建 resolve.py | 任务 7 |
| __init__.py 瘦身 | 任务 8 |
| 最终验证 | 任务 9 |

**2. 占位符扫描：** 无 TODO/TBD/待定。

**3. 类型一致性：**
- `WeiboDispatchTask` 定义在 `internal/post_runtime.py` → `post_helper.py` 重导出 → `post.py` / `sub_helper.py` / `internal/sub_runtime.py` 消费 ✓
- `append_fav` 定义在 `fav.py` → `resolve.py` 和 `__init__.py` 消费 ✓
- `reaction_weibo_rule` / `handle_weibo_reaction` 定义在 `resolve.py` → `__init__.py` 消费 ✓
- `adapt_post_message` 替代 `adapt_message`，签名兼容 ✓
- `render_post_message` 替代 `render_messages`，签名兼容 ✓

# hoshino.nb2 插件编写指南

## 项目架构

```
hoshino/
├── core/           # Service, hooks, config, permission, rule
├── command/        # Alconna, Args, CommandMeta, UniMsg (Alconna facade)
├── platform/       # adapter-aware facade + ob11/telegram/milky 隔离层
├── content/        # Post/PostMessage/UIDManager (内容推送引擎)
├── modules/        # 业务插件 ← 你的代码在这里
└── util/           # 工具函数
```

**Import 规则**：插件只 import `core`、`command`、`platform`、`content`。**禁止**直接 import `nonebot.adapters.onebot.v11`。

## 快速开始

新插件放在 `hoshino/modules/<category>/`（information, interactive, develop, tools, entertainment）。

最小模板：

```python
# hoshino/modules/develop/my_plugin.py
from hoshino.core.service import Service
from hoshino.command import Alconna, Args, UniMessage

sv = Service("my_plugin", enable_on_default=True)

@sv.on_alconna(Alconna("hello", Args["name?", str]))
async def _(name: str | None = None):
    msg = f"Hello {name}!" if name else "Hello World!"
    await UniMessage.text(msg).send()
```

## 命令注册

### 基础命令 (`on_alconna`)

```python
from hoshino.command import Alconna, Args

@sv.on_alconna(Alconna("天气", Args["city", str]))
async def _(city: str):
    # city 自动从消息中提取
    await UniMessage.text(f"{city}的天气是晴天").send()
```

### 命令别名 (`aliases`)

```python
@sv.on_alconna(Alconna("订阅", Args["keyword", str]), aliases=("关注", "follow"))
async def _(keyword: str):
    ...
```

### 命令元数据 (`meta`)

```python
from hoshino.command import CommandMeta

@sv.on_alconna(
    Alconna("天气", Args["city", str]),
    meta=CommandMeta(description="查询城市天气", usage="天气 <城市>", example="天气 杭州"),
)
async def _(city: str):
    ...
```

### 旧命令 API (`on_command`) — 兼容保留

```python
# 仍可用，内部已切到 on_alconna
@sv.on_command("旧命令", aliases={"oldcmd"})
async def _(bot, event):
    ...
```

## 依赖注入（DI）

用 DI 获取事件信息，无需 `bot`/`event` 参数：

```python
from hoshino.platform.depends import GroupID, SenderID, PlainText

@sv.on_alconna(Alconna("投票", Args["option", str]))
async def _(option: str, gid: int = GroupID(), uid: int = SenderID()):
    # gid = 群号, uid = 发送者, option = 命令参数
    await UniMessage.text(f"群{gid} 用户{uid} 投票: {option}").send()
```

可用 DI：

| DI | 类型 | 说明 |
|---|---|---|
| `GroupID()` | `int \| None` | 群号 |
| `SenderID()` | `int \| None` | 发送者 user_id |
| `PlainText()` | `str` | 消息纯文本 |
| `MsgTarget` | `MsgTarget` | Alconna 原生 — 发送目标 |

### Reaction DI

Reaction handler 不接收 adapter Event，也不直接调用 `bot.get_msg()`：

```python
from hoshino.platform import (
    ReactedMessage,
    Reaction,
    ReactionInfo,
    RetrievedMessage,
    reaction_event_rule,
)

@sv.on_notice(rule=reaction_event_rule)
async def _(
    reaction: ReactionInfo | None = Reaction(),
    message: RetrievedMessage | None = ReactedMessage(),
):
    if (
        reaction is None
        or message is None
        or not reaction.is_add
        or reaction.face_id != "66"
    ):
        return
    text = message.content.extract_plain_text()
```

该对象统一 OB11 的 `GroupReactionEvent` / `GroupMsgEmojiLikeEvent` 与 Milky 的
`GroupMessageReactionEvent`。字段定义和取消事件差异见 `docs/milky.md`。

## 消息构造

全部用 `UniMessage`，不用 `Message`/`MessageSegment`：

```python
from hoshino.command import UniMessage

# 文本
msg = UniMessage.text("Hello")

# 图片（本地文件）
msg = UniMessage.image(file="/path/to/img.png")

# 图片（URL）
msg = UniMessage.image(url="https://example.com/img.png")

# 图片（bytes）
msg = UniMessage.image(raw=img_bytes)

# 组合消息
msg = UniMessage.text("标题\n") + UniMessage.image(file="/path/to/img.png")

# 发送
await msg.send()                         # 自动目标
await msg.send(target)                   # 显式 Target
await UniMessage.text("ok").send(reply_to=message_id)  # 回复
```

**禁止**：
```python
# ❌ 不要用 OneBot Message/MessageSegment
from nonebot.adapters.onebot.v11 import Message
msg = Message("text")
```

## 权限

```python
from hoshino.core.permission import SUPERUSER
from hoshino.platform.permission import ADMIN, NORMAL, OWNER

@sv.on_alconna(Alconna("admin_cmd"), permission=ADMIN)
async def _():
    ...

@sv.on_alconna(Alconna("public_cmd"), permission=NORMAL)
async def _():
    ...
```

## 事件判断

```python
from hoshino.platform import is_group_event, is_private_event

@sv.on_alconna(Alconna("test"), only_group=False)
async def _(msg: UniMsg):
    ...
```

**禁止**：`isinstance(event, GroupMessageEvent)` — 用 `is_group_event(event)`。

## 合并转发

节点内容继续使用 `UniMessage`，不要构造 OB11 `node` segment：

```python
from hoshino.platform import send_group_forward

await send_group_forward(
    bot,
    gid,
    [
        UniMessage.text("第一条"),
        UniMessage.image(url="https://example.com/image.jpg"),
    ],
    user_id=bot.self_id,
    nickname="Hoshino",
)
```

OB11 与 Milky 会发送原生合并转发；Telegram 会按顺序逐条发送节点内容。

## DB 访问

`create_all` 必须放在启动钩子中，不能放在 import 时：

```python
from hoshino.core.hooks import on_serial_startup

@on_serial_startup
async def _ensure_schema():
    Base.metadata.create_all(engine)
```

## 完整示例

```python
# hoshino/modules/information/my_subscribe.py
from hoshino.core.service import Service
from hoshino.command import Alconna, Args, CommandMeta, UniMessage
from hoshino.platform.depends import GroupID
from hoshino.platform.message import send_to_target
from hoshino.platform.permission import ADMIN
from hoshino.platform.target import group_target

sv = Service("my_subscribe", enable_on_default=False, manage_perm=ADMIN)

@sv.on_alconna(
    Alconna("订阅", Args["keyword", str]),
    aliases=("关注",),
    meta=CommandMeta(description="订阅关键词"),
)
async def _(keyword: str, gid: int = GroupID()):
    # 保存订阅...
    await UniMessage.text(f"已订阅: {keyword}").send()

async def push_to_group(bot, gid: int, title: str, img_path: str):
    msg = UniMessage.text(title) + UniMessage.image(file=img_path)
    await send_to_target(bot, group_target(gid), msg)
```

## Import 速查表

| 需要什么 | Import 路径 |
|---|---|
| Service | `hoshino.core.service` |
| Alconna/Args/UniMessage | `hoshino.command` |
| CommandMeta | `hoshino.command` |
| Permission (ADMIN/NORMAL...) | `hoshino.platform.permission` |
| DI (GroupID/PlainText...) | `hoshino.platform.depends` |
| 事件判断 (is_group_event...) | `hoshino.platform` |
| Reaction DI | `hoshino.platform` (`Reaction`, `ReactedMessage`) |
| Target/send/forward | `hoshino.platform` common facade |
| Hooks (on_startup...) | `hoshino.core.hooks` |

## 绝对禁止

1. ❌ `from nonebot.adapters.onebot.v11 import ...` — 只允许 platform/ob11 内部使用
2. ❌ `isinstance(event, GroupMessageEvent)` — 用 `is_group_event(event)`
3. ❌ 构造 `Message`/`MessageSegment` — 用 `UniMessage`
4. ❌ `event.group_id` / `event.user_id` — 用 DI 或 platform helper
5. ❌ `bot.send_group_msg()` / `bot.send_private_msg()` — 用 `send_to_target()`
6. ❌ import 时执行 DB DDL — 用 `@on_serial_startup`
7. ❌ `except BaseException` — 用 `except Exception`
8. ❌ reaction handler import adapter Event — 用 `Reaction()` DI

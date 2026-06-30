# hoshino.nb2 插件编写指南

## 快速开始

新插件放在 `hoshino/modules/<category>/` 下（category = information, interactive, develop, tools, entertainment 等）。

最小插件模板：

```python
# hoshino/modules/develop/my_plugin.py
from hoshino.service import Service
from hoshino.platform import UniMessage, UniMsg

sv = Service("my_plugin", enable_on_default=True)

@sv.on_alconna("hello")
async def _():
    await UniMessage.text("Hello World!").send()

@sv.on_alconna("echo")
async def _(msg: UniMsg):
    await msg.send()
```

## 消息发送

### 推荐方式

```python
from hoshino.platform import group_target, send_to_target, UniMessage

# 回复当前事件
await UniMessage.text("Hello!").send()

# 发送到指定群
await send_to_target(bot, group_target(12345678), "Hello group!")

# 发送图片到当前事件
await UniMessage.image(path="/path/to/image.png").send()

# 构造复杂消息，并用当前 matcher 上下文发送
msg = UniMessage.text("标题\n") + UniMessage.image(file="/path/to/img.png")
await msg.send()
```

## 事件访问

新代码优先用 Alconna/NoneBot 依赖注入直接拿需要的数据，不要把 `bot/event` 当成默认签名：

```python
from hoshino.platform import UniMsg, MsgTarget, UniMessage

@sv.on_alconna("inspect")
async def _(msg: UniMsg, target: MsgTarget):
    await UniMessage.text(f"target={target.id}, text={msg.extract_plain_text()}").send()
```

只有兼容旧 matcher 或特殊事件时，再用 `hoshino.platform` 的 helper：

```python
from hoshino.platform import get_group_id, get_user_id, get_plaintext, get_event_message

@sv.on_command("mycmd")
async def _(bot: Bot, event: Event):
    gid = get_group_id(event)          # int | None
    uid = get_user_id(event)           # int | None
    text = get_plaintext(event)        # str
    msg = get_event_message(event)     # Message
```

**不要**这样写：
```python
gid = event.group_id           # 直接属性访问 — 绑死了 OneBot
gid = getattr(event, "group_id", None)  # 裸鸭子类型 — 散布在代码中
```

## 事件类型判断

```python
from hoshino.platform import is_group_event, is_private_event

@sv.on_message()
async def _(bot: Bot, event: Event):
    if is_group_event(event):
        await bot.send(event, "这是群聊")
    elif is_private_event(event):
        await bot.send(event, "这是私聊")
```

**不要**这样写：
```python
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent

if isinstance(event, GroupMessageEvent):  # bind OneBot
    ...
```

## 权限

```python
from hoshino.permission import ADMIN, NORMAL, SUPERUSER, OWNER

# 管理员命令
@sv.on_command("admin_cmd", permission=ADMIN)
async def _(bot: Bot, event: Event):
    ...

# 所有人可用
@sv.on_command("public_cmd", permission=NORMAL)
async def _(bot: Bot, event: Event):
    ...
```

权限定义：
- `NORMAL` — 所有人（群聊 + 私聊 + 超级用户）
- `ADMIN` — 超级用户 + 群管理员 + 群主
- `OWNER` — 超级用户 + 群主
- `SUPERUSER` — 仅超级用户
- `PADMIN` / `POWNER` — 加私聊权限的变体

## Service 开关

```python
sv = Service("my_plugin",
    manage_perm=ADMIN,         # 谁可以开关此服务
    enable_on_default=True,    # 默认开启
    visible=True,              # 在服务列表中可见
)
```

群管理员可以用 `.enable my_plugin` / `.disable my_plugin` 控制开关。

## DB 访问

避免在 import 时执行 `create_all`。使用启动钩子：

```python
# ❌ 不要
Base.metadata.create_all(engine)  # import 时执行

# ✅ 正确
from hoshino.hooks import on_serial_startup

@on_serial_startup
async def _ensure_schema():
    Base.metadata.create_all(engine)
```

## Message 构造（information 类插件）

新代码优先构造 `UniMessage`：

```python
from hoshino.platform import UniMessage

msg = UniMessage.text("标题") + UniMessage.image(url="https://example.com/a.png")
await msg.send()
```

兼容旧 `Message` 消费者时，再用 platform 包装器：

```python
from hoshino.platform import (
    text_message,
    image_segment,
    video_segment,
    message_from_parts,
    send_to_target,
)

# 文本
msg = text_message("这是一条消息")

# 图片
img = image_segment("/path/to/image.png")

# 多段组合
combined = message_from_parts([
    text_message("标题"),
    image_segment("/path/to/img1.png"),
    image_segment("/path/to/img2.png"),
])

# 发送
await send_to_target(bot, group_target(gid), combined)
```

## 完整示例

```python
# hoshino/modules/information/my_subscribe.py
from hoshino.service import Service
from hoshino.types import Bot, Event
from hoshino.permission import ADMIN
from hoshino.platform import (
    get_group_id,
    get_plaintext,
    group_target,
    send_to_target,
    text_message,
    image_segment,
    message_from_parts,
)

sv = Service("my_subscribe", enable_on_default=False, manage_perm=ADMIN)

# 订阅命令
@sv.on_command("订阅")
async def _(bot: Bot, event: Event):
    gid = get_group_id(event)
    keyword = get_plaintext(event).strip()
    if not keyword:
        await bot.send(event, "用法: 订阅 <关键词>")
        return
    # 保存订阅...
    await bot.send(event, f"已订阅: {keyword}")

# 推送
async def push_to_group(bot: Bot, gid: int, title: str, img_path: str):
    msg = message_from_parts([
        text_message(title),
        image_segment(img_path),
    ])
    await send_to_target(bot, group_target(gid), msg)
```

## 注意事项

1. **不要** import `nonebot.adapters.onebot.v11.*` — 用 `hoshino.platform` 替代
2. **不要** `isinstance(event, GroupMessageEvent)` — 用 `is_group_event(event)`
3. **不要** `event.group_id` / `event.user_id` — 用 `get_group_id(event)` / `get_user_id(event)`
4. **不要** `bot.send_group_msg()` / `bot.send_private_msg()` — 用 `send_to_target()`
5. **不要** import 时执行 DB DDL — 用 `@on_serial_startup` 钩子
6. **不要** `except BaseException` — 用 `except Exception`
7. **不要** 为无状态工厂创建类 — 函数足够
8. **不要** 默认写 `(bot: Bot, event: Event)` handler — 优先用 `UniMsg` / `MsgTarget` / Alconna 参数注入

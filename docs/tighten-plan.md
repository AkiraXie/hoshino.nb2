# hoshino.nb2 平台依赖收紧计划

## 目标

**全项目仅 5 个文件允许接触 OneBot 符号，其余零接触。**

即：`grep -r "onebot\|from hoshino.types import Bot\|from hoshino.event import GroupMessage" hoshino/modules/` 返回空。

## 当前状态

31 个文件通过 `from hoshino.types import Bot, Event, Message...` 间接使用 OneBot 符号。根因：`hoshino/types.py` 和 `hoshino/event.py` 是 OneBot 的 re-export 网关。

## 执行步骤

### 收紧-A：`hoshino/types.py` 重命名 OneBot 符号

```python
# 改后：显式前缀，吓阻直接使用
from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter
from nonebot.adapters.onebot.v11.event import Event as OneBotV11Event

# 保留 NoneBot 原生（适配器无关）符号
from nonebot.typing import T_Handler, T_State
from nonebot.params import Depends, BotParam, EventParam, ...
from nonebot.matcher import Matcher, current_bot, current_event
from nonebot.adapters import Bot, Event  # 基类，适配器无关
```

影响：所有 `from hoshino.types import Bot, Event` 会炸掉，强制迁移。

### 收紧-B：模块 handler 迁移到 Alconna DI + UniMessage

每个 handler 按以下模式改写：

```python
# 旧
@sv.on_command("xxx")
async def _(bot: Bot, event: Event):
    gid = event.group_id
    text = event.get_plaintext()
    await bot.send(event, result)

# 新
@sv.on_alconna(Alconna("xxx", Args["text", str]))
async def _(target: MsgTarget, text: str):
    await UniMessage.text(result).send(target)
```

执行顺序（按模块）：
1. `tools/b64.py` ✅ 已完成
2. `tools/emojimix/` — testemoji 用 UniMsg
3. `develop/echoandsay.py` — echo + reply
4. `entertainment/bihua.py` — 2 handlers
5. `interactive/chooseone.py`
6. `steam/steam.py` — 4 handlers
7. `bilireq/__init__.py` — 4 handlers（添加/删除/列表/刷新）
8. `pushlive/__init__.py` — 添加订阅 handler
9. `weibo/__init__.py` — 6 handlers（加 Reply/Message 自定义 DI）
10. `base/ls.py`, `base/broadcast.py`, `base/cookies.py`
11. `base/service_manage/` — 3 handlers（需 state 交互，部分迁移）
12. `interactive/QA/` — 8 handlers（复杂 state 流程，部分迁移）

### 收紧-C：写自定义 DI 注入器

对 Alconna 没有内置的参数，创建自定义 `Depends`：

```python
# hoshino/platform/alconna.py 新增

def ReplyMessage() -> Any:
    """DI：注入回复消息对象"""
    async def _dep(event: Event):
        reply = getattr(event, "reply", None)
        return reply.message if reply else None
    return Depends(_dep)

def EventMessageID() -> int:
    """DI：注入当前消息 ID"""
    async def _dep(event: Event):
        return getattr(event, "message_id", 0)
    return Depends(_dep)
```

### 收紧-D：消息构造直接产出 UniMessage

废弃 `image_segment()`、`text_message()` 等 platform 包装器，改为直接构造：

```python
# 旧（platform 包装，仍返回 OneBot 类型）
from hoshino.platform import image_segment, text_message
msg = text_message("标题")

# 新（直接 UniMessage）
from hoshino.platform import uni_image, uni_text
msg = uni_text("标题")
img = uni_image("/path/to/img.png")
combined = msg + img
```

`hoshino/platform/message.py` 里已有的 `image_segment` 等保留兼容，但新代码不用。

### 收紧-E：删除 `hoshino/event.py` 的非必要导出

```python
# 改后：仅保留自定义事件
from hoshino.platform.event import is_group_event, is_private_event  # re-export

# 自定义事件（compat 边界）
class GroupReactionEvent(NoticeEvent): ...
class GroupMsgEmojiLikeEvent(NoticeEvent): ...

# 不再导出：Event, MessageEvent, GroupMessageEvent, PrivateMessageEvent
```

## 验证标准

- `grep -rn "from hoshino.types import Bot\|from hoshino.types import Event\|from hoshino.event import GroupMessage\|from hoshino.event import PrivateMessage\|from hoshino.event import MessageEvent" hoshino/modules/ hoshino/base/` → 空
- `uv run ruff check .` → 无新增 error
- 启动烟测 → 插件加载完成
- 每个迁移后的 handler 功能正常

## 不可触碰的边界

- `hoshino/bootstrap.py` — Bot.send() patch
- `hoshino/message.py` — Message/MessageSegment 核心类型
- `hoshino/event.py` 的自定义事件类 — 来自 Lagrange/LLOneBot 的协议扩展
- `hoshino/base/image.py` 的 reaction/emoji 事件处理
- `hoshino/base/test.py` — 测试代码

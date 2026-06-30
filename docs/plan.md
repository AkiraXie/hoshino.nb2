# hoshino.nb2 平台解耦计划

## 目标

用 `nonebot-plugin-alconna` 的 `UniMessage` / `Target` 替代 OneBot v11 原生调用，使 hoshino 层成为适配器无关的抽象，支持未来接入 Telegram、Discord 等多平台。

## 当前耦合全景

### 耦合热力图

```
run.py               🔴 注册 OneBot Adapter
hoshino/message.py   🔴 Message/MessageSegment 类型
hoshino/event.py     🔴 Event 类型 + 自定义事件
hoshino/permission.py 🔴 GROUP/GROUP_ADMIN 等权限
hoshino/bootstrap.py 🔴 Bot.send() patch (最复杂)
hoshino/types.py     🟡 IDE 类型桩
hoshino/service.py   🟡 get_enable_groups/broadcast
hoshino/util/        🟡 parse_qq, send_segments, forward
modules/*            🟢 各模块 isinstance/直接API调用
```

### 关键 OneBot API 使用统计

| API | 使用次数 | 位置 |
|---|---|---|
| `bot.send_group_msg()` | 10+ | bootstrap, service, broadcast, modules |
| `bot.send_private_msg()` | 3 | bootstrap, util, listenmeta |
| `bot.get_group_list()` | 6 | service, broadcast, service_manage, healthchecker |
| `bot.get_group_member_info()` | 2 | bootstrap, alisten |
| `bot.call_api(send_group_forward_msg)` | 1 | util/send_segments |
| `isinstance(event, GroupMessageEvent)` | 15+ | 遍布各模块 |
| `isinstance(event, PrivateMessageEvent)` | 3 | service_manage, util |

### OneBot Segment 类型清单

`text`, `image`, `at`, `video`, `forward`, `node_custom`, `reply`, `mface`

其中 `forward` / `node_custom`（合并转发节点）是 OneBot 专有概念，Alconna 无直接等价物。

---

## 分步执行计划

### 阶段一：基础设施（Phase 1 — Foundation）

#### 步骤 1：添加依赖

```bash
uv add nonebot-plugin-alconna
```

**验证**：`uv run python -c "from nonebot_plugin_alconna import UniMessage; print('ok')"`

#### 步骤 2：重构 `hoshino/message.py` — 消息抽象层

**目标**：用 `UniMessage` 替代 OneBot `Message`/`MessageSegment`，同时保持向后兼容。

**当前代码**：
```python
from nonebot.adapters.onebot.v11.message import MessageSegment, Message
from nonebot.adapters import MessageTemplate
```

**方案**：创建兼容包装层。

```python
# hoshino/message.py (新)
from nonebot_plugin_alconna import UniMessage, Image, Text, At, Video, Reply

# 向后兼容别名
Message = UniMessage

class MessageSegment:
    """兼容层 — 提供与 OneBot MessageSegment 相同的方法签名"""
    @staticmethod
    def text(content: str) -> UniMessage:
        return UniMessage.text(content)

    @staticmethod
    def image(file_or_bytes) -> UniMessage:
        return UniMessage.image(file=file_or_bytes) if isinstance(file_or_bytes, str) else UniMessage.image(raw=file_or_bytes)

    @staticmethod
    def at(user_id: str | int) -> UniMessage:
        return UniMessage.at(user_id=str(user_id))

    @staticmethod
    def video(file_or_bytes) -> UniMessage:
        return UniMessage.video(file=file_or_bytes) if isinstance(file_or_bytes, str) else UniMessage.video(raw=file_or_bytes)

    @staticmethod
    def reply(msg_id: str | int) -> UniMessage:
        return UniMessage.reply(str(msg_id))

    @staticmethod
    def node_custom(user_id, nickname, content) -> UniMessage:
        # OneBot 专有 — 保留为特殊标记，在 Bot.send() 层处理
        return UniMessage.custom(
            type="node_custom",
            user_id=str(user_id),
            nickname=nickname,
            content=content,
        )

    @staticmethod
    def forward(id_: str) -> UniMessage:
        # OneBot 专有 — 保留为特殊标记
        return UniMessage.custom(type="forward", id=id_)

    # mface 降级为 image
    @staticmethod
    def mface(data: dict) -> UniMessage:
        url = data.get("url", "")
        return UniMessage.image(url=url) if url else UniMessage.text("[动画表情]")
```

**验证**：现有模块 import 不报错；`MessageSegment.image()`, `MessageSegment.at()`, `MessageSegment.text()` 返回类型与现有代码兼容。

#### 步骤 3：重构 `hoshino/event.py` — 事件抽象层

**目标**：自定义事件不依赖 OneBot 的 `NoticeEvent`；提供鸭子类型检查替代 `isinstance(event, GroupMessageEvent)`。

**方案**：

```python
# hoshino/event.py (新)
from nonebot.adapters import Event as BaseEvent
from pydantic import BaseModel

# 自定义事件 — 直接从 nonebot.adapters.Event 继承
class GroupReactionEvent(BaseEvent):
    """Lagrange GroupReactionEvent — 适配器无关"""
    group_id: int
    user_id: int  # operator_id
    # ... 保持其他字段不变

class GroupMsgEmojiLikeEvent(BaseEvent):
    """LLOneBot GroupMsgEmojiLike — 适配器无关"""
    group_id: int
    user_id: int
    # ... 保持其他字段不变

# 鸭子类型辅助函数（替代 isinstance 检查）
def is_group_event(event: BaseEvent) -> bool:
    return hasattr(event, "group_id") and not hasattr(event, "notice_type")

def is_private_event(event: BaseEvent) -> bool:
    return not hasattr(event, "group_id") and hasattr(event, "user_id")

def get_group_id(event: BaseEvent) -> int | None:
    return getattr(event, "group_id", None)

def get_user_id(event: BaseEvent) -> str | None:
    uid = getattr(event, "user_id", None)
    return str(uid) if uid is not None else None
```

**验证**：自定义事件可正常注册和触发；`is_group_event()` / `is_private_event()` 在 OneBot 环境下行为正确。

#### 步骤 4：重构 `hoshino/permission.py` — 权限抽象层

**目标**：不依赖 OneBot 的 `GROUP`/`GROUP_ADMIN` 等权限常量。

**方案**：NoneBot 基类 `Permission` 本身是适配器无关的。`GROUP`、`PRIVATE` 等是 OneBot 的 permission 策略。使用 duck-typing 实现：

```python
# hoshino/permission.py (新)
from nonebot.permission import SUPERUSER, Permission

def _group_check(sender) -> bool:
    return hasattr(sender, "group_id")

def _private_check(sender) -> bool:
    return not hasattr(sender, "group_id") and hasattr(sender, "user_id")

GROUP = Permission(_group_check)
PRIVATE = Permission(_private_check)

# GROUP_ADMIN, GROUP_OWNER 需要用 Alconna 的权限或 duck-typing role 字段
# 暂时保持与 OneBot 相同的语义，后续按需扩展
```

**验证**：现有 `ADMIN`、`NORMAL` 等组合权限行为不变。

#### 步骤 5：重构 `hoshino/bootstrap.py` — Bot.send() patch

**目标**：`Bot.send()` 使用 `UniMessage` + `Target` 替代 OneBot 的 `send_group_msg`/`send_private_msg`。

**这是整个迁移的核心和最复杂步骤。**

**方案**：

```python
# hoshino/bootstrap.py (新核心逻辑)
from nonebot_plugin_alconna import UniMessage, Target

async def send(
    self: Bot,
    event,
    message,
    at_sender=False,
    call_header=False,
    **kwargs,
):
    msg = UniMessage(message) if not isinstance(message, UniMessage) else message

    # 构建 Target
    target = Target.from_event(event)

    # at_sender 处理
    if at_sender and hasattr(event, "user_id"):
        msg = UniMessage.at(str(event.user_id)) + UniMessage.text(" ") + msg

    # call_header 处理
    if call_header and hasattr(event, "group_id"):
        member_info = await self.get_group_member_info(
            group_id=event.group_id, user_id=event.user_id, no_cache=True
        )
        header_text = member_info.get("title") or member_info.get("card") or member_info.get("nickname")
        if header_text:
            msg = UniMessage.text(f">{header_text}\n") + msg

    # 检查消息中是否有 node_custom / forward（OneBot 专有）
    if _has_onebot_special_types(msg):
        # 回退到 OneBot 原生 API
        return await _onebot_fallback_send(self, target, msg)
    else:
        return await UniMessage.send(msg, target=target)  # 具体参数待查 Alconna 文档
```

**验证**：
- 群聊消息正常发送
- 私聊消息正常发送
- `at_sender` 功能正常
- `call_header` 功能正常
- 合并转发消息走回退路径，功能不受影响

---

### 阶段二：服务层改造（Phase 2 — Service Layer）

#### 步骤 6：重构 `hoshino/service.py`

**改动点**：

1. **`get_enable_groups()`** — 替换 `bot.get_group_list()` 为更通用的群列表获取方式
2. **`broadcast()`** — 替换 `bot.send_group_msg()` 为 `bot.send(event, msg)` 或 `UniMessage.send()`
3. **`check_service()`** — 替换 `event.dict()` 检查为鸭子类型 `getattr(event, "group_id", None)`

#### 步骤 7：重构 `hoshino/util/__init__.py`

**改动点**：

1. **`parse_qq()`** — `isinstance(event, GroupMessageEvent)` → `is_group_event(event)`
2. **`send_to_superuser()`** — `bot.send_private_msg()` → `UniMessage.send()` 或回退
3. **`send_segments()`** — 保留 OneBot 回退路径用于合并转发
4. **`construct_nodes()`** — 保留兼容（OneBot 专有）

---

### 阶段三：模块批量迁移（Phase 3 — Module Migration）

#### 步骤 8：模块级改动

机械替换模式：

| 旧 | 新 |
|---|---|
| `isinstance(event, GroupMessageEvent)` | `is_group_event(event)` |
| `isinstance(event, PrivateMessageEvent)` | `is_private_event(event)` |
| `from nonebot.adapters.onebot.v11.event import GroupMessageEvent` | 删除，用鸭子类型 |
| `bot.send_group_msg(group_id=gid, message=msg)` | `bot.send(event_target, msg)` |
| `from nonebot.adapters.onebot.v11.utils import unescape` | 用内置 `html.unescape` 或自实现 |

涉及模块清单：
- `hoshino/base/zai.py`
- `hoshino/base/test.py`
- `hoshino/base/image.py`
- `hoshino/base/black/__init__.py`
- `hoshino/base/broadcast.py`
- `hoshino/base/listenmeta.py`
- `hoshino/base/ls.py`
- `hoshino/base/service_manage/__init__.py`
- `hoshino/base/service_manage/util.py`
- `hoshino/modules/develop/echoandsay.py`
- `hoshino/modules/develop/healthchecker.py`
- `hoshino/modules/interactive/alisten/__init__.py`
- `hoshino/modules/interactive/alisten/util.py`
- `hoshino/modules/interactive/qbitorrent/__init__.py`
- `hoshino/modules/interactive/qbitorrent/utils.py`
- `hoshino/modules/information/bilireq/__init__.py`
- `hoshino/modules/information/pushlive/__init__.py`
- `hoshino/modules/information/weibo/internal/post_runtime.py`
- `hoshino/modules/steam/steam.py`

---

### 阶段四：入口改造 + 多平台（Phase 4 — Entry Point）

#### 步骤 9：重构 `run.py`

```python
import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotAdapter
# 未来可添加更多 adapter
# from nonebot.adapters.telegram import Adapter as TelegramAdapter

nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(OneBotAdapter)
# driver.register_adapter(TelegramAdapter)  # 未来

# ... 其余不变
```

**本阶段不强制添加新 adapter，仅确保架构支持。**

---

## 验证标准

### 功能回归检查清单

- [ ] 群聊消息正常收发
- [ ] 私聊消息正常收发
- [ ] `at_sender` 功能正常
- [ ] `call_header` 功能正常
- [ ] 命令系统（`.xxx`）正常工作
- [ ] Service 开关（enable/disable）正常
- [ ] 合并转发消息正常
- [ ] 图片消息正常
- [ ] 微博推送正常
- [ ] B站推送正常
- [ ] 自定义事件（reaction, emoji_like）正常
- [ ] 定时任务（APScheduler）正常
- [ ] 黑名单功能正常

### 技术验证

- [ ] `uv run ruff check .` 无新增错误
- [ ] 类型检查无回归（如项目后续引入 mypy/pyright）
- [ ] `uv run python run.py` 启动无报错

---

## 风险与缓解

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| Alconna UniMessage 不兼容某些 segment | 中 | PoC 首轮覆盖所有 segment 类型 |
| `forward`/`node_custom` 无等价 API | 中 | 保留回退路径，检测 OneBot adapter 时走原生 API |
| `Bot.send()` patch 行为变化 | 高 | 分步提交，每步可独立回滚 |
| 模块 `isinstance` 改动遗漏 | 低 | grep 全量扫描 + CI 检查 |
| 性能回归 | 低 | Alconna 在 UniMessage 层做了缓存优化，预期无影响 |

---

## 执行顺序与依赖

```
步骤1 (加依赖)
  └─ 步骤2 (message.py)
       ├─ 步骤3 (event.py)
       ├─ 步骤4 (permission.py)
       └─ 步骤5 (bootstrap.py) ← 关键路径，依赖 2+3+4
            └─ 步骤6 (service.py)
                 └─ 步骤7 (util/__init__.py)
                      └─ 步骤8 (模块批量)
                           └─ 步骤9 (run.py)
```

步骤 2-5 是基础设施，必须严格按序；步骤 6-7 可部分并行；步骤 8 是纯机械替换，可细分后并行处理。

# hoshino.nb2 架构文档

## 分层边界

```
┌─────────────────────────────────────────────────┐
│  hoshino/modules/        业务插件                 │
│  import: core, platform, command, content        │
├─────────────────────────────────────────────────┤
│  hoshino/content/        内容推送引擎              │
│  Post, PostMessage, PostQueue, UIDManager        │
│  import: platform                                 │
├─────────────────────────────────────────────────┤
│  hoshino/core/           核心基础设施              │
│  Service, hooks, config, permission, rule         │
│  import: platform, nonebot, alconna               │
├─────────────────────────────────────────────────┤
│  hoshino/command/        Alconna 命令 facade      │
│  Alconna, Args, CommandMeta, UniMsg, UniMessage   │
│  import: nonebot_plugin_alconna, nonebot          │
├─────────────────────────────────────────────────┤
│  hoshino/platform/       平台抽象层               │
│  ├─ common: event, depends, reaction, Target, send   │
│  ├─ ob11/: OneBot v11 隔离区                      │
│  ├─ telegram/: Telegram 隔离区                    │
│  └─ milky/: Milky QQNT 隔离区                     │
├─────────────────────────────────────────────────┤
│  nonebot_plugin_alconna                           │
│  UniMessage, Alconna, MsgTarget, UniMsg, Args     │
├─────────────────────────────────────────────────┤
│  nonebot2                                         │
│  Matcher, Bot(基类), Event(基类), Rule, Permission │
├─────────────────────────────────────────────────┤
│  nonebot-adapter-onebot (OB11)                    │
│  Message, MessageSegment, Adapter, Bot            │
├─────────────────────────────────────────────────┤
│  nonebot-adapter-telegram                         │
│  Message, MessageSegment, Adapter, Bot            │
├─────────────────────────────────────────────────┤
│  nonebot-adapter-milky                            │
│  Message, MessageSegment, Adapter, Bot            │
└─────────────────────────────────────────────────┘
```

## 目录结构

```
hoshino/
├── platform/
│   ├── ob11/              # 全部 OneBot 符号的唯一入口和出口
│   │   ├── types.py       # Message, MessageSegment, Bot, Adapter, Event, ...
│   │   ├── events.py      # GroupReactionEvent, GroupMsgEmojiLikeEvent
│   │   ├── event.py       # get_group_id, get_user_id, is_group_event, ...
│   │   ├── message.py     # image_segment, video_segment, text_message, ...
│   │   ├── bot.py         # get_group_list, send_group_forward, ...
│   ├── telegram/          # Telegram 类型和 helper 隔离区
│   │   ├── types.py       # Message, MessageSegment, Bot, Adapter, Event
│   │   ├── event.py       # chat/user/message accessors
│   │   └── bot.py         # get_chat_member, send/upload wrappers
│   ├── milky/             # Milky 类型和 helper 隔离区
│   │   ├── types.py       # Message, MessageSegment, Bot, Event
│   │   ├── event.py       # Milky data model -> common accessor
│   │   ├── reaction.py    # native reaction -> ReactionInfo
│   │   ├── message.py     # Milky-only message constructors
│   │   └── bot.py         # group/member/upload wrappers
│   ├── event.py           # adapter-aware event 分发
│   ├── depends.py         # uninfo-backed IDs + message DI
│   ├── permission.py      # uninfo-backed 权限
│   ├── reaction.py        # Reaction/ReactedMessage DI
│   ├── models.py          # adapter-neutral value objects
│   ├── message.py         # UniMessage send facade
│   ├── target.py          # Target 序列化, scope key
│   └── __init__.py        # common facade
├── content/                # 内容推送引擎
│   ├── engine.py          # Post, PostMessage, PostQueue, UIDManager
│   └── __init__.py        # 统一导出
├── command/               # Alconna facade（不含 OB11 depends）
│   └── __init__.py        # Alconna, Args, UniMsg, UniMessage, ...
├── core/                  # 核心基础设施
│   ├── service.py
│   ├── hooks.py
│   ├── config.py
│   ├── log.py
│   ├── permission.py
│   ├── rule.py
│   └── schedule.py
├── service.py             # → compat re-export（过渡期）
├── hooks.py               # → compat re-export（过渡期）
├── config.py              # → compat re-export（过渡期）
├── permission.py          # → compat re-export（过渡期）
├── log.py                 # → compat re-export（过渡期）
├── schedule.py            # → compat re-export（过渡期）
├── types.py               # 纯 NoneBot 类型，零 OneBot
├── modules/               # 业务插件
├── base/                  # 内置服务
└── util/                  # 工具函数
```

## Import 约束

### 允许的 import 方向

| 层 | 可 import |
|---|---|
| `modules/` | core, platform, command, nonebot_plugin_alconna |
| `core/` | platform, nonebot, nonebot_plugin_alconna |
| `command/` | nonebot_plugin_alconna, nonebot（不能 import platform/ob11） |
| `platform/common` | nonebot, nonebot_plugin_alconna.uniseg, platform adapter modules |
| `platform/ob11/` | nonebot.adapters.onebot.v11（OneBot 符号唯一入口） |
| `platform/telegram/` | nonebot.adapters.telegram（Telegram 符号唯一入口） |
| `platform/milky/` | nonebot.adapters.milky（Milky 符号唯一入口） |

### 禁止

- `modules/` 不能直接 import `nonebot.adapters.onebot.v11`
- `modules/` 不能直接 import `nonebot.adapters.milky`
- `modules/` 不能直接 import `hoshino.message` 或 `hoshino.event`（过渡期兼容除外）
- `command/` 不能 import `platform/ob11`
- `hoshino/types.py` 只能在 `TYPE_CHECKING` 下引用 adapter 消息类型
- 业务代码不能 `isinstance(event, GroupMessageEvent)` — 用 `is_group_event(event)`
- reaction handler 不能接收 adapter Event — 用 `Reaction()` / `ReactedMessage()` DI

### 允许的特殊例外

- `hoshino/bootstrap.py` — Bot.send() monkey-patch 需要 OneBot Bot 类型
- `hoshino/base/image.py` — legacy OB11 Message 输出路径（reaction 已走公共 DI）
- `hoshino/base/test.py` — 测试代码

## 验证脚本

```bash
# OneBot 泄漏检查 — 只允许 platform/ob11 + bootstrap.py
rg "nonebot\.adapters\.onebot" hoshino/ --glob '*.py' -l \
  | grep -v "platform/ob11" | grep -v "bootstrap.py" | grep -v "base/image.py" \
  | grep -v "base/test.py"

# 旧入口淘汰进度
rg "from hoshino\.(types|message|event) import" hoshino/ --glob '*.py' -c

# 模块层不得 import OneBot
rg "from nonebot\.adapters\.onebot" hoshino/modules/ --glob '*.py'
# 预期输出：空

# 模块层不得 import Telegram adapter
rg "from nonebot\.adapters\.telegram" hoshino/modules/ --glob '*.py'
# 预期输出：空

# 模块层不得 import Milky adapter
rg "from nonebot\.adapters\.milky" hoshino/modules/ --glob '*.py'
# 预期输出：空
```

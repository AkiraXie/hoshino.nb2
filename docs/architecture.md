# hoshino.nb2 架构文档

## 分层边界

```
┌─────────────────────────────────────────────────┐
│  hoshino/modules/        业务插件                 │
│  import: core, platform, command                  │
├─────────────────────────────────────────────────┤
│  hoshino/core/           核心基础设施              │
│  Service, hooks, config, permission, rule         │
│  import: platform, nonebot, alconna               │
├─────────────────────────────────────────────────┤
│  hoshino/command/        Alconna 命令 facade      │
│  Alconna, Args, CommandMeta, UniMsg               │
│  import: nonebot_plugin_alconna, nonebot          │
├─────────────────────────────────────────────────┤
│  hoshino/platform/       平台抽象层               │
│  ├─ common:  Target, send, scope key              │
│  │   import: nonebot, nonebot_plugin_alconna      │
│  └─ ob11/:   OneBot v11 隔离区                    │
│      import: nonebot.adapters.onebot.v11          │
├─────────────────────────────────────────────────┤
│  nonebot_plugin_alconna                           │
│  UniMessage, Alconna, MsgTarget, UniMsg, Args     │
├─────────────────────────────────────────────────┤
│  nonebot2                                         │
│  Matcher, Bot(基类), Event(基类), Rule, Permission │
├─────────────────────────────────────────────────┤
│  nonebot-adapter-onebot (OB11)                    │
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
│   │   └── bot.py         # get_group_list, send_group_forward, ...
│   ├── send.py            # to_unimessage, send_to_event, send_to_target
│   └── target.py          # Target 序列化, scope key
│   └── __init__.py        # compat re-export（过渡期）
├── command/               # Alconna facade（下一步）
├── core/                  # 核心基础设施（下一步）
│   ├── service.py
│   ├── hooks.py
│   ├── config.py
│   ├── bootstrap.py
│   ├── permission.py
│   └── rule.py
├── types.py               # 纯 NoneBot 类型，零 OneBot
├── message.py             # → compat re-export（过渡期，后续删除）
├── event.py               # → compat re-export（过渡期，后续删除）
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
| `platform/common` (send.py, target.py) | nonebot, nonebot_plugin_alconna.uniseg（不能 import platform/ob11） |
| `platform/ob11/` | nonebot.adapters.onebot.v11（OneBot 符号唯一入口） |

### 禁止

- `modules/` 不能直接 import `nonebot.adapters.onebot.v11`
- `modules/` 不能直接 import `hoshino.message` 或 `hoshino.event`（过渡期兼容除外）
- `platform/common` 不能 import `platform/ob11`
- `command/` 不能 import `platform/ob11`
- `hoshino/types.py` 不能重新导出 OneBot 类型
- 业务代码不能 `isinstance(event, GroupMessageEvent)` — 用 `is_group_event(event)`

### 允许的特殊例外

- `hoshino/bootstrap.py` — Bot.send() monkey-patch 需要 OneBot Bot 类型
- `hoshino/base/image.py` — 自定义事件（GroupReactionEvent 等）处理
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
```

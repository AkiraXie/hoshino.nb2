# Milky adapter

## 配置

项目同时注册 OneBot V11、Telegram 与 Milky adapter。Milky 正向连接需要事件
WebSocket 和 HTTP API 指向同一个协议端：

```ini
milky_clients=[{"host":"127.0.0.1","port":3000,"access_token":"","secure":false}]
```

也可以使用 webhook 反向上报：

```ini
milky_webhook={"host":"127.0.0.1","port":3000,"access_token":"","secure":false}
```

协议端必须实现 Milky 1.2 API。`nonebot-plugin-uninfo>=0.11.1` 是必要依赖；旧的
0.6.10 没有 Milky fetcher，`GroupID()`、`SenderID()` 和成员权限无法跨平台工作。

## 平台边界

Milky 类型、事件访问和 Bot API wrapper 位于 `hoshino/platform/milky/`。业务代码
继续使用公共出口：

- 身份与权限：`GroupID()`、`SenderID()`、`GroupMemberName()` 和 Uninfo permission
- 消息：`UniMessage`、`send_to_event()`、`send_to_target()`
- reaction：`Reaction()`、`ReactedMessage()` 和 `reaction_event_rule`
- 群 API：`get_group_list()`、`get_group_member_info()`、`upload_group_file()`

业务 reaction handler 不接收平台 Event 或直接调用 Bot API。统一对象字段为：

| 字段 | 含义 |
|---|---|
| `face_id` | 表情 ID，始终保留为字符串 |
| `is_add` | 添加为 `True`，取消为 `False` |
| `message_id` | 被回应的群消息序列号 |
| `group_id` | 群号 |
| `user_id` | 操作者 QQ 号 |
| `reaction_type` | `face` 或 `emoji` |

### Reaction 映射

| 来源事件 | `face_id` | `is_add` | `reaction_type` |
|---|---|---|---|
| OB11 `GroupReactionEvent` | `code` | `sub_type == "add"` | `face` |
| OB11 `GroupMsgEmojiLikeEvent` | `likes[0].emoji_id` | `True` | `emoji` |
| Milky `GroupMessageReactionEvent` | `data.face_id` | `data.is_add` | 原值 |

LLOneBot 的 `GroupMsgEmojiLikeEvent` 上报当前点赞集合，不提供独立的取消动作，因此
只能规范化为添加。公共 image/Weibo reaction 消费者会忽略所有取消事件。

## 从 OB11 切换的差异

| 类别 | OB11 | Milky | 当前处理 |
|---|---|---|---|
| 群消息事件 | 顶层 `group_id/user_id/message_id` | `data.peer_id/sender_id/message_seq` | platform accessor / Uninfo DI |
| reaction | 两个协议端扩展事件 | 原生 `GroupMessageReactionEvent` | `ReactionInfo` DI |
| 获取消息 | `get_msg(message_id)` | `get_message(scene, peer_id, seq)` | `ReactedMessage()` DI |
| 群列表/成员 | dict API | Pydantic model API | wrapper 统一为 dict |
| 发送群消息 | `send_group_msg` | `send_group_message` | `UniMessage` exporter |
| @ 消息段 | `at` | `mention` | `UniMessage.at()` |
| 回复 ID | 全局样式 `message_id` | 会话内 `message_seq` | reaction 同时保留 `group_id` |
| 群文件 | `upload_group_file(file=...)` | `upload_group_file(path=...)` | wrapper |

## 尚未兼容的边界

1. `send_group_forward()` / `send_private_forward()` 的旧 helper 仍接收 OB11
   constructed node。Milky 协议本身支持 forward segment，但当前 common helper 会明确
   抛出 `NotImplementedError`；调用方应迁移到 `UniMessage.reference()`。
2. OB11 CQ 字符串、原生 `Message`/`MessageSegment` 和 `auto_escape` 语义不能直接传给
   Milky。插件必须构造 `UniMessage`。
3. `platform/ob11/bootstrap.py` 的 `Bot.send()` patch（`call_header` 等 legacy 行为）只在
   OB11 注册时应用；Milky 使用 adapter 原生 `Bot.send()` 和 UniMessage exporter。
4. 直接调用 `get_msg`、`send_group_msg`、`get_forward_msg` 等 OB11 API 的测试或 legacy
   helper 仍是 OB11-only。当前 reaction 原消息获取、群列表、成员信息和群文件已经有
   common wrapper；其余直接 API 需要按实际业务逐项迁移。
5. Milky 的消息 ID 是会话内序列号。只持久化 `message_id` 而丢弃群/会话 ID 的业务
   记录无法保证跨群唯一，持久化时应同时保存 Target 或 `group_id`。

## 验证范围

NoneBug 覆盖 Milky 消息 accessor、native/Alconna 命令规则、Uninfo 身份与管理员权限、
Milky referenced-message 获取，以及 OB11 两类 reaction 与 Milky reaction 进入同一业务
规则。测试使用协议模型和 API mock，没有连接真实 QQNT/Milky 协议端；上线前仍需验证
鉴权、WebSocket/webhook 连通、媒体临时 URL 和真实 forward payload。

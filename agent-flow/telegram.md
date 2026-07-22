# Telegram adapter

## 配置

项目同时注册 OneBot V11 与 Telegram adapter。Telegram bot 在 `.env.prod` 中配置：

```ini
telegram_bots=[{"token":"123456:ABC...","is_webhook":false}]
# telegram_proxy="http://127.0.0.1:7890"
```

`is_webhook=false` 使用 polling；webhook 模式还需要配置 `telegram_webhook_url`。

Telegram 事件、消息和 Bot API 位于 `hoshino/platform/telegram/`。跨平台会话 ID、成员名和权限由 `nonebot-plugin-uninfo` 支撑的 `hoshino.platform.depends` / `hoshino.platform.permission` 提供；业务插件不要直接 import adapter 类型。

项目使用 `nonebot-plugin-uninfo>=0.11.1`；该版本兼容当前 Pydantic，并同时提供
OneBot V11、Telegram 与 Milky fetcher。业务 handler 仍优先使用公共 DI，以避免
adapter 事件模型泄漏。

## 兼容性判断

不要维护按插件计数的静态兼容矩阵；插件和测试会持续变化。判断某个插件是否兼容时，
检查它是否只使用公共 `platform`/`command` facade，并通过 Telegram 事件分发与发送测试。

通常可跨平台的能力包括 Alconna/native message matcher、平台 scope 的 Service 开关、
Uninfo 身份/权限、UniMessage 文本和媒体发送、Target 持久化，以及公共 `Reaction()` /
`ReactedMessage()` normalization。以下能力需要显式降级或平台专用实现：全群/好友枚举、
原生 constructed forward 和直接 OB11 Bot API。

## 平台限制

- Telegram Bot API 不能列出机器人加入的所有聊天，因此 common `get_group_list()` 对 Telegram 返回空列表。
- uninfo 对 Telegram 的 `query_scenes/query_users/query_members` 也未实现；其短期缓存不能替代全 chat 枚举。
- Telegram 没有 OB11/Milky 的 constructed forward node 语义；
  `send_group_forward()` / `send_private_forward()` 会按节点顺序逐条发送内容。
- Telegram reaction update 不包含原消息正文，Bot API 也没有按 message ID 取回消息的接口；
  `ReactedMessage()` 因此返回 `None`。需要跨聊天转发时使用 `forward_reacted_message()`，它会调用
  Telegram 原生 `forwardMessage`，不依赖本地消息映射、原消息缓存或 reaction 幂等数据库。
  机器人向用户私聊前，用户必须先向机器人发送消息或 `/start`。
- Telegram admin/owner 权限通过 `get_chat_member` 在线查询；API 查询失败时权限检查返回 false。
- `upload_group_file()` 在 Telegram 映射为 `sendDocument`。

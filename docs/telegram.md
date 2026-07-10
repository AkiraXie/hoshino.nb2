# Telegram adapter

## 配置

项目同时注册 OneBot V11 与 Telegram adapter。Telegram bot 在 `.env.prod` 中配置：

```ini
telegram_bots=[{"token":"123456:ABC...","is_webhook":false}]
# telegram_proxy="http://127.0.0.1:7890"
```

`is_webhook=false` 使用 polling；webhook 模式还需要配置 `telegram_webhook_url`。

Telegram 事件、消息、Bot API 和 DI helper 位于 `hoshino/platform/telegram/`；业务插件应使用 `hoshino.platform`、`hoshino.platform.depends`、`hoshino.platform.permission` 和 `UniMessage`，不要直接 import adapter 类型。

## 当前兼容性

以下统计按 30 个 Hoshino plugin entrypoint 计算。结论基于 import/API 边界审计和 Telegram 事件、Target、scope、UniMessage smoke；未使用真实 Telegram token 做在线 API 测试。

### 可直接使用（21）

- `black`, `cookies`, `help`, `zai`
- `utils`, `bilireq`, `pushlive`, `resolve`
- `alisten`, `chooseone`, `emojimix`, `foods`, `QA`, `qbitorrent`, `steam`
- `b64`, `nbnhhsh`
- `echoandsay`
- `bihua`, `coser`, `dice`

订阅类插件通过 `telegram:<chat_id>` service scope 恢复定时推送；目标消息由 UniMessage Telegram exporter 发送。

### 部分可用（6）

| Plugin | Telegram 可用部分 | 限制 |
|---|---|---|
| `listenmeta` | 生命周期通知机制 | `superusers` 是跨 adapter 的全局 ID 列表，需自行配置 Telegram chat/user ID |
| `ls` | matcher/service 列表 | Telegram Bot API 不能枚举全部群聊或好友 |
| `service_manage` | 当前 Telegram 群内 enable/disable/lssv | 私聊中跨群管理依赖群列表，不可用 |
| `weibo` | 命令、订阅、定时推送 | 表情回应收藏使用 OB11 `GroupMsgEmojiLikeEvent` |
| `healthchecker` | Bot 存活检查 | 无法用群列表 API 验证 Telegram chat 权限 |
| `server_info` | `状态` 命令 | 上线主动通知受全局 `superusers` ID 限制 |

### OB11-only（3）

| Plugin | 原因 |
|---|---|
| `broadcast` | 依赖枚举机器人加入的全部群，Telegram Bot API 不提供该能力 |
| `image` | 依赖 OB11 Message/MessageSegment 和自定义 reaction 事件 |
| `test` | 直接测试 OB11 forward message API |

## 平台限制

- Telegram Bot API 不能列出机器人加入的所有聊天，因此 common `get_group_list()` 对 Telegram 返回空列表。
- Telegram 没有 OB11 的 constructed forward node 语义；`send_group_forward()` / `send_private_forward()` 会明确抛出 `NotImplementedError`。
- Telegram admin/owner 权限通过 `get_chat_member` 在线查询；API 查询失败时权限检查返回 false。
- `upload_group_file()` 在 Telegram 映射为 `sendDocument`。

# Milky 开发指南

编写或修改涉及 Milky adapter 的代码时，遵循以下规则。

## 核心原则

- **不直接 import Milky 类型**。所有 adapter 交互通过 `hoshino/platform/milky/` 隔离区，业务代码只用公共出口（`GroupID()`、`UniMessage`、`send_to_event()` 等）。
- **消息 ID 是会话内序列号**，不跨群唯一。持久化时必须同时保存 Target 或 `group_id`，不能只存 `message_id`。
- **forward ID 不可跨 adapter 复用**。跨 adapter 发送合并转发应提供 constructed node 内容，不要传递其他 adapter 的 forward ID。

## Reaction 处理

reaction handler 使用 `Reaction()` / `ReactedMessage()` DI，不接收平台 Event。统一字段：

| 字段 | 说明 |
|---|---|
| `face_id` | 表情 ID（字符串） |
| `is_add` | True=添加，False=取消 |
| `message_id` | 被回应的消息序列号 |
| `group_id` | 群号 |
| `reaction_type` | `face` 或 `emoji` |

注意：LLOneBot 的 emoji like 事件只能规范化为添加；OB11 CQ 字符串和原生 Message 不能直接传给 Milky，新插件应构造 `UniMessage`。

## 测试要求

Milky 行为测试必须走完整 dispatch 链路，具体要求见 `milky-plugin-test-protocol.md`。要点：

1. 用 `MilkyAdapter.json_to_event()` 构造事件，每个用例用唯一 `message_seq`
2. 调用 `await bot.handle_event(event)`（触发 reply/mention/to_me 预处理）
3. stub HTTP 边界并断言 action name + target ID + message payload
4. 不使用真实凭据或连接真实协议端

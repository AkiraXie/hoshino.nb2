# Telegram 开发指南

编写或修改涉及 Telegram adapter 的代码时，遵循以下规则。

## 核心原则

- **不直接 import Telegram 类型**。业务代码只用公共出口（`GroupID()`、`UniMessage`、`send_to_event()` 等）。
- **无法枚举所有聊天**。`get_group_list()` 对 Telegram 返回空列表；uninfo 的 `query_scenes/query_users/query_members` 也未实现。依赖全群列表的功能必须明确降级。
- **没有 constructed forward**。`send_group_forward()` / `send_private_forward()` 会按节点顺序逐条发送，不是原生合并转发。

## Reaction 限制

- `ReactedMessage()` 返回 `None`（Telegram reaction update 不含原消息正文，Bot API 无按 message ID 取回消息的接口）
- 需要跨聊天转发被回应消息时，用 `forward_reacted_message()`（调用原生 `forwardMessage`）
- 机器人向用户私聊前，用户必须先向机器人发消息或 `/start`

## 其他注意

- admin/owner 权限通过 `get_chat_member` 在线查询；API 失败时权限检查返回 false
- `upload_group_file()` 映射为 `sendDocument`
- 判断插件兼容性时，检查它是否只用公共 facade 并通过 Telegram 事件分发测试；不要维护静态兼容矩阵

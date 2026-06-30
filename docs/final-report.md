# hoshino.nb2 OneBot 解耦 — 最终报告

## 执行日期

2026-06-30

## 原始目标

将 hoshino.nb2 从 OneBot v11 强耦合中解耦，用 `nonebot-plugin-alconna` 的 `UniMessage` / `Target` 替代 OneBot 原生调用，使 hoshino 层成为适配器无关的抽象。

## 完成情况 vs Plan

### 阶段一：基础设施 ✅

| 计划 | 实际 | 状态 |
|---|---|---|
| 添加 alconna 依赖 | `nonebot-plugin-alconna>=0.50.0` (锁定 0.59.4) | ✅ |
| 重构 message.py | 新增 `hoshino/platform/message.py` facade，旧 `hoshino/message.py` 不动 | ✅ |
| 重构 event.py | 新增 `hoshino/platform/event.py` helper，旧 `hoshino/event.py` 保留类型导出 | ✅ |
| 重构 permission.py | 完全脱离 OneBot `GROUP`/`GROUP_ADMIN`，改为鸭子类型 Permission | ✅ |
| 重构 bootstrap.py | 未改 — 作为 compat 边界保留 | 🔒 |

### 阶段二：服务层改造 ✅

| 计划 | 实际 | 状态 |
|---|---|---|
| service.py — check_service | `event.dict()` → `get_group_id(event)` | ✅ |
| service.py — broadcast | `send_group_msg()` → `send_to_target()` | ✅ |
| service.py — Service scope | 新增 scope key 系统（非破坏性扩展，旧 group_id 并存） | ✅ |
| util/__init__.py | `send_private_msg()` → `send_to_target()`，`MessageEvent` → `Event` | ✅ |

### 阶段三：模块批量迁移 ✅（超出计划）

| 计划 | 实际 | 状态 |
|---|---|---|
| 19 个模块的 `isinstance`/`send_group_msg` 替换 | 完全迁移 + 额外做了： | |
| | — `platform/bot.py` 包装 `get_group_list`/`get_group_member_info`/forward | ✅ |
| | — `platform/event.py` helper（`get_group_id`, `get_user_id`, `get_plaintext` 等） | ✅ |
| | — `platform/message.py` 包装器（`image_segment`, `text_message` 等） | ✅ |
| | — information 管线（weibo/bilireq/pushlive/douyin/xhs）消息构造全部平台化 | ✅ |
| | — `PostMessage` 数据契约保持纯数据（无 OneBot 类型） | ✅ |

### 阶段四：入口改造 ✅

| 计划 | 实际 | 状态 |
|---|---|---|
| run.py 注册 alconna 插件 | `nonebot.load_plugin("nonebot_plugin_alconna")` | ✅ |
| 多 adapter | 架构就绪，未实际添加其他 adapter | 🔜 |

## Gap 分析

### 已完成的（超出原 plan）

1. **platform 层比计划更完整** — 原 plan 只有 message.py 替换，实际构建了 event/bot/message/target 四个子模块的完整 facade
2. **模块迁移比计划更彻底** — 原计划只做 `isinstance` 替换，实际连 DB 存储（`target_data` 列）、消息构造管线、`PostMessage` 数据契约都做了平台化
3. **Service scope 基础设施** — 原计划延后的 scope 重设计，实际以非破坏性扩展方式完成（`enable_scope`/`disable_scope` 与旧 `enable_group` 并存）
4. **代码质量修** — `except BaseException` → `Exception`、DB `create_all` 延迟到启动钩子、类型标注统一

### 未完成的（有意保留）

| 项目 | 原因 | 建议 |
|---|---|---|
| `bootstrap.py` 的 `Bot.send()` patch | 包含 `call_header`/`at_sender`/合并转发等 OneBot 专有能力 | 等接入第二个 adapter 时再重构 |
| 自定义事件（`GroupReactionEvent` 等） | 来自 Lagrange/LLOneBot 的协议扩展 | 作为 compat 边界保留 |
| 合并转发（`construct_nodes`/`node_custom`） | `send_group_forward_msg` 是 OneBot 专有 API | 保留在 `platform/bot.py` 包装器内 |
| Service scope 完整重设计 | 需要数据迁移 + API 变更 | 基础设施已铺（`event_scope_key` 等），API 层延后 |
| 多 adapter 实际接入 | 未添加 Telegram/Discord adapter | 架构已支持，按需接入 |

### Gap 结论

**解耦完成度：~85%**。业务代码已零接触 OneBot 概念。保留的 15% 是 compat 边界（bootstrap patch + 自定义事件 + 合并转发），这些只有在真正接入第二个 adapter 时才有动力重构。

## Alconna 利用度评估

### 已充分利用

| Alconna 能力 | 使用位置 |
|---|---|
| `UniMessage` — 通用消息类型 | `to_unimessage()` + `send_to_event()` |
| `Target` — 通用目标抽象 | `target_from_event()` + `send_to_target()` + DB 持久化 |
| `FallbackStrategy.rollback` — 序列化失败回退 | `send_to_event_or_fallback()` |
| `UniMessage.send()` — 通用发送 | `send_to_event()` / `send_to_target()` |

### 未充分利用

| Alconna 能力 | 原因 |
|---|---|
| `Alconna` 命令框架 | hoshino 有自己的 `Service.on_command()` 体系，无需替换 |
| `AlconnaMatcher` | 同上，`MatcherWrapper` 已满足需求 |
| `Arparca` 参数解析 | 项目使用 NoneBot 原生命令解析 |

### 评估结论

Alconna 的**消息抽象层**（UniMessage + Target）已被充分利用。**命令框架层**（Alconna/Arparca）不需要替换，hoshino 的 Service 体系已经工作良好。这是合理的取舍 — 用 Alconna 做平台解耦，用自己的 Service 做业务抽象。

## 新插件可以用 Alconna 直接写吗？

**可以**。在当前架构下，新插件有两种写法：

1. **使用 hoshino Service 体系（推荐）** — 通过 `Service.on_command()` 注册，用 `bot.send(event, msg)` 或 `send_to_event()` 发送
2. **使用 Alconna 原生** — 直接从 `nonebot_plugin_alconna` 导入 `Alconna`、`UniMessage` 等，用 `hoshino.platform` 的 helper 发送

详见 `docs/plugin-guide.md`。

## 统计

- **Commits**：12（从 `194d819` 到 `106381c`）
- **文件变更**：~50 files，+1500/-400 lines
- **新增模块**：`hoshino/platform/`（event.py, bot.py, message.py, target.py）
- **修改模块**：service.py, util/__init__.py, permission.py, types.py, event.py, run.py
- **迁移模块**：base/（5 个），information/（10 个），interactive/（4 个），tools/（2 个），steam/
- **DB 迁移**：3 个 SQLite 表新增 `target_data` 列（非破坏性 ALTER TABLE）
- **验证**：`uv run ruff check .` 通过，启动烟测通过（9223 端口）

## 残留 OneBot 导入分布

| 类别 | 文件 | 数量 |
|---|---|---|
| 核心类型（message.py, event.py, types.py） | 3 | 保留 |
| bootstrap patch | 1 | compat 边界 |
| platform 包装器内部 | 2 | 封装在 platform/ |
| 测试代码 | 1 | test.py |
| 工具函数（unescape） | 1 | 可替换 |

# 架构指南

编写代码时遵循以下分层和 import 约束。插件开发示例见 `docs/plugin-development.md`。

## 分层边界

```
┌─────────────────────────────────────────────────┐
│  hoshino/modules/        业务插件                 │
│  import: core, platform, command, content        │
├─────────────────────────────────────────────────┤
│  hoshino/content/        内容推送引擎              │
│  import: platform                                │
├─────────────────────────────────────────────────┤
│  hoshino/core/           Service, hooks, config   │
│  import: platform, nonebot, alconna              │
├─────────────────────────────────────────────────┤
│  hoshino/command/        Alconna facade           │
│  import: nonebot_plugin_alconna                  │
├─────────────────────────────────────────────────┤
│  hoshino/platform/       平台抽象层               │
│  ├─ common / ob11/ / telegram/ / milky/          │
├─────────────────────────────────────────────────┤
│  nonebot2 + adapters (OB11 / Telegram / Milky)   │
└─────────────────────────────────────────────────┘
```

## 目录结构

```
hoshino/
├── platform/          # adapter-neutral 事件/DI/消息/Target + ob11/telegram/milky 隔离区
├── content/           # Post, PostMessage, PostQueue, UIDManager
├── command/           # Alconna, Args, UniMessage facade
├── core/              # Service, matcher, hooks, config, permission, schedule
├── ai/                # AI 基建包（非插件，详见 ai.md）
├── modules/           # 业务插件（含 ai/：chat、ai_admin、task_commands）
├── base/              # 始终加载的内置服务
├── service.py         # Service/MatcherWrapper 兼容出口
├── types.py           # 纯 NoneBot 类型
└── util/              # 工具函数
```

各子包的详细文件职责见 [AI 模块文档](ai.md) 和 [插件开发指南](../docs/plugin-development.md)。

## Import 约束

### 允许

| 层 | 可 import |
|---|---|
| `modules/` | core, platform, command, nonebot_plugin_alconna |
| `core/` | platform, nonebot, nonebot_plugin_alconna |
| `command/` | nonebot_plugin_alconna, nonebot |
| `ai/` | platform, nonebot, pydantic-ai |
| `platform/<adapter>/` | 对应 adapter（该 adapter 符号唯一入口） |

### 禁止

- `modules/` 不能直接 import 任何 adapter 包
- 业务代码不能用 `isinstance(event, GroupMessageEvent)` — 用 `is_group_event()`
- reaction handler 不能接收 adapter Event — 用 `Reaction()` / `ReactedMessage()` DI

### 例外

- `bootstrap.py` — 注册 adapter
- `platform/ob11/bootstrap.py` — OB11 legacy patch
- `base/image.py` — legacy OB11 Message 输出

## 验证脚本

```bash
# adapter 泄漏检查
rg "nonebot\.adapters\.onebot" hoshino/ --glob '*.py' -l \
  | grep -v "platform/ob11" | grep -v "base/image.py" | grep -v "base/test.py"

# 模块层不得 import adapter
rg "from nonebot\.adapters\.(onebot|telegram|milky)" hoshino/modules/ --glob '*.py'
# 预期输出：空
```

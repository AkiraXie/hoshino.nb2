# Hoshino.nb2 插件开发指南

本文面向 Hoshino.nb2 插件开发者，描述当前插件目录、Service API、命令注册、依赖注入、
跨平台消息发送、生命周期和测试方法。公共 API 以当前代码为准；涉及 adapter 细节时继续
阅读 [Milky](../agent-flow/milky.md)、[Telegram](../agent-flow/telegram.md) 和
[架构文档](../agent-flow/architecture.md)。

## 1. 开发前准备

```bash
uv sync
cp .env.prod.example .env.prod
```

插件开发通常只需要本地测试，不需要连接真实协议端。运行机器人：

```bash
uv run python run.py
```

仓库中的自动化 Agent 必须先阅读根目录 `AGENTS.md`。

## 2. 插件放在哪里

基础插件位于 `hoshino/base/`，启动时始终加载。普通业务插件放在：

```text
hoshino/modules/
├── information/    信息获取、解析、订阅和推送
├── interactive/    交互工具和外部服务
├── develop/        运维与开发工具
├── tools/          小型通用工具
└── entertainment/  娱乐功能
```

`.env.prod` 的 `modules` 决定加载哪些分类。新增插件应放入语义最接近的现有分类，不要为单个
插件创建新的顶级分类。

插件可使用以下公共层：

```text
hoshino.core       Service、权限、hook、调度
hoshino.command    Alconna、Args、UniMessage 等命令 facade
hoshino.platform   adapter-neutral 事件、DI、消息、Target 和 Bot API
hoshino.content    内容推送模型与队列
hoshino.ai         AI 能力基建包（Agent/persona/provider/工具/task，非插件）
```

业务插件不得直接 import `nonebot.adapters.onebot.v11`、`nonebot.adapters.milky` 或
`nonebot.adapters.telegram`。adapter-specific 类型和转换应留在 `hoshino/platform/<adapter>/`。

`hoshino.ai` 是 AI 能力基建包（不被 `nonebot.load_plugins` 扫描），AI 功能集中在
`hoshino/modules/ai/` 三个插件里（chat `#` 对话、ai_admin 管理、task_commands 后台
任务）。需要 AI 能力的插件用 `from hoshino.ai.<submodule>` 直连；模块结构、pydantic-ai
能力使用与自有扩展见 [AI 模块文档](../agent-flow/ai.md)，工具注册表与门控见
[AI 工具系统](../agent-flow/ai-tools.md)。

## 3. 最小插件

```python
from hoshino.command import Alconna, Args, UniMessage
from hoshino.core.service import Service

sv = Service("hello")


@sv.on_alconna(Alconna("hello", Args["name?", str]))
async def _(name: str | None = None):
    text = f"Hello, {name}" if name else "Hello!"
    await UniMessage.text(text).send()
```

模块 import 时会创建 `Service` 并注册 matcher。不要在 import 阶段发起网络请求、创建数据库
表、读取必须存在的外部资源或启动长期任务。

## 4. Service

```python
from hoshino.core.service import Service
from hoshino.platform.permission import ADMIN

sv = Service(
    "my_plugin",
    manage_perm=ADMIN,
    enable_on_default=True,
    visible=True,
)
```

参数含义：

| 参数 | 说明 |
| --- | --- |
| `name` | 全局唯一的 Service 名，也是日志和配置文件名 |
| `manage_perm` | 谁能管理 Service，可用 `ADMIN`、`OWNER`、`SUPERUSER` |
| `enable_on_default` | 没有显式 scope 状态时是否启用 |
| `visible` | 是否出现在服务列表和帮助信息中 |
| `config_type` | 可选的配置结构类型，通常是带默认值的 dataclass |

Service 开关按 adapter scope 保存到 `data/service/<name>.json`。业务代码不要自行维护裸群号
开关；使用 Service 自动注入的 rule，或者使用 `event_scope_key()` / `target_scope_key()`。

每个 Service 可在 `hoshino/service_config/<name>.json` 保存业务配置。新插件推荐绑定
一个带默认值的 dataclass；Service 初始化时会生成默认 JSON，之后 `get_config()` 直接返回
这个类型：

```python
from dataclasses import dataclass

from hoshino.core.service import Service


@dataclass(frozen=True, slots=True)
class WeatherConfig:
    api_key: str = ""
    timeout_seconds: float = 10.0


sv = Service("weather", config_type=WeatherConfig)
config = sv.get_config()
```

未绑定 `config_type` 的旧 Service 仍返回字典：

```python
config = sv.get_config()
```

无文件或读取失败时返回空字典。绑定结构类型后，JSON 格式或字段类型错误会抛出带文件路径的
配置错误。敏感凭据优先放环境变量，不要提交到配置 JSON。

## 5. 注册命令与 Matcher

### 5.1 Alconna 命令

新命令优先使用 `on_alconna()`：

```python
from hoshino.command import Alconna, Args, CommandMeta, UniMessage


@sv.on_alconna(
    Alconna("weather", Args["city", str]),
    aliases=("天气",),
    meta=CommandMeta(
        description="查询城市天气",
        usage="天气 <城市>",
        example="天气 上海",
    ),
)
async def _(city: str):
    await UniMessage.text(f"正在查询 {city}").send()
```

`on_command()` 是兼容入口，内部也使用 Alconna。维护旧插件时可保留，新插件应直接声明
Alconna，以便使用参数、选项和子命令。

### 5.2 Native message matcher

Service 提供以下 message matcher 工厂：

- `on_startswith()`
- `on_endswith()`
- `on_fullmatch()`
- `on_regex()`
- `on_message()`

```python
from hoshino.command import UniMessage


@sv.on_regex(r"^roll\s+\d+$", only_group=False)
async def _():
    await UniMessage.text("matched").send()
```

`on_keyword()` 走 Alconna delegate；如果关键词为空则退化为 `on_message()`。matcher 工厂会
自动组合 Service 开关、`only_to_me`、`only_group` 和传入的额外 rule。

### 5.3 Notice 与 request

```python
from hoshino.core.rule import Rule


@sv.on_notice(rule=Rule(my_notice_rule))
async def _():
    ...
```

`on_notice()` 和 `on_request()` 同样注入 Service 开关。跨平台 notice 应基于公共 value object
或 DI；不要让业务 handler 接收 adapter-specific event 类型。

### 5.4 MatcherWrapper

Service 工厂返回 `MatcherWrapper`；Alconna 入口返回其子类 `AlconnaMatcherWrapper`。
wrapper 提供：

- `handle()`、`receive()`、`got()`
- `send()`、`finish()`、`reject()`、`pause()`
- `set_arg()`、`get_arg()`
- Alconna 专用的 `assign()`、`dispatch()`、`got_path()`、`reject_path()`

```python
matcher = sv.on_fullmatch("confirm")


@matcher.handle()
async def _():
    await matcher.finish("done")
```

一般消息回复优先使用 `UniMessage.send()`；需要 wrapper 的会话控制语义时再调用
`finish()`、`reject()` 或 `pause()`。

## 6. Handler 依赖注入

不要在 handler 中反复解析 adapter event。公共 DI 位于 `hoshino.platform.depends`：

| DI | 返回值 | 用途 |
| --- | --- | --- |
| `GroupID()` | `int | None` | 当前群/聊天 ID |
| `SenderID()` | `int | None` | 发送者 ID |
| `PlainText()` | `str` | 完整消息纯文本 |
| `ParamMessage()` | `UniMessage` | 命令参数对应的消息 |
| `ParamText()` | `str` | 命令参数纯文本 |
| `EventMessage()` | adapter message | 原始事件消息，仅在公共抽象不足时使用 |
| `RawMessage()` | `str` | 原始消息字符串 |
| `ReplyMessage()` | message 或 `None` | 被回复消息 |
| `MessageID()` | `int | None` | 当前消息 ID/sequence |
| `GroupMemberName()` | `str` | Uninfo 解析的成员显示名 |
| `LightAppJsonPayload()` | `dict | None` | OB11 JSON/Milky light_app payload |

```python
from hoshino.command import Alconna, Args, UniMessage
from hoshino.platform.depends import GroupID, SenderID


@sv.on_alconna(Alconna("vote", Args["option", str]))
async def _(
    option: str,
    group_id: int | None = GroupID(),
    user_id: int | None = SenderID(),
):
    if group_id is None:
        await UniMessage.text("请在群聊中使用").send()
        return
    await UniMessage.text(f"{user_id} voted for {option}").send()
```

需要直接判断事件时，使用 `hoshino.platform` 的 `is_group_event()`、`is_private_event()`、
`get_group_id()`、`get_user_id()` 等 helper，不要 `isinstance(event, GroupMessageEvent)` 或直接
读取 `event.group_id`。

## 7. 权限与规则

```python
from hoshino.command import Alconna
from hoshino.core.permission import SUPERUSER
from hoshino.platform.permission import ADMIN, NORMAL, OWNER


@sv.on_alconna(Alconna("public"), permission=NORMAL)
async def _(): ...


@sv.on_alconna(Alconna("admin"), permission=ADMIN)
async def _(): ...


@sv.on_alconna(Alconna("owner"), permission=OWNER)
async def _(): ...


@sv.on_alconna(Alconna("system"), permission=SUPERUSER)
async def _(): ...
```

管理员和群主权限通过 Uninfo/adapter API 解析。查询失败时应拒绝受保护操作，不要默认为有
权限。权限相关测试必须包含无权限用户不响应或被拒绝的负例。

## 8. 构造和发送消息

新插件统一使用 `UniMessage`：

```python
from hoshino.command import UniMessage

text = UniMessage.text("hello")
remote_image = UniMessage.image(url="https://example.com/image.png")
local_image = UniMessage.image(path="data/image/example.png")
memory_image = UniMessage.image(raw=image_bytes)
video = UniMessage.video(path="data/video/example.mp4")
message = text + remote_image

await message.send()
```

禁止在新插件中构造 OB11 `Message`、`MessageSegment`、CQ 字符串，或直接调用
`send_group_msg()` / `send_private_msg()`。

### 回复当前事件

```python
await UniMessage.text("ok").send()
await UniMessage.text("ok").send(reply_to=message_id)
```

需要显式 `bot`/`event` 或 Hoshino 的 `at_sender`、`call_header` 语义时：

```python
from hoshino.platform import send_to_event

await send_to_event(bot, event, "ok", at_sender=True, call_header=True)
```

### 向 Target 发送

```python
from hoshino.platform import group_target, send_to_target

target = group_target(group_id)
await send_to_target(bot, target, UniMessage.text("scheduled message"))
```

可用 Target helper：

- `group_target(group_id)`
- `private_target(user_id)`
- `target_from_event(bot, event)`
- `dump_target(target)` / `load_target(data)`
- `load_target_or_group(data, group_id)`，用于兼容旧的裸群号记录

订阅和定时推送应持久化序列化后的 Target。只保存 Milky `message_id` 或裸群号不足以表达
adapter 与会话范围。

### 合并转发

```python
from hoshino.platform import send_group_forward

await send_group_forward(
    bot,
    group_id,
    [UniMessage.text("first"), UniMessage.image(url=image_url)],
    user_id=bot.self_id,
    nickname="Hoshino",
)
```

OB11 和 Milky 使用原生 constructed forward；Telegram 没有等价语义，会按顺序发送节点。

## 9. Reaction

Reaction handler 使用公共 DI：

```python
from hoshino.platform import (
    ReactedMessage,
    Reaction,
    ReactionInfo,
    RetrievedMessage,
    reaction_event_rule,
)


@sv.on_notice(rule=reaction_event_rule)
async def _(
    reaction: ReactionInfo | None = Reaction(),
    message: RetrievedMessage | None = ReactedMessage(),
):
    if reaction is None or message is None or not reaction.is_add:
        return
    if reaction.face_id != "66":
        return
    text = message.content.extract_plain_text()
```

不要 import OB11/Milky reaction event，也不要在 handler 中直接调用 `get_msg()`。Telegram
目前没有等价的公共 reaction 映射，相关功能必须允许不注册或降级。

## 10. 生命周期、数据库和定时任务

模块可能在 NoneBot 初始化完成前被 import，因此使用 Hoshino hook：

```python
from hoshino.core.hooks import on_serial_startup, on_shutdown


@on_serial_startup
async def initialize() -> None:
    ...


@on_shutdown
async def close() -> None:
    ...
```

- `on_serial_startup`：按注册顺序运行并阻塞 server 启动，适合建表和必要客户端初始化
- `on_post_startup`：server 启动后创建后台任务，不阻塞启动
- `on_startup` / `on_shutdown`：普通生命周期
- `on_bot_connect` / `on_bot_disconnect`：Bot 生命周期

不要在插件 import 时调用 `nonebot.get_driver().on_startup`，也不要在 import 时执行 DDL。

调度使用 `hoshino.core.schedule` 的 `scheduled_job()` 或 `add_job()`，不要在模块加载时直接
访问尚未初始化的 APScheduler 实例。定时任务发送消息时使用已持久化 Target 和公共消息层。

## 11. HTTP、文件和错误处理

- 网络请求使用异步 client；不要在 async handler 中调用阻塞式 HTTP API。
- 共享 client 在 startup hook 初始化，在 shutdown hook 关闭。
- 文件和数据库资源使用 `with` / `async with` 管理。
- 捕获 `Exception`，不要捕获 `BaseException`；不要用空 `except` 吞掉错误。
- 日志使用 `sv.logger`，包含 Service 名和操作上下文，但不得记录 token、cookie 等秘密。
- 外部 API 失败时给用户稳定、简短的回复，并在日志中保留诊断上下文。

## 12. 测试插件

最低检查：

```bash
uv run ruff check path/to/plugin.py path/to/test.py
uv run ruff format --check path/to/plugin.py path/to/test.py
uv run pytest path/to/test.py -q
git diff --check
```

涉及公共核心或跨 adapter 行为时运行：

```bash
uv run pytest nb-tests -q
```

插件行为测试应经过真实 NoneBot dispatch，而不是只调用 handler 或 matcher rule：

1. 用 adapter 的真实模型构造 event。
2. 构造已注册 adapter 的 Bot。
3. 调用 `await bot.handle_event(event)`。
4. stub adapter 的 API/HTTP 边界。
5. 断言 action、target ID 和有意义的消息 payload。

测试至少覆盖：

- 正常输入会响应；
- 非匹配输入不响应；
- Service 禁用 scope 不响应；
- `only_to_me`、群聊/私聊边界符合声明；
- 管理命令拒绝无权限用户；
- 文本、媒体和 Target 导出符合所测 adapter。

Milky 用例必须使用唯一 `message_seq`，避免 Alconna 消息缓存串用。完整协议见
[Milky 插件测试协议](../agent-flow/milky-plugin-test-protocol.md)。测试不得读取生产
`.env.prod`、使用真实 token 或连接真实协议端。

## 13. 提交前检查

- 插件位于正确分类，Service 名全局唯一。
- 没有 adapter-specific import、CQ 字符串或直接 Bot API。
- 生命周期初始化没有发生在 import 阶段。
- 订阅目标保存完整 Target，而不是仅保存裸 ID。
- 权限、Service scope 和不响应路径已有测试。
- focused tests、Ruff 和 `git diff --check` 通过。
- 文档和配置示例没有包含秘密或生产标识。

## 14. 进一步阅读

- [AGENTS.md](../AGENTS.md)：仓库级开发和交付规则
- [架构文档](../agent-flow/architecture.md)：分层和 adapter 隔离
- [AI 模块文档](../agent-flow/ai.md)：AI 模块结构、pydantic-ai 能力使用与自有扩展
- [AI 工具系统](../agent-flow/ai-tools.md)：AI 工具注册表、类别/风险门控
- [Milky](../agent-flow/milky.md)：Milky 数据模型和平台限制
- [Telegram](../agent-flow/telegram.md)：Telegram 平台限制
- [Milky 插件测试协议](../agent-flow/milky-plugin-test-protocol.md)：Milky 行为测试协议

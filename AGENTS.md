# Hoshino.nb2 Agent Guide

本文件是仓库根目录的 Agent 工作入口，适用于整个仓库。开始工作前先读本文件；进入
子目录时，如存在更深层的 `AGENTS.md`，以更深层文件的规则为补充或覆盖。

## 1. 事实来源与工作原则

- 以当前代码、`pyproject.toml`、测试和实际命令结果为准；文档可能滞后。
- 先读取相关实现和调用方，再修改。不要根据旧迁移方案或文件名猜测现状。
- 保持改动聚焦，不顺手重构无关代码，不覆盖工作区中已有的用户改动。
- 修复或实现应包含与风险相称的测试。涉及权限、规则、平台分发时同时覆盖成功和拒绝路径。
- 完成结论必须有 lint、测试、构建或运行探针等客观证据；说明未执行或未通过的检查。
- 不执行生产操作，不使用真实机器人凭据或生产群聊做测试，不提交 `.env.prod` 中的秘密。
- 除非用户明确要求，不主动提交、推送或重写 Git 历史。

协作计划与报告：

- Agent 生成的 plan、调查报告和执行报告统一落在 `agent-plan-report/`。
- `agent-plan-report/` 已加入 `.gitignore`，其中不得写入 token、cookie、密码或其他秘密；
  只记录脱敏后的键名、数量、路径、命令结果和验证结论。
- plan 阶段不应修改业务代码；用户确认后再按 plan 执行，并在同一目录补充执行结果和未覆盖风险。

专题文档位于 `agent-flow/`：

- `architecture.md`：分层与 adapter 隔离边界
- `ai-tools.md`：AI 模块工具系统（注册表、类别/风险门控、`hoshino-nb2-code` 仓库知识工具）
- `docs/plugin-development.md`：面向开发者的完整插件开发指南
- `milky.md` / `telegram.md`：平台能力与限制
- `milky-plugin-test-protocol.md`：Milky 端到端行为测试标准

专题文档与代码冲突时，以代码和测试为准，并在任务范围内更新过时文档。

## 2. 项目概览

HoshinoBot 是迁移到 NoneBot2 的多适配器机器人，支持：

- OneBot V11：连接 Lagrange、LLOneBot 等协议端
- Milky：QQNT 正向 WebSocket/HTTP 或 webhook
- Telegram：polling 或 webhook

Python 要求 `>=3.10`，Python 依赖和虚拟环境统一由 `uv` 管理。机器人配置默认读取
`.env.prod`；示例配置见 `.env.prod.example`。

仓库还包含独立的微博图片 Web 应用：FastAPI 后端加 React/Vite 前端。它读取同一仓库
下的数据，但不依赖 NoneBot 运行时。

## 3. 常用命令

所有命令从仓库根目录执行，除非命令中明确切换目录。

```bash
# 同步锁文件中的依赖；默认包含 dev dependency group
uv sync

# 启动机器人
uv run python run.py

# 也可使用 pyproject.toml 中的 console script
uv run hoshino

# 全量 NoneBot/跨适配器测试
uv run pytest nb-tests -q

# legacy/业务专项测试
uv run pytest .tests -q

# 单文件或单用例
uv run pytest nb-tests/test_message_sending.py -q
uv run pytest path/to/test.py::test_name -q

# 静态检查与格式检查
uv run ruff check .
uv run ruff format --check .
git diff --check

# 仅格式化本次修改的文件
uv run ruff format path/to/file.py path/to/test_file.py

# Python 依赖变更；不要直接编辑 uv.lock
uv add <package>
uv add --dev <package>
uv remove <package>
```

前端和 Web 应用：

```bash
# 安装前端依赖（微博 / X 站点）
npm --prefix weibo_image_web/frontend ci
npm --prefix x_image_web/frontend ci

# 前端开发服务器（微博 3001 / X 3003）
npm --prefix weibo_image_web/frontend run dev -- --host 0.0.0.0 --port 3001
npm --prefix x_image_web/frontend run dev -- --host 0.0.0.0 --port 3003

# TypeScript 检查并构建前端
npm --prefix weibo_image_web/frontend run build
npm --prefix x_image_web/frontend run build

# 统一后端入口（x 默认 9997 / weibo 默认 9998，支持 --host/--port/--reload）
uv run python -m image_web x
uv run python -m image_web weibo

# 一键构建前端并启动 Vite 与后端
bash weibo_image_web/start_dev.sh
bash x_image_web/start_dev.sh

# 停止脚本管理的后端进程
bash weibo_image_web/stop_dev.sh
bash x_image_web/stop_dev.sh
```

不要混用 `pip install` 与 `uv`，也不要手工修改 `package-lock.json`。Python 依赖改动应同时
提交 `pyproject.toml` 和 `uv.lock`；前端依赖改动应同时提交 `package.json` 和 lockfile。

## 4. 启动与配置

`run.py` 的加载顺序是运行契约，修改时要谨慎：

1. `nonebot.init()` 读取环境配置。
2. 注册 OneBot V11、Telegram、Milky adapter。
3. 在导入 Hoshino 前加载 APScheduler、Alconna 和 Uninfo 插件。
4. 导入 Hoshino 配置并执行 `hoshino.bootstrap.bootstrap()`。
5. bootstrap 创建数据目录、应用 OB11 patch/自定义事件、配置日志并 replay 延迟 hook。
6. 加载 `hoshino/base/`，再按 `config.modules` 加载 `hoshino/modules/<category>/`。
7. `nonebot.run()` 启动 driver。

不要把依赖 NoneBot 初始化的 import 移到 `nonebot.init()` 之前。Alconna 必须先作为
NoneBot 插件加载，否则其 matcher 可能无法正常注册。

常用配置项位于 `.env.prod`：`host`、`port`、`debug`、`superusers`、`nickname`、
`modules`、`data`、`static`、Telegram/Milky 客户端和 APScheduler 配置。测试必须隔离本机
`.env.prod`；共享 NoneBug fixture 已在 `nb-tests/conftest.py` 中提供最小配置。

运行时数据主要位于 `data/`：

- `data/service/`：各 Service 的平台 scope 开关
- `data/db/`：SQLite 数据
- `data/image/`、`favorite/`、`video/`：媒体与收藏
- `data/weibomsgs/`：微博内容及 Web 应用数据

除非任务明确要求数据迁移，不要修改或清理运行时数据。

## 5. 代码结构与依赖方向

```text
run.py                     启动入口与插件加载顺序
hoshino/bootstrap.py       初始化目录、OB11 patch、事件、日志和 hook
hoshino/core/              Service、MatcherWrapper、hooks、配置、权限、规则、调度
hoshino/command/           Alconna 与 UniMessage 的项目 facade
hoshino/platform/          adapter-neutral 事件、DI、Target、消息和 Bot API
hoshino/platform/ob11/     OneBot V11 类型与实现隔离区
hoshino/platform/milky/    Milky 类型与实现隔离区
hoshino/platform/telegram/ Telegram 类型与实现隔离区
hoshino/content/           Post/PostMessage/PostQueue/UIDManager 内容推送引擎
hoshino/ai/                AI 对话/任务模块（persona/provider/tools/task，详见 agent-flow/ai-tools.md）
hoshino/base/              始终加载的内置服务
hoshino/modules/           按 category 配置加载的业务插件
hoshino/service_config/    每个 Service 的业务配置 JSON
hoshino/util/              通用工具；不要在此堆积业务逻辑
nb-tests/                  NoneBug、跨适配器和插件行为测试
.tests/                    legacy 与微博业务专项测试
weibo_image_web/           独立 FastAPI + React/Vite 应用
```

允许的主要依赖方向：

```text
modules/base -> core + command + platform + content
content      -> platform
core         -> platform + nonebot + alconna
command      -> nonebot_plugin_alconna
platform     -> adapter-specific subpackages
```

`hoshino/service.py` 是 Service/MatcherWrapper 的兼容出口。新代码优先使用
`hoshino.core.*` 和公共 facade；不要继续扩张兼容层。

### Core 职责

- `core/service.py`：Service 状态、scope、配置和 matcher 工厂
- `core/matcher.py`：`MatcherWrapper`、`AlconnaMatcherWrapper` 及 matcher 日志 hook
- `core/hooks.py`：NoneBot 初始化前可注册的延迟生命周期 hook
- `core/log.py`：Loguru sinks 和重复 matcher 日志过滤
- `core/config.py`：Hoshino 配置模型

每个功能通常创建一个 `Service`：

```python
from hoshino.core.service import Service

sv = Service("my_plugin", enable_on_default=True, visible=True)
```

Service 状态按 adapter scope 持久化；不要退回只使用裸群号的存储。`Service.on_*` 会自动
注入服务开关规则。`MatcherWrapper` 提供 `handle`、`got`、`send`、`finish`、`reject`、
`pause` 等便捷接口。

### Hook 规则

业务模块使用：

```python
from hoshino.core.hooks import on_serial_startup, on_shutdown
```

不要在 import 时调用 `nonebot.get_driver().on_startup`。数据库建表、客户端初始化等需要
确定顺序的工作放 `on_serial_startup`；非阻塞后台启动工作使用 `on_post_startup`；资源释放
放 `on_shutdown`。不要在模块 import 阶段执行 DDL 或启动长期任务。

## 6. 插件与平台规范

新插件放在 `hoshino/modules/<category>/`：`information`、`interactive`、`develop`、
`tools` 或 `entertainment`。优先使用 `Service.on_alconna()`；`on_command()` 是兼容 API。

```python
from hoshino.command import Alconna, Args, UniMessage
from hoshino.core.service import Service
from hoshino.platform.depends import GroupID, SenderID

sv = Service("hello")


@sv.on_alconna(Alconna("hello", Args["name?", str]))
async def _(name: str | None, gid: int | None = GroupID(), uid: int = SenderID()):
    text = f"Hello {name}" if name else f"Hello from {gid}, user {uid}"
    await UniMessage.text(text).send()
```

核心规则：

- 业务插件不得直接 import `nonebot.adapters.onebot.v11`、`.milky` 或 `.telegram`。
- adapter 类型只能出现在对应的 `hoshino/platform/<adapter>/` 隔离区和必要 bootstrap 中。
- 使用 `GroupID()`、`SenderID()`、`PlainText()`、`GroupMemberName()` 等 DI 获取 handler 数据。
- 使用 `is_group_event()` / `is_private_event()`，不要 `isinstance(...GroupMessageEvent)`。
- 使用 `get_group_id()` / `get_user_id()` 等 helper，不直接读取 adapter event 字段。
- 构造消息使用 `UniMessage`，不要在新代码中构造 OB11 `Message`/`MessageSegment` 或 CQ 字符串。
- 发送使用 `UniMessage.send()`、`send_to_event()` 或 `send_to_target()`，不要直接调用
  `send_group_msg()` / `send_private_msg()`。
- Target 使用 `group_target()`、`private_target()`、`target_from_event()`；持久化时使用
  `dump_target()` / `load_target()`，不要只保存 Milky 的会话内 message sequence。
- 合并转发使用 `send_group_forward()` / `send_private_forward()`。Telegram 会顺序发送节点，
  不具备 OB11/Milky 的原生 constructed-forward 语义。
- 权限使用 `hoshino.platform.permission` 的 `NORMAL`、`ADMIN`、`OWNER`，超级用户使用
  `hoshino.core.permission.SUPERUSER`。
- reaction handler 使用 `Reaction()`、`ReactedMessage()` 和 `reaction_event_rule`，不得依赖
  adapter-specific reaction event 或直接调用 `get_msg()`。

Telegram 无法枚举机器人加入的所有聊天；依赖全群列表的功能必须明确降级。Milky 的消息
ID 是会话内序列号，取回消息时必须保留 group/scene。详细限制见对应专题文档。

## 7. Python 代码风格

- 保持 Python 3.10 兼容；不要使用仅更新版本支持的语法或标准库 API。
- 遵循现有 Ruff 规则。import 按 stdlib、third-party、local 分组并置于文件顶部。
- 函数内 import 仅用于真实循环依赖、可选依赖或昂贵 lazy load，并注释原因。
- 优先小函数和明确的数据流；只有在维护状态或匹配既有抽象时才新增类。
- handler 用 DI 声明依赖，不要从全局或 event 中重复抓取数据。
- 异步 I/O 不得使用阻塞网络或文件调用；共享 HTTP client 应在 hook 中初始化和关闭。
- 资源使用 `with` / `async with` 管理；捕获 `Exception`，不要捕获 `BaseException`。
- 不写吞掉错误的裸 `except`，日志要包含操作上下文，但不得输出 token、cookie 等秘密。
- 类型注解用于公共边界和不明显的数据结构；仅在需要推迟求值时使用
  `from __future__ import annotations`。
- 注释解释不明显的原因和协议差异，不复述代码。沿用文件当前语言风格。
- 保持公开 API 小而稳定；重构兼容出口前先搜索全部调用方。

## 8. 测试策略

测试范围按改动风险递增：

1. 纯函数或单模块：运行对应测试文件。
2. Service、matcher、hook、消息或平台 facade：运行相关 `nb-tests`，至少覆盖 OB11/Milky
   或任务涉及的 adapter。
3. 插件行为：通过真实 NoneBot dispatch 路径构造事件并断言发送/API 边界。
4. 启动、公共平台接口或共享核心变更：运行 `uv run pytest nb-tests -q`。
5. 微博内部逻辑变更：同时运行相关 `.tests/test_weibo_*.py`。
6. 前端变更：运行 `npm ... run build`，并用 Playwright 在桌面和移动 viewport 验证关键流程。

Milky 消息行为测试必须：

- 使用 `MilkyAdapter.json_to_event()` 构造真实事件模型；
- 使用唯一 `message_seq`，避免 Alconna 缓存串用；
- 调用 `await bot.handle_event(event)`，不能只测 rule/parser 或直接调用 handler；
- stub adapter 的 HTTP/API 边界；
- 断言 action、target ID 和有意义的消息 payload；
- 不连接真实 QQNT/Milky endpoint。

权限、service scope、regex/fullmatch、`only_to_me` 等规则要有负例，确认不应响应的输入确实
不发送消息。不要把“成功 import”当作行为覆盖。

当前测试可能暴露与任务无关的既有失败。先单独重跑并检查相关文件 diff；不要为了全绿而
顺手修改无关业务。最终报告应给出通过数量、失败用例和为何判断其是否相关。

## 9. Web 应用

图片浏览站点后端统一在 `image_web/` 包中，按 provider 划分：`image_web/x/`（X/Twitter，
数据源 `data/db/x.db`）与 `image_web/weibo/`（微博，数据源 `data/weibomsgs/`）。共享基础
设施（环境解析、收藏写入、CORS/缓存中间件、SPA 挂载、分页、生命周期）位于
`image_web/common/`；provider 在 `image_web/registry.py` 登记。每个 provider 暴露
`create_app()` 与模块级 `app`，对应前端分别在 `x_image_web/frontend/` 与
`weibo_image_web/frontend/`（React 19、TypeScript、Vite 6、Tailwind CSS 4）。

统一启动入口：

```bash
uv run python -m image_web x        # X 站点后端，默认 9997
uv run python -m image_web weibo    # 微博站点后端，默认 9998
# 支持 --host / --port / --reload
```

端口约定：x 后端 9997 / 前端 dev 3003；weibo 后端 9998 / 前端 dev 3001。

- 后端修改至少做 import/启动探针和相关 API 请求验证。
- 新增 provider：新建 `image_web/<name>/server.py`（暴露 `create_app()` 与模块级 `app`），
  并在 `image_web/registry.py` 登记一行。
- 前端修改必须通过 TypeScript/Vite build。
- UI 变更使用 Playwright 检查真实页面、控制台错误、关键交互和响应式布局。
- 远程开发时浏览器访问使用机器实际 IP；先用 `ip addr` 确认，不要把浏览器 URL 写死为
  `localhost`/`127.0.0.1`。
- 启停前读取脚本和 PID 文件状态，不杀死不属于本项目的进程。

## 10. 交付检查

完成代码任务前按适用范围检查：

```bash
git diff --check
uv run ruff check <changed paths>
uv run ruff format --check <changed paths>
uv run pytest <focused tests> -q
```

公共核心或跨平台改动再运行：

```bash
uv run pytest nb-tests -q
```

前端改动再运行：

```bash
npm --prefix weibo_image_web/frontend run build
```

最后检查 `git status --short` 和 diff，确保没有提交凭据、运行日志、缓存、构建产物或无关
格式化。交付说明应简洁列出行为变化、关键文件、验证结果及仍存在的风险或未覆盖边界。

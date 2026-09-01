# Hoshino.nb2

Hoshino.nb2 是基于 [NoneBot2](https://github.com/nonebot/nonebot2) 的 HoshinoBot
迁移与重构项目。项目保留 HoshinoBot 的 Service 与插件组织方式，并通过统一的平台层支持
OneBot V11、Milky 和 Telegram。AI 模块基于 pydantic-ai 构建，参考了
[DeepSeek Harness](https://github.com/nicepkg/deepseek-harness) 的事件溯源与会话治理思路。

项目当前包含机器人主体、跨平台消息与事件抽象、AI 对话与管理、订阅/内容推送插件，以及
一个独立的图片浏览 Web 应用。

## 主要能力

- 同时注册 OneBot V11、Milky 和 Telegram adapter
- 基于 Service 的群聊/会话级功能开关和权限管理
- Alconna 命令、NoneBot native matcher 和统一 `MatcherWrapper`
- 基于 UniMessage 的跨平台文本、图片、视频和合并转发
- 基于 Uninfo 的身份、群成员信息和权限查询
- 统一的 Target、reaction 和被回应消息抽象
- **AI 对话**：pydantic-ai Agent + 事件溯源会话历史 + 多对话管理 + persona 三级解析
- **AI 工具系统**：五类工具（core/computer/bot/web/skill）+ 注册表门控 + 审批流
- **AI 后台任务**：research/plan 状态机 + 调度器 + capability snapshot 冻结恢复
- **Provider 治理**：多 provider 全局管理、统一 model 槽 scope 覆盖、原生多模态看图、实时 API 校验
- APScheduler 定时任务与订阅推送
- NoneBug/pytest 跨适配器行为测试

## 项目结构

```text
run.py                     NoneBot 初始化、adapter 和插件加载入口
hoshino/bootstrap.py       数据目录、OB11 扩展、日志和 hook 初始化
hoshino/core/              Service、MatcherWrapper、配置、权限、hook 和调度
hoshino/command/           Alconna、UniMessage 等命令 facade
hoshino/platform/          adapter-neutral 事件、DI、消息、Target 和 Bot API
hoshino/platform/ob11/     OneBot V11 隔离实现
hoshino/platform/milky/    Milky 隔离实现
hoshino/platform/telegram/ Telegram 隔离实现
hoshino/content/           内容推送模型与队列
hoshino/ai/                AI 能力基建包（Agent/provider/persona/tools/task，非插件）
hoshino/base/              始终加载的内置服务
hoshino/modules/           按配置加载的业务插件
hoshino/modules/ai/        AI 插件（chat 对话 / ai_admin 管理 / task_commands 后台任务）
hoshino/service_config/    各 Service 的业务配置
nb-tests/                  NoneBug、跨适配器和插件行为测试
agent-flow/                架构、AI、插件和 adapter 专题文档
docs/                      插件开发指南
image_web/                 图片浏览站点后端（共享基础 + x/weibo provider）
weibo_image_web/           微博站点前端与启停脚本
x_image_web/               X 站点前端与启停脚本
```

详细的分层和 import 边界见 [架构文档](agent-flow/architecture.md)。

## 环境要求

- Python 3.12 或更高版本
- [uv](https://docs.astral.sh/uv/)
- 至少一个可用的机器人协议端或 Telegram Bot token
- Node.js 与 npm，仅在开发图片浏览站点前端时需要

## 安装

```bash
git clone https://github.com/AkiraXie/hoshino.nb2.git
cd hoshino.nb2
uv sync
cp .env.prod.example .env.prod
```

编辑 `.env.prod`，至少确认以下配置：

```ini
host=0.0.0.0
port=9223
debug=false

superusers=[]
nickname=[]
modules=["information","interactive","develop","tools","entertainment"]

DRIVER=~fastapi+~httpx+~websockets
```

`.env.prod` 可能包含 token、access token 等敏感数据，不要提交到版本控制。

## 配置 Adapter

### OneBot V11

项目注册 OneBot V11 adapter，可连接 Lagrange、LLOneBot 等兼容实现。请在协议端配置与
NoneBot driver 对应的 WebSocket 连接和 access token。具体连接方式取决于所使用的协议端。

### Milky

正向连接示例：

```ini
milky_clients=[{"host":"127.0.0.1","port":3000,"access_token":"","secure":false}]
```

也可以配置 `milky_webhook` 接收反向事件。协议端需要实现 Milky 1.2 API；配置和平台限制
见 [Milky 文档](agent-flow/milky.md)。

### Telegram

```ini
telegram_bots=[{"token":"123456:ABC...","is_webhook":false}]
# telegram_proxy="http://127.0.0.1:7890"
```

`is_webhook=false` 使用 polling。Telegram 的群列表、reaction 和合并转发能力与 QQ adapter
不同，详见 [Telegram 文档](agent-flow/telegram.md)。

## 运行

```bash
uv run python run.py
```

也可以使用项目提供的命令入口：

```bash
uv run hoshino
```

启动时会先加载 APScheduler、Alconna 和 Uninfo，再初始化 Hoshino 并加载
`hoshino/base/` 与 `.env.prod` 中 `modules` 指定的业务分类。

日志输出到 stdout，同时写入：

```text
logs/info/hsnYYYYMMDD.log
logs/error/hsnYYYYMMDD_error.log
```

## AI 模块

AI 能力分为两层：`hoshino/ai/` 基建包（非插件）和 `hoshino/modules/ai/` 插件层。

### Provider 与模型

Provider 是全局资源，不与群绑定。真正跑哪套 `(provider, model)` 只看统一 model 槽：

```text
provider（全局连接）   → ai setup / ai alter / ai provider list / ai provider remove
model（唯一槽）        → ai model set / ai model reset / ai model default
搜索 provider（独立）   → ai search add / ai search default / ai search list
```

- `ai model list`：列出所有 provider 的可用模型（API 实时获取），标注当前 model
- `ai status`：显示当前生效的 model + 搜索状态
- model 优先级：scope 覆盖 > 全局默认（`ai model default`）；两级都空需先配置
- 含图聊天走同一 model 的原生多模态（压缩 BinaryContent），不再做图片描述子请求

### 对话与工具

- `#` 前缀或回复机器人消息触发即时对话
- 多对话管理：`#new` / `#switch` / `#list` / `#clear`
- 五类工具（core/computer/bot/web/skill），按 surface 和 scope 类别门控
- persona 三级解析：scope > 全局 > 默认，支持 `{{variable}}` 模板变量
- 后台任务：`ai task research|plan` 创建持久化任务，状态机驱动

详细的 AI 模块结构、pydantic-ai 能力使用和自有扩展见
[AI 模块文档](agent-flow/ai.md)；工具注册表与门控见
[AI 工具系统](agent-flow/ai-tools.md)。

## 开发插件

新插件放在 `hoshino/modules/<category>/`，业务代码应使用公共平台 API，不要直接依赖某个
adapter 的事件、消息或 Bot 类型。

```python
from hoshino.command import Alconna, Args, UniMessage
from hoshino.core.service import Service
from hoshino.platform.depends import GroupID

sv = Service("hello")


@sv.on_alconna(Alconna("hello", Args["name?", str]))
async def _(name: str | None, group_id: int | None = GroupID()):
    text = f"Hello, {name}" if name else f"Hello from {group_id}"
    await UniMessage.text(text).send()
```

完整的命令、DI、权限、消息、reaction 和数据库启动规范见
[插件开发指南](docs/plugin-development.md)。

## 测试与检查

```bash
# NoneBot、跨适配器和插件行为测试
uv run pytest nb-tests -q

# legacy 与微博业务专项测试
uv run pytest .tests -q

# 静态检查和格式检查
uv run ruff check .
uv run ruff format --check .
git diff --check
```

Milky 插件测试需要经过真实事件模型、`bot.handle_event()` 和被 stub 的 HTTP/API 边界，
具体要求见 [Milky 插件测试协议](agent-flow/milky-plugin-test-protocol.md)。测试不得连接生产
协议端或使用真实凭据。

## 图片浏览 Web 应用

仓库包含两个独立的 FastAPI + React/Vite 图片浏览站点。后端统一在 `image_web/` 包中按
provider 划分（共享基础设施在 `image_web/common/`），前端分别位于
`weibo_image_web/frontend` 和 `x_image_web/frontend`：

- **微博站点**（`weibo` provider）：浏览 Hoshino 保存的微博内容，后端默认 `9998`，前端 dev `3001`。
- **X 站点**（`x` provider）：浏览 X/Twitter 内容，后端默认 `9997`，前端 dev `3003`。

```bash
# 统一后端入口（支持 --host / --port / --reload）
uv run python -m image_web weibo
uv run python -m image_web x

# 安装前端依赖
npm --prefix weibo_image_web/frontend ci
npm --prefix x_image_web/frontend ci

# 一键构建前端并启动 Vite 与后端；停止用对应 stop_dev.sh
bash weibo_image_web/start_dev.sh
bash x_image_web/start_dev.sh
```

## Agent 与贡献者

自动化编码 Agent 在读取或修改仓库前必须先阅读根目录的
[AGENTS.md](AGENTS.md)。该文件定义项目结构、启动顺序、包管理、代码风格、平台隔离、
测试要求和交付检查。`agent-flow/` 只保留需要按任务深入阅读的专题资料。

人工贡献者也建议遵守同一套约束，尤其是 adapter 隔离、UniMessage 消息构造和真实事件
分发测试要求。

## License

本项目使用 [GNU General Public License v3.0](LICENSE)。

## 特别感谢

- [NoneBot2](https://github.com/nonebot/nonebot2)：机器人框架与插件生态
- [HoshinoBot](https://github.com/Ice-Cirno/HoshinoBot)：本项目的原始设计与功能基础
- [DeepSeek Harness](https://github.com/nicepkg/deepseek-harness)：AI Agent 架构参考
- [pydantic-ai](https://github.com/pydantic/pydantic-ai)：AI Agent 框架
- [go-cqhttp](https://github.com/Mrs4s/go-cqhttp) / [LLOneBot](https://github.com/LLOneBot/LLOneBot) / [Lagrange.Core](https://github.com/LagrangeDev/Lagrange.Core)：QQ 协议实现

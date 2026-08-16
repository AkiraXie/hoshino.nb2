# Hoshino.nb2 Agent Guide

本文件是仓库根目录的 Agent 工作入口，适用于整个仓库。开始工作前先读本文件；进入
子目录时，如存在更深层的 `AGENTS.md`，以更深层文件的规则为补充或覆盖。

## 1. 工作原则

- 以当前代码、`pyproject.toml`、测试和实际命令结果为准；文档可能滞后。
- 先读实现和调用方再修改；改动聚焦，不覆盖工作区已有改动。
- 完成结论必须有 lint/测试/构建/探针等客观证据；说明未执行或未通过的检查。
- 不执行生产操作、不用真实机器人凭据或生产群聊测试、不提交 `.env.prod` 中的秘密。
- 任务完成后按 §1.5 主动本地提交；不 push、不重写 Git 历史。

协作计划与报告：

- plan/调查/执行报告统一落 `agent-plan-report/`（已 gitignore，不写 token/cookie/密码，
  只记脱敏键名、数量、路径、命令结果、验证结论）；plan 阶段不改业务代码，用户确认后执行。
- 专题文档在 `agent-flow/`（architecture / ai / ai-tools / milky / telegram /
  milky-plugin-test-protocol）与 `docs/plugin-development.md`；与代码冲突时以代码和测试
  为准，并在任务范围内更新过时文档。

## 1.5 提交、分支与工作区策略

任务开始时先判级并向用户说明工作方式；判级看影响面（是否波及其他模块、是否需全仓库
验证、是否公共基建设计），不看改动行数。

| 级别 | 触发条件 | 工作方式 |
| --- | --- | --- |
| **L0 琐碎** | typo/注释/纯文档，无行为变化 | 当前分支直接改，并入相关 commit |
| **L1 常规** | 单文件/单插件局部修复，验证范围明确 | 当前分支直接改，完成后主动提交 |
| **L2 重大** | 跨模块、影响多插件、新功能、配置/依赖变更、测试基建 | 切 `feat|fix|style/xxx` 分支，分逻辑 commit，用户确认后合并 |
| **L3 公共领域** | `core/`/`platform/`/`content/`/`util/`/`ai/` 设计重构、ruff 基线、依赖方向/架构契约 | 切分支 + `git worktree` 独立工作区，验证后迁回主仓库 |

提交规则：

- L1+ 完成后主动提交，不等催促；拆逻辑 commit（`fix`/`chore`/`test`/`style` 分开），
  message 用 `type(scope): 中文摘要` + 正文说明关键点与行为变化。
- 提交门槛（L1+ 全部通过）：`ruff check` / `ruff format --check`（改动范围）、相关 pytest
  （公共核心跑 `pytest nb-tests -q` 全量）、`git diff --check`。
- 只做本地提交：不 push、不重写历史；不提交 `.env.prod`、日志、缓存、构建产物；
  依赖变更同时提交 `pyproject.toml`+`uv.lock`（前端则 `package.json`+lockfile）。
- L2 分支与 L3 worktree 的提交未经用户确认不 merge、不 push；迁回主仓库后由用户决定
  是否 `git worktree remove`。
- 提交前 `git status --short` + `git diff` 复核：无秘密、无无关改动；公共领域提交在
  message 中标注验证证据（测试数、探针结果）。

## 2. 项目概览

NoneBot2 多适配器机器人（OneBot V11 / Milky / Telegram），Python>=3.12，依赖与虚拟环境
由 `uv` 管理，配置读 `.env.prod`（示例 `.env.prod.example`）。

仓库还含独立图片浏览 Web 应用：`image_web/` 统一后端（按 provider 分 `image_web/x/`、
`image_web/weibo/`）+ 两个前端（`x_image_web/frontend/`、`weibo_image_web/frontend/`），
读取仓库数据但不依赖 NoneBot 运行时。

## 3. 常用命令

```bash
uv sync                                    # 同步锁文件依赖（含 dev group）
uv run python run.py                       # 启动机器人（或 uv run hoshino）
uv run pytest nb-tests -q                  # 全量 NoneBot/跨适配器测试
uv run pytest nb-tests/test_x.py -q        # 单文件/单用例（::test_name）
uv run ruff check .                        # 静态检查
uv run ruff format --check .               # 格式检查（仅格式化改动文件用 ruff format <paths>）
git diff --check                           # 空白错误
uv add <pkg> / uv add --dev <pkg> / uv remove <pkg>   # 依赖变更（不手工改 uv.lock）
```

前端/Web 应用：

```bash
npm --prefix weibo_image_web/frontend ci   # 安装前端依赖（x_image_web 同理）
npm --prefix weibo_image_web/frontend run build        # TS 检查并构建
npm --prefix x_image_web/frontend run build
uv run python -m image_web x              # 后端：x 9997 / weibo 9998，支持 --host/--port/--reload
bash weibo_image_web/start_dev.sh / stop_dev.sh        # 一键起停 Vite+后端
```

不要混用 `pip` 与 `uv`；依赖改动同时提交 manifest 与 lockfile。

## 4. 启动与配置

`run.py` 加载顺序是运行契约，修改需谨慎：

1. `nonebot.init()` 读环境配置；
2. 注册 OneBot V11 / Telegram / Milky adapter；
3. 导入 Hoshino 前加载 APScheduler、Alconna、Uninfo 插件；
4. 导入 Hoshino 配置并 `hoshino.bootstrap.bootstrap()`（建数据目录、OB11 patch、日志、replay hook）；
5. 加载 `hoshino/base/`，再按 `config.modules` 加载 `hoshino/modules/<category>/`；
6. `nonebot.run()` 启动。

不要把依赖 NoneBot 初始化的 import 移到 `nonebot.init()` 之前；Alconna 必须先作为插件
加载，否则 matcher 注册可能失败。

常用配置在 `.env.prod`（host/port/debug/superusers/nickname/modules/data/static、各适配器
与 APScheduler 配置）。测试必须隔离本机 `.env.prod`（`nb-tests/conftest.py` 已提供最小配置）。

运行时数据在 `data/`（`service/` scope 开关、`db/` SQLite、`image|favorite|video/` 媒体、
`weibomsgs/` 微博及 Web 数据）；除非任务明确要求，不要修改或清理运行时数据。

## 5. 代码结构与依赖方向

```text
run.py                     启动入口与插件加载顺序
hoshino/bootstrap.py       初始化目录、OB11 patch、事件、日志和 hook
hoshino/core/              Service、MatcherWrapper、hooks、配置、权限、规则、调度
hoshino/command/           Alconna 与 UniMessage 的项目 facade
hoshino/platform/          adapter-neutral 事件、DI、Target、消息和 Bot API
hoshino/platform/{ob11,milky,telegram}/   各 adapter 类型隔离区
hoshino/content/           Post/PostMessage/PostQueue/UIDManager 内容推送引擎
hoshino/ai/                AI 能力基建包（非插件；详见 agent-flow/ai.md、ai-tools.md）
hoshino/modules/ai/        AI 插件（chat / ai_admin / task_commands）
hoshino/base/              始终加载的内置服务
hoshino/modules/           按 category 加载的业务插件
hoshino/service_config/    每个 Service 的业务配置 JSON
hoshino/util/              通用工具；不要堆积业务逻辑
nb-tests/                  NoneBot 集成与插件行为测试（+ one-shot/ 联网探针）
image_web/                 Web 应用统一后端（x / weibo / common / registry.py）
x_image_web/ weibo_image_web/   两个前端（React+Vite）
```

允许的主要依赖方向：

```text
modules/base -> core + command + platform + content
content      -> platform
core         -> platform + nonebot + alconna
command      -> nonebot_plugin_alconna
platform     -> adapter-specific subpackages
```

`hoshino/service.py` 是 Service/MatcherWrapper 兼容出口，新代码优先用 `hoshino.core.*`，
不要继续扩张兼容层。

Core 职责：`core/service.py`（Service 状态/scope/配置/matcher 工厂）、`core/matcher.py`
（MatcherWrapper + matcher 日志 hook）、`core/hooks.py`（延迟生命周期 hook）、
`core/log.py`（loguru sinks）、`core/config.py`（配置模型）。每个功能通常建一个 `Service`：

```python
from hoshino.core.service import Service

sv = Service("my_plugin", enable_on_default=True, visible=True)
```

Service 状态按 adapter scope 持久化，不要退回裸群号存储；`Service.on_*` 自动注入开关规则，
`MatcherWrapper` 提供 handle/got/send/finish/reject/pause。

Hook 规则：业务模块用 `hoshino.core.hooks` 的 `on_serial_startup` / `on_shutdown`（确定性
顺序工作放 serial、非阻塞后台放 post_startup），不要在 import 阶段调用
`nonebot.get_driver().on_startup`、执行 DDL 或启动长期任务。

AI 模块（`hoshino/ai/` 基建 + `hoshino/modules/ai/` 插件）：底座 pydantic-ai（Agent +
RunContext deps + 动态 system prompt + ApprovalRequiredToolset + agent.iter + UsageLimits），
自有扩展为事件溯源会话历史、多对话管理、三级 persona 模板、provider DB 治理与双模型槽位、
工具注册表门控、后台 Task 运行时、Goal 服务、拦截瀑布 hooks、遥测脱敏、Markdown 渲染、
多模态 vision。详细结构与改法见 `agent-flow/ai.md`、`ai-tools.md`；改人格在 `prompts.py`、
输出规范在 `hoshino/ai/output.md`、新工具在 `tools/`、新配置在 `config.py`（env `AI_*`）。

## 6. 插件与平台规范

新插件放 `hoshino/modules/<category>/`（information / interactive / develop / tools /
entertainment），优先 `Service.on_alconna()`：

```python
from hoshino.command import Alconna, Args, UniMessage
from hoshino.core.service import Service
from hoshino.platform.depends import GroupID, SenderID

sv = Service("hello")


@sv.on_alconna(Alconna("hello", Args["name?", str]))
async def _(name: str | None, gid: int | None = GroupID(), uid: int = SenderID()):
    await UniMessage.text(f"Hello {name}").send()
```

核心规则：

- 业务插件不得 import `nonebot.adapters.onebot.v11` / `.milky` / `.telegram`；adapter 类型
  只出现在对应 `platform/<adapter>/` 隔离区与必要 bootstrap。
- handler 用 DI 拿数据（`GroupID()`/`SenderID()`/`PlainText()`/`GroupMemberName()` 等）；
  用 `is_group_event()`/`is_private_event()`、`get_group_id()`/`get_user_id()` 等 helper，
  不直接读 adapter event 字段、不做 `isinstance(...GroupMessageEvent)`。
- 消息构造用 `UniMessage`（不写 OB11 `Message`/CQ 字符串）；发送用 `UniMessage.send()` /
  `send_to_event()` / `send_to_target()`（不直接调 `send_group_msg()` 等）。
- Target 用 `group_target()`/`private_target()`/`target_from_event()`；持久化用
  `dump_target()`/`load_target()`，不要只存 Milky 会话内 message sequence。
- 合并转发用 `send_group_forward()`/`send_private_forward()`（Telegram 顺序发送，无原生
  constructed-forward 语义）。
- 权限用 `hoshino.platform.permission` 的 NORMAL/ADMIN/OWNER，超管用
  `hoshino.core.permission.SUPERUSER`。
- reaction 用 `Reaction()`/`ReactedMessage()`/`reaction_event_rule`，不得依赖
  adapter-specific reaction event 或直接 `get_msg()`。

Telegram 无法枚举所有聊天，依赖全群列表的功能必须明确降级；Milky 消息 ID 是会话内序列号，
取回消息必须保留 group/scene。详细限制见 `agent-flow/milky.md`、`telegram.md`。

## 7. Python 代码风格

通用规范（Ruff、Google 风格、Pythonic 惯用法）见仓库 `.claude/skills/` 下的
python-guidelines / piglet / friendly-python；本仓库额外约定：

- 保持 Python 3.12 兼容；import 按 stdlib / third-party / local 分组置顶；函数内 import
  仅用于真实循环依赖、可选依赖或昂贵 lazy load（注释原因）。
- 优先小函数和明确数据流；仅在维护状态或匹配既有抽象时新增类。
- 异步 I/O 不用阻塞调用；共享 HTTP client 在 hook 中初始化和关闭；资源用 `with` 管理；
  捕获 `Exception` 不捕获 `BaseException`；不写吞错的裸 `except`，日志带操作上下文但
  不输出 token/cookie。
- 类型注解用于公共边界与不明显结构；仅在需要推迟求值时用 `from __future__ import annotations`。
- 注释解释"为什么"（不明原因、协议差异），不复述代码；沿用文件当前语言风格。
- 公开 API 小而稳定；重构兼容出口前先搜全部调用方。

## 8. 测试策略与纪律

### 8.1 测试组织（仓库现状）

- `nb-tests/`：NoneBot 集成与插件行为测试，唯一进入常规 `pytest nb-tests` 的套件。
  共享 fixture 在 `nb-tests/conftest.py`：`_nonebot_bootstrap`（session 级初始化+全插件加载）、
  `tmp_store`（AI store 指向临时 SQLite）、`fake_ai_server`（本地 fake OpenAI/Anthropic
  HTTP，可 parametrize 注入自定义响应）、`_clear_uninfo_cache`；事件与消息 helper 见
  `_helpers.py` / `adapter_events.py`。
- `nb-tests/one-shot/`：真实 provider/第三方站点联网探针（`test_ai_provider_live.py`、
  `live_ai_persona_probe.py`）。必须设 `ONE_SHOT_LIVE=1` 才运行，不进常规套件；只打印
  脱敏信息，不落 key/token、不写 usage 事件。

### 8.2 测试范围与跑法（按改动风险递增）

1. 纯函数/单模块：`pytest <对应文件> -q`。
2. Service、matcher、hook、消息或平台 facade：`pytest <相关 nb-tests> -q`，至少覆盖涉及的 adapter。
3. 插件行为：真实 NoneBot dispatch（事件 → `handle_event` → 断言发送/API 边界）。
4. 公共核心或跨平台改动：`pytest nb-tests -q` 全量。
5. 前端改动：`npm ... run build` + Playwright 桌面/移动 viewport 关键流程。
6. 真实 provider/外网验证走 one-shot 探针，不混入常规套件。

提交前一律过 §10 门槛。

### 8.3 测试纪律（增删测试的准入）

1. **计划阶段先声明补测**：任务开始时（计划/方案阶段）主动说明本次「是否需要补测试、补哪些、
   按哪个层级（单测/端到端/探针）」；不得在实施中途自行决定补测。只有改动面超出预期
   （隐藏复杂分支、真实 bug 复现）才允许实施中补测，且必须向用户说明理由。
2. **不为简单改动补测试**：简单 bug、简单逻辑、薄的导入/导出或纯配置读取改动，默认不新增
   测试，除非用户明确要求。靠既有测试 + lint/build + 运行探针验证即可。
3. **单测有门槛**：只有复杂 bug 修复或流程核心业务逻辑（解析层、权限、生命周期、状态机、
   护栏等）才写单测；聚焦**函数/类/功能的整体行为**，不为单个 if 分支、单个报错文案、
   单条配置项单独建用例。写完单测必须在交付说明末尾附**测试用例表**（文件/函数/内容/补测
   理由；理由不充分的用例不写）。
4. **端到端必须是完整流程**：从交互输入到最终产出（如 `#消息 → build_agent → provider HTTP
   → 渲染 → 发送`）的整套链条，不是流程切片；能用端到端覆盖的不退化成分散单测。

### 8.4 什么是碎片（不补、并删）

2026-08 全量排查（501 → 435 用例）确立的删除对象，新增测试对照规避：

- 简单工具函数（几行字符串/算术/归一化/字段映射）、薄 CRUD roundtrip；
- 纯配置读取/默认值/环境变量解析断言；文案与展示断言（help/model 展示/prompt 关键词）；
- 单个 if 分支、单个报错文案、单条配置项校验的独立用例；
- import 可用性 smoke、与既有端到端重复的 rule/切片测试；第三方库逐字段透传的薄包装测试。

保留对象：

- 复杂 bug 回归（真实故障背景）；核心状态机/权限/护栏/安全边界（SSRF、containment、
  敏感路径、并发租约）；解析层与消息队列整体行为；完整流程端到端。
- 平台协议关键行为：Milky 测试按 `docs/milky-plugin-test-protocol.md`（json_to_event 构造
  真实事件、唯一 message_seq、handle_event 真实 dispatch、stub API 边界、断言 action/
  target/payload、不连真实 endpoint）。
- 权限、scope、`only_to_me` 等规则必须有负例（应响应 + 不应响应都要覆盖）；不要把
  「成功 import」当行为覆盖。

### 8.5 验证与报告

- 既有失败先单独重跑并检查相关文件 diff，不要为全绿顺手改无关业务；报告给出通过数、
  失败用例及相关性判断。
- 写了单测必须附测试用例表（§8.3.3）；测试基建改动（fixture/helper/one-shot/conftest）
  在交付说明中说明影响面与验证方式。

## 9. Web 应用

后端统一在 `image_web/` 包，provider 分 `image_web/x/`（数据源 `data/db/x.db`）与
`image_web/weibo/`（`data/weibomsgs/`）；共享设施（环境解析、收藏写入、CORS/缓存中间件、
SPA 挂载、分页、生命周期）在 `image_web/common/`，provider 在 `image_web/registry.py` 登记，
每个 provider 暴露 `create_app()` 与模块级 `app`。前端为 `x_image_web/frontend/`、
`weibo_image_web/frontend/`（React 19 / TypeScript / Vite 6 / Tailwind 4）。

启动：`uv run python -m image_web x`（9997）/ `uv run python -m image_web weibo`（9998），
支持 `--host/--port/--reload`；前端 dev 3003/3001。端口约定：x 9997/3003、weibo 9998/3001。

- 后端修改至少做 import/启动探针 + 相关 API 请求验证；新增 provider 建
  `image_web/<name>/server.py` 并在 registry 登记一行。
- 前端修改必须过 TypeScript/Vite build；UI 变更用 Playwright 验证真实页面、控制台错误、
  关键交互与响应式布局。
- 远程开发浏览器用机器实际 IP（`ip addr` 确认），不写死 localhost；启停脚本先读 PID 文件，
  不杀无关进程。

## 10. 交付检查

按改动范围执行（公共核心加跑全量 pytest，前端加 build）：

```bash
git diff --check
uv run ruff check <changed paths>
uv run ruff format --check <changed paths>
uv run pytest <focused tests> -q     # 公共核心/跨平台：uv run pytest nb-tests -q
```

最后 `git status --short` + diff 复核：无凭据、日志、缓存、构建产物或无关格式化。交付说明
简洁列出：行为变化、关键文件、验证结果、未覆盖边界；写了单测附测试用例表（§8.3.3）。

# Hoshino.nb2 Agent Guide

本文件是仓库根目录的 Agent 工作入口，适用于整个仓库。开始工作前先读本文件；进入
子目录时，如存在更深层的 `AGENTS.md`，以更深层文件的规则为补充或覆盖。

## 1. 工作原则

- 以当前代码、`pyproject.toml`、测试和实际命令结果为准；文档可能滞后。
- 先读实现和调用方再修改；改动聚焦，不覆盖工作区已有改动。
- 完成结论必须有 lint/测试/构建/探针等客观证据；说明未执行或未通过的检查。
- **本仓库是个人/低流量机器人，不是大型生产服务**：可直接启动/重启 bot、用真实凭据跑联网探针、
  改动真实运行数据来验证。唯一硬约束是 git 卫生——不把 `.env.prod` 等密钥/凭据提交进 git。
- **改 DB/JSON/API 定义不做兼容**：bot 不关心任何可用性指标。
  改表/字段/接口定义时不要加兼容层、不做旧→新双写，直接**停掉当前 bot** 再改
  （新定义就是事实源，旧代码、死列、迁移分流一并删除）。改完主动本地提交。
- 任务完成后按 §1.5 主动本地提交；不 push、不重写 Git 历史。

协作计划与报告：

- **默认不信任 `agent-plan-report/` 里已有内容**（含 `archived/`）。那里是某次会话的草稿，
  会过时、会和代码冲突。流程规范只信本文件与 `agent-flow/`（architecture / ai / ai-tools /
  milky / telegram / milky-plugin-test-protocol）以及 `docs/plugin-development.md`；
  与代码冲突时以代码和测试为准，并在任务范围内更新过时的 `agent-flow`/本文件。
- 调研、规划、执行报告由**当前任务的 agent 自己产出**，不靠翻旧报告续摊。需要落盘时仍写
  `agent-plan-report/`（已 gitignore；不写 token/cookie/密码，只记脱敏键名、数量、路径、
  命令结果、验证结论）。plan 阶段不改业务代码，用户确认后执行。过时稿归档到
  `agent-plan-report/archived/`，归档件同样不可作为后续依据。

## 1.5 提交、分支与工作区策略

本仓库是个人/低流量 bot，常规改动**直接在当前分支上改、改完主动提交**，不需要切分支。
但 **L3 大型/复杂改动要切 `git worktree` 独立工作区**——你不一定想立即应用大型变更，
先在隔离工作区验证，由你决定何时迁回/合并。任务开始时简单判一下影响面即可。

| 级别 | 触发条件 | 工作方式 |
| --- | --- | --- |
| **L0 琐碎** | typo/注释/纯文档，无行为变化 | 当前分支直接改，并入相关 commit |
| **L1 常规** | 单文件/单插件局部修复，验证范围明确 | 当前分支直接改，完成后主动提交 |
| **L2 重大** | 跨模块、影响多插件、新功能、配置/依赖变更 | 当前分支直接改，分逻辑 commit，主动提交 |
| **L3 公共领域** | `core/`/`platform/`/`content/`/`util/`/`ai/` 设计重构、大型复杂改动 | 切 `git worktree` 独立工作区，改动前先全仓库搜调用方，验证覆盖全量相关测试 |

提交规则：

- 主动提交，不等催促；拆逻辑 commit（`fix`/`chore`/`test`/`style` 分开），
  message 用 `type(scope): 中文摘要` + 正文说明关键点与行为变化。
- 提交门槛（L1+ 全部通过）：`ruff check` / `ruff format --check`（改动范围）、相关 pytest
  （公共核心跑 `pytest nb-tests -q` 全量）、`git diff --check`。
- 只做本地提交：不 push、不重写历史；不提交 `.env.prod`、日志、缓存、构建产物；
  依赖变更同时提交 `pyproject.toml`+`uv.lock`（前端则 `package.json`+lockfile）。
- L3 worktree 里的提交不 merge、不 push；迁回主仓库/合并由用户决定。
- 提交前 `git status --short` + `git diff` 复核：无秘密、无无关改动；公共领域提交在
  message 中标注验证证据（测试数、探针结果）。

### L3 worktree 迁出规则

`git worktree add` 产生的是不含运行时数据的干净 checkout；live 探针/启动验证要读
真实配置与数据，迁出后需补两个只读软链（`.gitignore` 已覆盖 `data` 与 `.env*`，
不污染 git status）：

```bash
git worktree add ../<name> -b feat/xxx HEAD
cd ../<name>
ln -s <主仓库绝对路径>/.env.prod .env.prod   # 读 AI_*/OUTSIDE_PROXY 等配置
ln -s <主仓库绝对路径>/data data            # 读 aichat.db 等运行时数据
```

注意：`.env.prod`/`data` 已存在时 `ln -s` 会把链接建到目录**里面**（GNU ln 语义），
先确认目标不存在或用 `rm -rf data` 清理再建；`hoshino.ai.store` 的 DB 路径解析自
`config.data_dir`（相对 cwd），软链后即指向主仓库 `data/db/aichat.db`。探针只读
provider 行、不落库时可直接复用主仓库数据，无需复制。

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

常用配置在 `.env.prod`（host/port/debug/superusers/nickname/modules/data、各适配器
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
自有扩展为事件溯源会话历史、多对话管理、三级 persona 模板、provider DB 治理
（文本模型 + 独立配置的 vision 槽位）、工具注册表门控、后台 Task 运行时、Goal
服务、拦截瀑布 hooks、遥测脱敏、Markdown 渲染、vision 看图。详细结构与改法见
`agent-flow/ai.md`、`ai-tools.md`；改人格在 `prompts.py`、
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

- 保持 Python 3.12 兼容；import 按 stdlib / third-party / local 分组置顶。**默认禁止函数内
  import**：写代码时先置顶，不要“预防性 lazy”。仅当满足下列之一且**必须在 import 旁用
  一行注释写明原因**时才允许：① 已验证的循环依赖（用 import 图说明边）；② 可选依赖
  （`try/except ImportError` 或缺失时明确降级）；③ 插件加载时序约束（如 alconna/uninfo
  未加载前不可 import）；④ 确实昂贵且该路径很少走到的初始化。禁止用“可能慢/可能循环/
  看起来更干净”当理由。审查/改 AI 模块时主动扫一遍函数内 import 并清掉不合规项。
- 优先小函数和明确数据流；仅在维护状态或匹配既有抽象时新增类。
- 异步 I/O 不用阻塞调用；共享 HTTP client 在 hook 中初始化和关闭；资源用 `with` 管理；
  捕获 `Exception` 不捕获 `BaseException`；不写吞错的裸 `except`，日志带操作上下文但
  不输出 token/cookie。
- 类型注解用于公共边界与不明显结构；仅在需要推迟求值时用 `from __future__ import annotations`。
- 注释解释"为什么"（不明原因、协议差异），不复述代码；沿用文件当前语言风格。
- 公开 API 小而稳定；重构兼容出口前先搜全部调用方。

## 8. 测试策略与纪律

### 8.1 核心原则：只写 e2e 测试

**禁止写单元测试（函数/类级别的直接调用测试），除非用户明确要求。**

所有测试必须是 e2e（端到端）测试：从用户交互入口（`bot.handle_event(event)`）出发，
经过完整的 NoneBot dispatch 链路，断言用户可见的输出（发送的消息、API 调用边界）。
不允许绕过 dispatch 直接调用内部函数、store CRUD、解析器、工具函数等进行断言。

### 8.2 测试组织

- `nb-tests/`：e2e 测试套件，唯一进入常规 `pytest nb-tests` 的目录。
  共享 fixture 在 `nb-tests/conftest.py`：`_nonebot_bootstrap`（session 级初始化+全插件加载）、
  `tmp_store`（AI store 指向临时 SQLite）、`fake_ai_server`（本地 fake OpenAI/Anthropic
  HTTP）、`_clear_uninfo_cache`；事件与消息 helper 见 `_helpers.py` / `adapter_events.py`。
- `nb-tests/one-shot/`：真实 provider/第三方站点联网探针。必须设 `ONE_SHOT_LIVE=1`
  才运行，不进常规套件；只打印脱敏信息，不落 key/token。

### 8.3 测试纪律

1. **不鼓励主动写测试**：本 bot 测试必要性不高，很多改动**上线后简单跑一下**即可验证，
   e2e 不是必选项。默认不新增测试，也不要主动提议补测。
2. **补测必须事先声明**：只有用户明确要求、或行为变更大（影响多个插件/公共基建）时才补，
   且必须在计划阶段先声明要补 e2e，确认后再写；不得在实施中途自行决定补测。
3. **e2e 只求插件级覆盖**：保证每个插件有基本 e2e 覆盖即可，不为每个改动点补测；需补测的
   场景很少。
4. **one-shot 探针可以随时写/跑**：聊天机器人里看某些输出（渲染、图片、HTTP 效果）不直观，
   one-shot 联网探针正是为此准备的，需要时直接写直接跑。
5. 补的必须是 e2e：从交互输入到最终产出的完整链条（如 `#消息 → handle_event →
   build_agent → provider HTTP → 渲染 → 发送`），不是流程切片。

### 8.4 验证与报告

- 既有失败先单独重跑并检查相关文件 diff，不要为全绿顺手改无关业务；报告给出通过数、
  失败用例及相关性判断。
- 测试基建改动（fixture/helper/one-shot/conftest）在交付说明中说明影响面与验证方式。

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
简洁列出：行为变化、关键文件、验证结果、未覆盖边界。

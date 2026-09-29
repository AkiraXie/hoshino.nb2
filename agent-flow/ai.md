# AI 模块开发指南

修改 AI 模块代码前，先了解整体结构和关键约定。工具系统详见 `ai-tools.md`。

## 1. 分层总览

```text
hoshino/ai/            基建包（非插件）：config / store / providers / provider /
                      persona / prompts / sessions / context / runner / hooks /
                      goal / skills / tools / task / harness / metrics / rendering /
                      reply / media / errors
hoshino/modules/ai/    插件层：chat.py（# 对话）、ai_admin.py（管理命令）、
                      task_commands.py（ai task）、zssm/
```

- 基建包不被 `nonebot.load_plugins` 扫描，插件用 `from hoshino.ai.<submodule>` 直连
- 两个 surface：**chat**（`#` 即时对话）和 **task**（`ai task` 后台任务，持久化 TaskContext）

## 2. 模块职责

| 文件 | 职责 |
|---|---|
| `config.py` | `AIConfig` + `AI_*` env 挂载 |
| `base.py` | 配置读取、provider 解析（仅全局默认） |
| `provider.py` | provider 领域层：DB CRUD / 可用模型拉取 / 统一 model 槽解析 |
| `providers.py` | pydantic-ai Model / Agent 工厂，按快照缓存 |
| `runner.py` | `agent.iter()` 图循环驱动、有界重试、RunLog |
| `persona.py` | 三级解析（scope > 全局 > 默认）、`{{variable}}` 模板渲染 |
| `prompts.py` | 系统提示词、示例对话、输出规范 |
| `sessions.py` | ConversationManager：多命名对话，内存 LRU + SQLite write-through |
| `context.py` | 事件日志 → `derive_messages` 派生模型历史 |
| `hooks.py` | 拦截瀑布：pre-step / request-error / post-execute |
| `goal.py` | 跨轮目标：revision CAS + round cap |
| `skills.py` | Skill catalog + scope 状态 |
| `deps.py` | `AgentDeps`（surface/scope/target/config/权限/bot/event/telemetry/task） |
| `store.py` | SQLite 表层：providers / personas / conversations / events / goals / usage |
| `metrics.py` | 用量提取与聚合 |
| `rendering.py` | Markdown → Playwright PNG（pygments 代码高亮；LaTeX 公式经 `latex2mathml` 转 MathML 交给 Chromium 排版，认 `$…$` / `$$…$$` / `\(…\)` / `\[…\]` / amsmath 环境） |
| `media.py` | 事件图片规范为 JPEG/PNG 的 BinaryContent（按字节判格式 + 压缩 + 单边 ≤4096px）；动图抽首/中/尾帧当多张静态图，构建原生多模态 prompt |
| `reply.py` | 回复交付形态：`reply` 输出工具（文档即 `deliver_reply` docstring）+ 排版判定 `needs_image` + 纯文本分段 `split_plain_text` + 归一 `to_delivery` |
| `harness.py` | pydantic-ai-harness facade（Planning / StepPersistence，可降级） |
| `errors.py` | 异常详情提取 |
| `tools/` | 工具注册表与实现（详见 `ai-tools.md`） |
| `task/` | 后台任务运行时：状态机 / 调度 / 审批 / 冻结快照 |

## 3. pydantic-ai 能力使用

**Agent 组装**（`providers.py`）：Model 工厂（OpenAI / Anthropic）+ `Agent(deps_type=AgentDeps)` + 动态 system prompt + `ApprovalRequiredToolset(DynamicToolset(...))` + web_search 走独立搜索 provider。chat 的 `output_type` 是**混合形态**：`TextOutput(guard_reply)`（直接写文字终局）与 `ToolOutput(reply.deliver_reply)`（调 reply 工具交付「形态 + 正文」，调用即结束本轮）；Task 用 run 级 `output_type=TaskOutput` 覆盖。

**Run 驱动**（`runner.py`）：`async with agent.iter(...)` 图循环 + `UsageLimits` 护栏 + `DeferredToolResults` 审批恢复 + `RunResult.usage()` 用量落库；含图时 prompt 为文本 + BinaryContent 原生多模态。

**Harness 扩展**（`harness.py`）：Planning 工具 + StepPersistence ledger；import 失败时降级为空，不影响核心运行。

## 4. 自建扩展

- **工具治理**：注册表 + `resolve_tools` 按 surface/scope/live-event 过滤；授权与注入分离。`hoshino_nb2_code` 属于 core，chat/zssm 默认可用，用来查仓库知识和命令 help
- **事件溯源会话**：append-only 事件日志 → `derive_messages` 派生模型历史，log-only 事件不污染输入
- **多对话管理**：每 scope 多命名对话，turn 锁串行化，`#new/#switch/#list/#clear` 控制
- **persona 体系**：三级解析 + `{{variable}}` 严格插值 + 示例对话 few-shot + `output.md` 强制规范
- **provider 治理**：全局资源不与群绑定；统一 model 槽（scope 覆盖 > 全局默认）；`ai model list` 遍历所有 provider
- **后台任务**：状态机 + 调度器 + 创建时冻结 capability snapshot，恢复只按冻结展开
- **审批流**：Task 按冻结的 approval_mode 暂停/恢复 run
- **Goal 服务**：每 scope 单目标 + revision CAS + round cap
- **拦截瀑布**：pre-step（reject/rewrite）+ request-error（有界重试）
- **预告文本拦截**：`preamble.py` + `TextOutput` guard；有工具却只吐「我先搜一下」时同轮打回一次（`reply` 工具走同一个 `guard_preamble`，不能绕路）
- **回复形态**：`reply.py` 的 `reply` 输出工具让模型显式选「纯文本消息 / Markdown 图片」（工具文档用 MUST 级别写清两种场景）；交付前按硬规则归一——正文带 Markdown / 中文式排版记号一律走图片（模型声明的 text 会被改判，图片是保底），干净文字才走纯文本；纯文本按自然段与 140~210 字窗口分段：一条直接发，多条整合成一条合并转发聊天记录（Telegram 平台层降级为顺序逐条）
- **可观测**：RunLog + 参数/key/url 脱敏 + 实时工具日志（info 级带主负载摘要，
  50 字截断）+ token 用量落库（含 conversation_id，`ai status` 可查当前对话用量）
- **聊天体验**：Markdown 图片渲染、纯文本形态、引用回复识别、原生多模态看图、执行护栏

## 5. 常见任务入口

- 改人格/说话方式：`prompts.py`
- 改输出规范：`hoshino/ai/output.md`
- 改回复形态（纯文本 vs 图片）：`reply.py`（工具文档、形态判定、纯文本化同处一模块）
- 新增工具：`tools/<category>/xxx.py` + `tools/__init__.py` 注册（见 `ai-tools.md`）
- 新增配置：`config.py` `AIConfig` 字段
- 改 provider 支持：`provider.py` + `providers.py`

## 6. 验证（简单直接）

本仓库是个人/低流量 bot，**改动真实运行数据、联网探针、重启 bot 都可直接做**，不必畏手畏脚。
验证以「上线简单跑一下 + one-shot 探针」为主，e2e 不是必选项：

- 常规验证：`uv run ruff check <changed paths>` + `uv run ruff format --check <changed paths>`，
  然后启动 bot 简单跑一下改动的入口（或跑对应 one-shot 探针）确认行为。
- 需要真实链路/看渲染输出：直接在仓库跑 one-shot 联网探针
  （`ONE_SHOT_LIVE=1 uv run pytest nb-tests/one-shot/<探针>.py -s -q`，读 `.env.prod` 的
  `AI_*` 与 `data/db/aichat.db`，只打印脱敏信息），如 `test_vision_chat_live.py`（看图）、
  `test_reply_format_live.py`（回复形态选择，报告落 `agent-plan-report/`）。
- 回归保障：改动后跑**既有**相关测试，确认没弄坏现有覆盖即可
  （AI 相关 `uv run pytest nb-tests/modules/ai -q`；公共核心/跨模块 `uv run pytest nb-tests -q`）。
  补测只在用户明确要求或行为变更大时做，且按 AGENTS.md §8.3 先声明。
- 改 DB/JSON/API 定义：按 AGENTS.md §1 的「不做兼容」策略，先停 bot、直接改定义并同步 ALTER，
  改完跑探针/测试验证后再启动

完成即主动本地提交（见 AGENTS.md §1.5）。

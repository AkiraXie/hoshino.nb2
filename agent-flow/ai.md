# AI 模块结构与实现说明（agent-flow/ai.md）

本文描述 `hoshino/ai/` 与 `hoshino/modules/ai/` 的整体结构：**用了 pydantic-ai 的哪些
能力**、**在它之上又多做了什么**，以及设计参考来源。工具系统的注册表/门控细节见
`ai-tools.md`；读完本文再看 `ai-tools.md` 即可对 AI 模块形成完整认识。

## 1. 分层总览

AI 能力分为两层：

```text
hoshino/ai/            基建包（非插件）：config / store / providers / provider /
                      persona / prompts / sessions / context / runner / hooks /
                      goal / skills / tools / task / harness / metrics / rendering /
                      media / vision / errors
hoshino/modules/ai/    插件层（NoneBot 插件，被 bootstrap 按 modules 配置加载）：
                      chat.py（# 对话）、ai_admin.py（provider/model/persona/tools
                      管理，SUPERUSER）、task_commands.py（ai task 命令，SUPERUSER）、
                      zssm.py（zssm 解释命令）
```

`hoshino/ai/` 不会被 `nonebot.load_plugins` 扫描（扫描路径固定为
`hoshino/modules/<category>`），模块命名无需 `_` 前缀；插件一律
`from hoshino.ai.<submodule>` 直连子模块。基建包内部大部分模块不 import nonebot
（`deps.py` 例外：`AgentDeps` 携带 `Bot`/`Event` 可选引用，供 chat 注入），便于
脱离 NoneBot 运行时做单元测试。

两个 surface 共用同一套底座：

- **chat**：`#` 前缀或回复机器人消息触发，即时对话，`deps.task is None`；
- **task**：`ai task` 创建的后台任务（research/plan），持久化 `TaskContext`，
  `deps.task` 注入，恢复时 `bot`/`event` 为 None。

## 2. 模块结构（hoshino/ai/ 文件职责）

| 文件 | 职责 |
|---|---|
| `config.py` | `AIConfig`（默认 provider、护栏、代理、渲染配置）；`AI_*` env 挂载进 `HoshinoConfig` |
| `base.py` | 配置读取、provider/scope 解析的公共入口（不 import nonebot） |
| `provider.py` | provider 领域层：DB provider / model-list 校验 / scope 模型覆盖 / 可 hash 的 `ProviderRecord` |
| `providers.py` | pydantic-ai model / Agent 工厂：按 `(provider_id, 快照, model, 代理)` 缓存 Agent |
| `runner.py` | `run_agent`：在 `async with agent.iter(...)` 内把图跑到结束；有界重试、RunLog 观测 |
| `persona.py` | persona 领域层：三级解析（scope > 全局 > 默认）、CRUD/绑定、`{{variable}}` 模板渲染 |
| `prompts.py` | 系统提示词素材：`TOOL_CALL_PROMPT`、`DEFAULT_SYSTEM_PROMPT`、`DEFAULT_BEGIN_DIALOGS`、`output.md` 输出规范 |
| `sessions.py` | `ConversationManager`：scope → 多命名对话，内存 LRU + SQLite write-through + turn 锁 |
| `context.py` | 事件日志（append-only）→ 模型历史派生（`derive_messages`）；轮边界对齐截断 |
| `hooks.py` | 拦截瀑布：pre-step（reject/rewrite）/ request-error（retry）/ post-execute（预留） |
| `goal.py` | 跨轮持续目标 `GoalService`：每 scope 单目标 + revision CAS + round cap |
| `skills.py` | Skill catalog / scope 状态：内置 `skills/<name>/SKILL.md` + 本地 `data/skills/` 覆盖 |
| `deps.py` | `AgentDeps`（surface/scope/target/config/权限快照/bot/event/telemetry/task）与权限快照构造 |
| `store.py` | SQLite 表层：providers / personas / conversations / events / skills / goals / usage |
| `metrics.py` | 用量提取（`RunResult.usage()`）与 `ai stats` 聚合 |
| `rendering.py` | Markdown → HTML → Playwright PNG 渲染（聊天图片输出） |
| `media.py` | 事件图片 → pydantic-ai 多模态输入（`ImageUrl` / `BinaryContent`） |
| `vision.py` | vision 模型"看图"子请求：描述文本 → 默认模型作答 |
| `harness.py` | `pydantic-ai-harness` 兼容 facade：Planning / StepPersistence / Skills（可选，可降级） |
| `errors.py` | 异常详情提取（duck-typed，截断输出，供失败日志与 usage event） |
| `tools/` | 工具注册表与实现（core/computer/bot/web/skill 五类），详见 `ai-tools.md` |
| `task/` | 后台任务运行时：`models.py`（TaskContext/TaskOutput）、`policy.py`、`scheduler.py`（claim/lease/heartbeat/审批）、`runtime.py`（TaskContext → Agent run）、`workers.py`、`events.py`（稳定领域事件）、`store.py` |

## 3. 用了 pydantic-ai 的什么能力

模型与 Agent 组装（`providers.py`）：

- **Model 工厂**：`OpenAIChatModel` / `OpenAIResponsesModel` / `AnthropicModel`，配合
  `OpenAIProvider` / `AnthropicProvider` 与自定义 `httpx.AsyncClient`
  （`trust_env=False` 显式忽略环境变量代理，避免 `ALL_PROXY=socks://...` 崩溃；
  socks:// 归一化为 socks5://）。
- **`Agent`**：`deps_type=AgentDeps`（RunContext 依赖注入）、`model_settings`
  （temperature/max_tokens/timeout 从 provider 行转 `ModelSettings`）、
  `retries={"tools": ...}`（工具失败重试预算，默认 3 而非 pydantic-ai 默认 1，
  web_fetch 类抓取工具偶发失败会杀掉整轮 run）、`capabilities`（注入原生
  `WebSearch`，仅 anthropic / openai_responses kind，openai_chat 自动跳过）。
- **动态 system prompt**：`agent.system_prompt(dynamic=True)`，每 run 解析 persona、
  示例对话与输出规范，一个缓存 Agent 服务多 scope。
- **工具集（toolsets）**：`ApprovalRequiredToolset(DynamicToolset(_resolve_toolset,
  per_run_step=False), approval_required_func=approval_required)` ——
  `FunctionToolset` 从工具函数签名自动推断参数 schema（含 `RunContext` 的
  `takes_ctx`）；`DynamicToolset` 每 run 求值一次工具集（scope 工具类别在单次对话
  中不变，省 DB 查询）；`ApprovalRequiredToolset` 把高风险工具调用变成
  deferred approval。
- **web 工具复用 common_tools**：`duckduckgo_search` 直接复用
  `pydantic_ai.common_tools.duckduckgo`（web_fetch 因需要证书关闭等定制而自实现）。

Run 驱动（`runner.py`）：

- **`agent.iter()` 图循环**（pydantic_graph）：`async with agent.iter(...)` 内逐节点
  推进（`ModelRequestNode` → `CallToolsNode` → … → `End`）。文档明确记录了为什么
  不能把 run 循环暴露成异步生成器（iter 上下文内部管理 anyio task group / cancel
  scope，enter/exit 必须同一任务，提前 break 会悬空 asyncgen 导致 NoneBot shield
  CancelScope 退出报错）。
- **`conversation_id`**：审批恢复时以原消息历史 + `DeferredToolResults` 重新进入
  Agent，沿用同一 conversation 关联。
- **`output_type`**：Task 结构化输出 `TaskOutput`（chat 不传，默认 str）。
- **`UsageLimits`**：run 级护栏（`chat_max_requests` 请求次数上限），超限抛
  `UsageLimitExceeded`；墙钟超时另由调用方 `asyncio.wait_for` 控制。
- **消息序列化**：`ModelMessagesTypeAdapter.dump_json/validate_json` 持久化历史。
- **`RunResult.usage()`**：token / cache 用量提取，落库供 `ai stats`。
- **`Model.request()`**：vision 看图走一次直接子请求（不进 Agent 图，避免嵌套 run、
  不带工具无副作用）。

能力扩展（`harness.py`，依赖 `pydantic-ai-harness==0.18.1`）：

- **Planning**：结构化计划工具（`add_task`/`update_task_status`/`read_plan`），计划按
  `deps.task.task_id` 落到与 task store 同一 SQLite 文件的独立 session，跨
  attempt/恢复持久且隔离。
- **StepPersistence**：step 事件 ledger + tool-effect ledger + 可续跑 snapshot，
  `agent_name` 传 Task id，run_id 天然按 Task 隔离。
- **Skills**：harness 的 `Skills(directories, ...)` 仅作可选扩展暴露，Task surface
  不默认注入（Skill 已按内容冻结进 `tool_profile`，叠加会造成工具重复）。
- **降级路径**：harness 是独立 0.x 包，import 失败时所有构建函数返回 None / 空列表，
  Task runtime 照常工作（无 planning 工具、无 step ledger）。

## 4. 在 pydantic-ai 之上多做了什么

pydantic-ai 只提供"单次 run"的模型循环；聊天机器人需要的会话、权限、后台任务、治理
全部是本仓库自建：

- **工具治理（授权与注入分离）**：`ToolRegistration` 注册表（tool_id/version、
  category、risk、risk_for、surfaces、requires_live_event、local_access）+ 
  `resolve_tools` 过滤——模型"看见哪些工具"由 surface、scope 类别绑定与 live-event
  依赖决定；工具执行时仍复核 scope、权限、路径与 live runtime。computer/bot 默认
  不注入，需管理员显式开启；chat 静态排除 high-risk。详见 `ai-tools.md`。
- **事件溯源式会话历史**：对话历史是 append-only 事件日志（`user/message`、
  `assistant/message`、`tool/result` 三类 surface 事件 + `turn/start|end`、
  `step/end`、`tool/call`、`request/header` 等 log-only 事件），模型历史由
  `derive_messages` 派生，可重放、log-only 事件不污染模型输入。这比直接存扁平
  ModelMessage 列表多一层，换来可观测与未来压缩/重放能力。
- **多对话管理**：每个 scope 多个命名对话（内存 LRU + SQLite write-through +
  turn 锁串行化 + 忙检测），`#new` / `#switch` / `#list` / `#clear` 控制；崩溃最多
  丢"进行中尚未落库的一轮"。
- **persona 体系**：三级解析（scope > 全局 > 默认）、`{{variable}}` 严格模板插值
  （内置变量 date/time/scope/group_name/user_name，未知变量 fail loud）、示例对话
  few-shot（锚定说话方式）、`output.md` 强制输出规范（所有 persona 生效）、
  `ai persona` CRUD 命令与 `persona_manage` 工具。
- **provider 治理**：provider 存 SQLite（非 env），`ai setup` 一键配置；model-list
  实时校验（`ai model list` 调 provider API）；scope 绑定 + 全局默认；文本/视觉
  双模型槽位（`vision none` 显式禁用）。
- **后台任务（Task）**：`ai task` 创建 research/plan 任务——状态机
  （created/queued/running/waiting_approval/succeeded/failed/cancelled）、调度器
  （claim/lease/heartbeat、有限重试、持久化取消、启动恢复）、**创建时冻结**
  capability snapshot（persona、skill、tool_profile、approval_mode、workspace），
  恢复只按冻结展开；`TaskOutput` 是唯一产物，群消息只渲染它。
- **审批流**：Task 按冻结的 `approval_mode`（never/always/auto）用
  `ApprovalRequiredToolset` 的 deferred 机制暂停 run，审批决议后以
  `DeferredToolResults` 恢复同一 conversation。
- **Goal 服务**：跨轮持续目标（每 scope 单目标 + revision CAS + round cap），
  `#goal` 命令显式管理；执行仍由用户逐轮 `#` 提问驱动。
- **拦截瀑布**：`hooks.py` 的 pre-step（reject/rewrite 进入模型的 prompt）与
  request-error（瞬态异常有界重试，无工具副作用才重试）注册表，短路语义，
  供未来扩展不侵入 run 循环。
- **可观测与脱敏**：RunLog 收集 steps/tool_calls/nodes，实时日志
  （`describe_node`）；工具参数脱敏为"键名 + 值长度"；key/url 脱敏
  （`mask_key`/`mask_url`）；token/cache 用量落库（`ai stats`）；异常详情提取
  （`errors.py`，不再只记异常类名）。
- **聊天体验**：Markdown → 图片渲染（Playwright，超时回退纯文本）、引用回复识别
  （回复机器人消息继续追问、转发内容一并交给模型）、多模态（vision 描述子请求）、
  执行护栏（墙钟超时 + 请求上限，超时把本轮提问写入上下文可续问）。
- **仓库知识工具**：`hoshino_nb2_code`（overview/norms/flow/ai_module/read），让
  agent 改进本仓库（尤其 `hoshino/ai/` 自身）前快速掌握上下文，只读、路径
  containment、敏感路径拒绝。

## 5. 参考与致谢

AI 模块的设计参考了以下开源项目的能力模型；参考点是**架构思路对齐**，实现均为
Python/pydantic-ai 原生重写，未直接搬运代码：

### DeepSeek Harness（dsh）

TypeScript + Cordis 的事件溯源 agent 框架：

- **事件溯源会话**：append-only `SessionEvent` 日志 + `deriveMessages()` 派生模型
  历史 → 对应 `context.py` 的事件日志与 `derive_messages`（含 `turn/start|end`、
  `step/start|end`、`user/message`、`assistant/message`、`tool/call`、`tool/result`、
  `request/header` 事件类型）。
- **拦截瀑布**：`agent/pre-step`（reject | enter）与 `agent/request-error`
  （retry）→ 对应 `hooks.py` 的 pre-step / request-error / post-execute 三组 hook
  注册表（post-execute 本期只定义接缝，未接线）。
- **Goal 语义**：`goal.md` 的 phase=active/paused/blocked/complete + revision CAS
  + maxGoalRounds → 对应 `goal.py`（用"状态行 + CAS"而非事件溯源）。
- **persona 模板变量**：dsh-persona 的 `{{variable}}` 严格插值与 `VARIABLE_NAME`
  命名 → 对应 `persona.py` 的模板渲染（未知变量 fail loud）。
- **SKILL.md 格式**：Harness 支持的 frontmatter（`name` + `description`）→ 对应
  `skills.py` 的技能文件格式（不自研不兼容协议）。
- **pydantic-ai-harness 包**：Planning / StepPersistence / Skills 能力 → 对应
  `harness.py` 的兼容 facade。

### AstrBot

Python 聊天机器人框架（对话管理与提示词组织参考）：

- **ConversationManager**：Session(scope) → 多命名 Conversation 的双层对话模型、
  内存缓存 + 持久化 write-through → 对应 `sessions.py` / `store.py` 的
  `ConversationManager` 与 `ai_conversations` 表。
- **round_utils**：历史截断按轮边界对齐（不切半轮，避免孤儿 tool 消息导致
  provider 400）→ 对应 `context.py` 的 `truncate_messages`。
- **上下文压缩思路**：token 估算、82% 阈值、LLM 摘要压缩 → `context.py` 预留
  `ContextCompressor` 协议（首期仅轮次截断）。
- **skill prompt**：可用技能清单 + "先读说明再执行"的提示词组织 → 对应
  `prompts.py` 的 `build_skills_prompt`。
- **begin_dialogs**：示例对话 few-shot 锚定说话方式（与 shebot mes_example 同
  思路）→ 对应 `prompts.py` 的 `DEFAULT_BEGIN_DIALOGS` 与 persona 的
  `--dialogs` 配置。

## 6. 常见任务入口

- 改默认人格 / 说话方式：`prompts.py` 的 `DEFAULT_SYSTEM_PROMPT` /
  `DEFAULT_BEGIN_DIALOGS`。
- 改输出规范 / 禁用词：`hoshino/ai/output.md`（改动注意保留测试断言的关键词）。
- 新增工具：`tools/<category>/xxx.py` 写异步函数 + `tools/__init__.py` 注册一行
  （步骤见 `ai-tools.md` §新增一个工具）。
- 新增配置：`config.py` `AIConfig` 字段（env `AI_*`，写 `.env.prod`）。
- 改 provider 支持：`provider.py`（领域层）+ `providers.py`（model 工厂）。
- 验证：`uv run pytest nb-tests/test_ai_persona.py nb-tests/test_ai_chat.py -q`；
  真实 provider 人格探针 `uv run python nb-tests/one-shot/live_ai_persona_probe.py`。

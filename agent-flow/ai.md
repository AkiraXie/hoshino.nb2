# AI 模块开发指南

修改 AI 模块代码前，先了解整体结构和关键约定。工具系统详见 `ai-tools.md`。

## 1. 分层总览

```text
hoshino/ai/            基建包（非插件）：config / store / providers / provider /
                      persona / prompts / sessions / context / runner / hooks /
                      goal / skills / tools / task / harness / metrics / rendering /
                      media / errors
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
| `rendering.py` | Markdown → Playwright PNG |
| `media.py` | 事件图片压缩为 BinaryContent，构建原生多模态 prompt |
| `harness.py` | pydantic-ai-harness facade（Planning / StepPersistence，可降级） |
| `errors.py` | 异常详情提取 |
| `tools/` | 工具注册表与实现（详见 `ai-tools.md`） |
| `task/` | 后台任务运行时：状态机 / 调度 / 审批 / 冻结快照 |

## 3. pydantic-ai 能力使用

**Agent 组装**（`providers.py`）：Model 工厂（OpenAI / Anthropic）+ `Agent(deps_type=AgentDeps)` + 动态 system prompt + `ApprovalRequiredToolset(DynamicToolset(...))` + web_search 走独立搜索 provider。

**Run 驱动**（`runner.py`）：`async with agent.iter(...)` 图循环 + `UsageLimits` 护栏 + `DeferredToolResults` 审批恢复 + `RunResult.usage()` 用量落库；含图时 prompt 为文本 + BinaryContent 原生多模态。

**Harness 扩展**（`harness.py`）：Planning 工具 + StepPersistence ledger；import 失败时降级为空，不影响核心运行。

## 4. 自建扩展

- **工具治理**：注册表 + `resolve_tools` 按 surface/scope/live-event 过滤；授权与注入分离
- **事件溯源会话**：append-only 事件日志 → `derive_messages` 派生模型历史，log-only 事件不污染输入
- **多对话管理**：每 scope 多命名对话，turn 锁串行化，`#new/#switch/#list/#clear` 控制
- **persona 体系**：三级解析 + `{{variable}}` 严格插值 + 示例对话 few-shot + `output.md` 强制规范
- **provider 治理**：全局资源不与群绑定；统一 model 槽（scope 覆盖 > 全局默认）；`ai model list` 遍历所有 provider
- **后台任务**：状态机 + 调度器 + 创建时冻结 capability snapshot，恢复只按冻结展开
- **审批流**：Task 按冻结的 approval_mode 暂停/恢复 run
- **Goal 服务**：每 scope 单目标 + revision CAS + round cap
- **拦截瀑布**：pre-step（reject/rewrite）+ request-error（有界重试）
- **可观测**：RunLog + 参数/key/url 脱敏 + token 用量落库
- **聊天体验**：Markdown 图片渲染、引用回复识别、原生多模态看图、执行护栏

## 5. 常见任务入口

- 改人格/说话方式：`prompts.py`
- 改输出规范：`hoshino/ai/output.md`
- 新增工具：`tools/<category>/xxx.py` + `tools/__init__.py` 注册（见 `ai-tools.md`）
- 新增配置：`config.py` `AIConfig` 字段
- 改 provider 支持：`provider.py` + `providers.py`
- 验证：`uv run pytest nb-tests/test_ai_persona.py nb-tests/test_ai_chat.py -q`

# AI 工具开发指南

新增或修改 AI 工具时，遵循以下规则。AI 对话（`#`）与后台任务（Task）共用同一套工具系统。工具注册在 `hoshino/ai/tools/__init__.py` 的 `REGISTRATIONS`；模型"看见哪些工具"由 `resolve_tools` 按 surface、scope 绑定与 runtime capability 过滤决定；执行时仍复核 scope、权限、路径与 live runtime（授权与注入分离）。

## 注册表字段

| 字段 | 含义 |
|---|---|
| `tool_id` / `version` | 稳定标识；Task 冻结 `tool_profile` 用 |
| `category` | `core` / `computer` / `bot` / `web` / `skill` |
| `surfaces` | `chat` / `task` |
| `risk` | `low` / `medium` / `high` |
| `risk_for` | 参数级风险判定函数 |
| `requires_live_event` | 需要真实事件（后台恢复时不注入） |
| `local_access` | 触碰本机文件/进程 |

## 类别门控

- 未配置的 scope 默认 `core/web/skill`；`ai tools on/off` 叠加/移除
- `computer` 与 `bot` 默认不注入，需管理员显式开启
- chat 静态排除 `risk=high`；file delete 在 chat 中返回无副作用提示
- Task 恢复只按冻结的 `tool_profile` 展开

## 审批模型

- chat：从不审批（high-risk 已静态排除）
- task：按冻结的 `approval_mode`——`never` / `always` / `auto`（仅 high-risk 先审批）

## 工具一览

下表是 `REGISTRATIONS` 里可注入的**功能工具**（受类别/scope/surface 门控）。另有 chat
专有的 `reply` **输出工具**，不在注册表内（见文末「输出工具」）。

| tool_id | category | risk | surfaces | 说明 |
|---|---|---|---|---|
| `now` | core | low | chat/task | 当前时间 |
| `memory` | core | medium | chat/task | scope 隔离长期记忆 |
| `persona_manage` | core | medium | chat/task | 人设 CRUD/绑定 |
| `provider_choose` | core | medium | chat/task | provider/模型切换（仅 superuser） |
| `hoshino_nb2_code` | core | low | chat/task | 仓库知识（只读，chat/zssm 默认可用） |
| `bash` | computer | high | task | shell（需显式开启） |
| `python` | computer | high | task | Python 执行 |
| `file` | computer | medium→high | chat/task | 工作目录内读写删（参数级风险） |
| `service_manage` | bot | medium | chat | 服务开关 |
| `send_message` | bot | medium | chat | 单向发消息 |
| `web_search` | web | low | chat/task | 联网搜索（deepseek/tavily/博查） |
| `web_fetch` | web | low | chat/task | 网页转 Markdown |
| `image_view` | core | low | chat/task | 图片 URL → BinaryContent（规范为 JPEG/PNG/GIF，原生看图） |
| `browser_use` | web | medium | chat/task | Playwright 浏览截图 → BinaryContent |
| `skill_read` | skill | low | chat/task | 读技能说明 |
| `skill_manage` | skill | medium | chat | 技能启停 |

## hoshino_nb2_code

仓库知识工具（只读，**core 类别**，chat / zssm 默认注入，不必开 computer）。子命令：`overview`（概览）、`norms`（规范）、`flow`（工作流）、`ai_module`（AI 模块指南）、`help [query]`（命令 help / USAGE / Alconna `get_help()`）、`read <path>`（读文件）。路径限制在仓库根目录内，敏感路径（`.env*`、`.git`、`data/`、凭据等）直接拒绝。

询问机器人本身时优先 `help`：例如用户说 `zssm`、`ai model reset`、`#help ai model set`，先调 `help` 拿 USAGE/模块说明，需要实现细节再 `read` 对应源文件。

## 输出工具（`reply`，不属于本注册表）

chat 的最终回复有「纯文本消息」和「Markdown 图片」两种形态，选择器是 `hoshino/ai/reply.py`
的 `deliver_reply`：它作为 `ToolOutput` 挂在 chat 的 `output_type`（见 `providers.py`），
与 `TextOutput(guard_reply)` 共存——模型直接写文字就是纯文本终局，调 `reply` 工具则把
「形态 + 正文」一次交出来并结束本轮，`result.output` 是 `Reply`。

- 不进 `REGISTRATIONS`：它不是可按类别/scope 开关的能力，而是 chat 的交付出口，恒可用；
- 工具文档（模型看到的 description）就是 `deliver_reply` 的 docstring：MUST / MUST NOT /
  SHOULD 级别写明两种形态的适用场景、纯文本必须平铺直叙（不得出现任何排版记号）、
  拿不准一律选图片（图片是保底）；
- 交付前 `reply.to_delivery` 按硬规则归一形态：正文检出 Markdown / 中文式排版记号
  （`needs_image`）→ 一律图片，模型声明的 `text` 也会改判（`Delivery.escalated`）；
  否则按模型声明或文本终局自动判定；
- text 形态由 `split_plain_text` 分段：空行分隔的自然段是首选断点，打包成
  140~210 字（`SEGMENT_MIN_CHARS`/`SEGMENT_MAX_CHARS`）的几条，chat 把多条
  整合成一条合并转发聊天记录发出（单条直接发；Telegram 平台层降级为顺序逐条）；
- 预告文本守卫对两条路都生效（`preamble.guard_preamble`），不能靠调工具绕开。

## 新增工具

1. `tools/<category>/xxx.py` 写异步函数 `(ctx: RunContext[AgentDeps], ...)`
2. `tools/__init__.py` 追加 `ToolRegistration(...)`
3. `nb-tests/modules/ai/` 的插件级 e2e 覆盖（按 AGENTS.md §8.3 决定是否补）
4. computer/bot 类需管理员显式开启

## 验证

```bash
uv run pytest nb-tests/modules/ai -q
uv run ruff check hoshino/ai/tools
```

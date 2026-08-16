# AI 模块工具系统（agent-flow/ai-tools.md）

AI 对话（`#`）与后台任务（Task）共用同一套 LLM 工具系统。工具是纯函数/`pydantic-ai
Tool`，注册在 `hoshino/ai/tools/__init__.py` 的 `REGISTRATIONS`；模型"看见哪些工具"由
`resolve_tools` 按 surface、scope 绑定与 runtime capability 过滤决定；工具执行时仍必须
复核 scope、权限、路径与 live runtime（授权与注入分离）。

## 注册表字段（ToolRegistration）

| 字段 | 含义 |
|---|---|
| `tool_id` / `version` | 稳定标识；Task 冻结 `tool_profile` 用 `(tool_id, version)` |
| `tool` | 工具函数（`FunctionToolset` 自动推断 schema）或 `pydantic_ai Tool` |
| `category` | `core` / `computer` / `bot` / `web` / `skill` |
| `surfaces` | `chat` / `task`（或两者） |
| `risk` | `low` / `medium` / `high`（静态基线） |
| `risk_for` | 参数级风险判定函数（如 file 的 read/list=low、write=medium、delete=high） |
| `requires_live_event` | 需要真实事件（bot 类工具；后台恢复时 event 为 None 不注入） |
| `local_access` | 触碰本机文件/进程（computer 类） |

## 类别门控与安全默认

- 未配置过工具类别的 scope 使用安全默认 `core/web/skill`；`ai tools on/off` 在默认之上
  **叠加/移除**（显式开 computer 不会丢掉默认类别）。
- `computer`（bash/python/file/hoshino_nb2_code）与 `bot` 默认**不注入**，需管理员在
  scope 显式开启：`ai tools on computer chat <scope>`。
- chat surface 静态排除 `risk=high` 工具（bash/python 永不进聊天）；file 的 delete 在
  chat 中返回"创建 Task"，不产生副作用。
- Task 恢复只按冻结的 `tool_profile` 展开，不受执行时 binding 变化影响。

## 审批模型（approval_required）

- chat（`deps.task is None`）：从不审批；high-risk 已静态排除，file 参数级高风险返回
  无副作用提示。
- task：按 Task 创建时冻结的 `approval_mode`——`never` 不审批 / `always` 全部审批 /
  `auto` 仅 high-risk（含 `risk_for` 参数级判定）先审批，批准后以 `DeferredToolResults`
  恢复同一 conversation 继续执行。

## 当前工具一览

| tool_id | category | risk | surfaces | 说明 |
|---|---|---|---|---|
| `now` | core | low | chat/task | 当前时间 |
| `memory` | core | medium | chat/task | scope 隔离长期记忆读写 |
| `persona_manage` | core | medium | chat/task | 人设 CRUD/绑定（use/reset 需管理员） |
| `provider_choose` | core | medium | chat/task | 调整 scope 的 provider/文本模型/vision（**仅 superuser**） |
| `bash` | computer | high | chat/task | shell（chat 静态排除；需显式开启） |
| `python` | computer | high | chat/task | Python 执行（chat 静态排除） |
| `file` | computer | medium→high | chat/task | 冻结工作目录内读写删（参数级风险） |
| `hoshino_nb2_code` | computer | low | chat/task | 仓库知识（只读，见下） |
| `service_manage` | bot | medium | chat | 服务开关（需 live event + 管理员） |
| `send_message` | bot | medium | chat | 单向发消息（需 live event） |
| `web_search` | web | low | chat/task | 联网搜索（`ai search` 配置，deepseek/tavily/博查，默认 deepseek） |
| `web_fetch` | web | low | chat/task | 网页转 Markdown |
| `image_view` | core | low | chat/task | 抓图片 URL → vision 模型识别 → 返回文字描述 |
| `browser_use` | web | medium | chat/task | Playwright 浏览网页 → 截图 → vision 模型识别 |
| `skill_read` | skill | low | chat/task | 读技能说明 |
| `skill_manage` | skill | medium | chat | 技能启停 |

## hoshino-nb2-code：仓库知识工具

`hoshino/ai/tools/computer/repo_code.py`，函数名 `hoshino_nb2_code`（Python 函数名
不能含连字符，故注册 id 用 snake_case；管理命令/文档中可写作 `hoshino-nb2-code`）。

用途：让 AI agent 在改进本仓库（尤其是 `hoshino/ai/` 自身）前，快速掌握仓库基本情况、
开发规范与 agent 工作流程，并直接读取仓库内文件。只读、不执行、不落盘。

子命令：

- `overview`：仓库概览（项目、技术栈、目录结构、常用命令）
- `norms`：开发规范摘要（AGENTS.md 要点：事实来源、风格、测试策略、交付检查）
- `flow`：agent 工作流程（agent-flow/ 文档索引、agent-plan-report/ 约定）
- `ai_module`：AI 模块自身结构与改进指南（改人格/输出规范/加工具/加配置分别改哪）
- `read <path>`：读取仓库内文件全文（上限 50k 字符）

路径安全：只接受仓库根目录内相对路径（symlink 解析后 containment，拒绝绝对路径与
`..` 段）；敏感路径直接拒绝（`.env*`、`.git`、`credentials`/`secrets`/`id_rsa`、
`node_modules`、`logs`、`data`、`__pycache__`）。`data/`（运行时数据）与凭据相关
文件一律不可读，防止泄密。

## 新增一个工具（步骤）

1. 在 `hoshino/ai/tools/<category>/xxx.py` 写异步工具函数：签名 `(ctx: RunContext[AgentDeps], ...)`，
   pydantic-ai 自动推断参数 schema；执行时复核 scope/权限/路径（参考 `file.py` 的
   containment 与 `persona_manage.py` 的权限复核）。
2. 在 `tools/__init__.py` 导入并往 `REGISTRATIONS` 追加一行 `ToolRegistration(...)`，
   填对 category / risk / surfaces / risk_for / requires_live_event / local_access。
3. 在 `nb-tests/test_ai_tools.py` 加测试：注入断言（类别门控）、成功路径、拒绝/负例。
4. 如属于 computer/bot，管理员需在 scope 显式开启后才能被模型调用。

## 验证

```bash
uv run pytest nb-tests/test_ai_tools.py -q
uv run ruff check hoshino/ai/tools
```

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

| tool_id | category | risk | surfaces | 说明 |
|---|---|---|---|---|
| `now` | core | low | chat/task | 当前时间 |
| `memory` | core | medium | chat/task | scope 隔离长期记忆 |
| `persona_manage` | core | medium | chat/task | 人设 CRUD/绑定 |
| `provider_choose` | core | medium | chat/task | provider/模型切换（仅 superuser） |
| `bash` | computer | high | task | shell（需显式开启） |
| `python` | computer | high | task | Python 执行 |
| `file` | computer | medium→high | chat/task | 工作目录内读写删（参数级风险） |
| `hoshino_nb2_code` | computer | low | chat/task | 仓库知识（只读） |
| `service_manage` | bot | medium | chat | 服务开关 |
| `send_message` | bot | medium | chat | 单向发消息 |
| `web_search` | web | low | chat/task | 联网搜索（deepseek/tavily/博查） |
| `web_fetch` | web | low | chat/task | 网页转 Markdown |
| `image_view` | core | low | chat/task | 图片 URL → vision 识别 |
| `browser_use` | web | medium | chat/task | Playwright 浏览 + vision |
| `skill_read` | skill | low | chat/task | 读技能说明 |
| `skill_manage` | skill | medium | chat | 技能启停 |

## hoshino_nb2_code

仓库知识工具（只读），子命令：`overview`（概览）、`norms`（规范）、`flow`（工作流）、`ai_module`（AI 模块指南）、`read <path>`（读文件）。路径限制在仓库根目录内，敏感路径（`.env*`、`.git`、`data/`、凭据等）直接拒绝。

## 新增工具

1. `tools/<category>/xxx.py` 写异步函数 `(ctx: RunContext[AgentDeps], ...)`
2. `tools/__init__.py` 追加 `ToolRegistration(...)`
3. `nb-tests/test_ai_tools.py` 加测试
4. computer/bot 类需管理员显式开启

## 验证

```bash
uv run pytest nb-tests/test_ai_tools.py -q
uv run ruff check hoshino/ai/tools
```

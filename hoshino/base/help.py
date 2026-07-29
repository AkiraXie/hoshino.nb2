"""命令帮助系统 — 利用 Alconna 的 CommandMeta 和 get_help()"""

# from hoshino.command import CommandMeta, UniMessage
# from hoshino.platform.depends import ParamText
# from hoshino.platform.permission import ADMIN
# from hoshino.service import Service

# sv = Service("help", enable_on_default=False, visible=False, manage_perm=ADMIN)


# @sv.on_command(
#     "help",
#     meta=CommandMeta(
#         description="显示命令帮助",
#         usage="help [服务名/命令名]",
#         example="help QA",
#     ),
#     only_group=False,
# )
# async def _(text: str = ParamText()):
#     if not text:
#         # 列出所有服务
#         lines = ["📋 可用服务列表："]
#         services = Service.get_loaded_services()
#         for name, service in sorted(services.items()):
#             if not service.visible:
#                 continue
#             cmds = []
#             for m_str in service.matchers:
#                 if "command=" in m_str:
#                     cmd = m_str.split("command=")[1].rstrip(">")
#                     cmds.append(cmd)
#             if cmds:
#                 lines.append(f"  **{name}** — {', '.join(cmds[:3])}")
#         await UniMessage.text("\n".join(lines)).send()
#         return

#     # 查找具体服务或命令
#     query_lower = text.lower()
#     services = Service.get_loaded_services()

#     # 先尝试匹配服务名
#     for name, service in services.items():
#         if name.lower() == query_lower:
#             lines = [f"📋 服务 **{name}** 的命令："]
#             for m_str in service.matchers:
#                 if "command=" in m_str:
#                     cmd = m_str.split("command=")[1].rstrip(">")
#                     type_str = (
#                         m_str.split("type=")[1].split(",")[0]
#                         if "type=" in m_str
#                         else "?"
#                     )
#                     lines.append(f"  `{cmd}` ({type_str})")
#             await UniMessage.text("\n".join(lines)).send()
#             return

#     # 尝试匹配命令名
#     for name, service in services.items():
#         for m_str in service.matchers:
#             if "command=" in m_str:
#                 cmd = m_str.split("command=")[1].rstrip(">")
#                 if cmd.lower() == query_lower or query_lower in cmd.lower():
#                     lines = [f"📋 命令 `{cmd}` — 属于服务 **{name}**"]
#                     type_name = (
#                         m_str.split("type=")[1].split(",")[0]
#                         if "type=" in m_str
#                         else "?"
#                     )
#                     lines.append(f"  类型: {type_name}")
#                     await UniMessage.text("\n".join(lines)).send()
#                     return

#     await UniMessage.text(f"未找到服务或命令: {text}").send()

"""Bot API wrappers — compat re-export from platform/ob11"""

from hoshino.platform.ob11.bot import (
    get_group_list as get_group_list,
    get_group_member_info as get_group_member_info,
    send_group_forward as send_group_forward,
    send_private_forward as send_private_forward,
    upload_group_file as upload_group_file,
)

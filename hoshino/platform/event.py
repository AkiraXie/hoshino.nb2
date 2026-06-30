"""Event helpers — compat re-export from platform/ob11"""

from hoshino.platform.ob11.event import (
    get_event_message as get_event_message,
    get_event_value as get_event_value,
    get_group_id as get_group_id,
    get_message_id as get_message_id,
    get_plaintext as get_plaintext,
    get_reply_message as get_reply_message,
    get_session_id as get_session_id,
    get_user_id as get_user_id,
    is_group_event as is_group_event,
    is_message_event as is_message_event,
    is_private_event as is_private_event,
)

"""Compatibility shim for hoshino.core.hooks."""

from hoshino.core.hooks import (
    event_preprocessor as event_preprocessor,
    on_bot_connect as on_bot_connect,
    on_bot_disconnect as on_bot_disconnect,
    on_post_startup as on_post_startup,
    on_serial_startup as on_serial_startup,
    on_shutdown as on_shutdown,
    on_startup as on_startup,
    replay as replay,
    run_preprocessor as run_preprocessor,
)

__all__ = [
    "event_preprocessor",
    "on_bot_connect",
    "on_bot_disconnect",
    "on_post_startup",
    "on_serial_startup",
    "on_shutdown",
    "on_startup",
    "replay",
    "run_preprocessor",
]

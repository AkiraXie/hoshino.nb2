"""Compatibility shim for hoshino.core.schedule."""

from hoshino.core.schedule import add_job as add_job
from hoshino.core.schedule import scheduled_job as scheduled_job
from hoshino.core.schedule import wrapper as wrapper

__all__ = ["add_job", "scheduled_job", "wrapper"]

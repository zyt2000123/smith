"""Deprecated compatibility imports for the relocated sandbox module.

New engine code must import execution environments from :mod:`engine.sandbox`.
This module remains temporarily so existing third-party tool providers do not
break during the package migration.
"""

from engine.sandbox.host import (
    MAX_OUTPUT,
    CommandResult,
    ExecutionEnvironment,
    LocalExecutionEnvironment,
    _cancel_stream_tasks,
    _drain_streams,
    _signal_process_group,
    _stop_process_group,
)

__all__ = (
    "MAX_OUTPUT",
    "CommandResult",
    "ExecutionEnvironment",
    "LocalExecutionEnvironment",
)

"""Cross-platform execution sandbox contracts and backends.

Only the macOS-native Seatbelt backend is implemented today.  Tool code uses
the ``ExecutionEnvironment`` contract and does not depend on platform details.
"""

from .host import MAX_OUTPUT, CommandResult, ExecutionEnvironment, LocalExecutionEnvironment
from .macos_seatbelt import MacOSSeatbeltEnvironment

__all__ = (
    "CommandResult",
    "ExecutionEnvironment",
    "LocalExecutionEnvironment",
    "MacOSSeatbeltEnvironment",
    "MAX_OUTPUT",
)

from .store import save_conversation_memory, sanitize_event_value

from ._files import (
    MEMORY_LAYER_FILES,
    atomic_write_text,
    contains_injection,
    contains_secret,
    safe_file_in_dir,
    safe_markdown_files,
    sanitize_memory_text,
)

__all__ = [
    "save_conversation_memory",
    "sanitize_event_value",
    "MEMORY_LAYER_FILES",
    "atomic_write_text",
    "contains_injection",
    "contains_secret",
    "safe_file_in_dir",
    "safe_markdown_files",
    "sanitize_memory_text",
]

from .dream import run_dream, DreamReport, dream_report_completed
from .compile import run_compilation, assemble_memory

__all__ += [
    "run_dream",
    "DreamReport",
    "dream_report_completed",
    "run_compilation",
    "assemble_memory",
]

# search depends on aiosqlite, which may be absent when this package is
# imported standalone by content-layer tools; everything else is stdlib-only.
try:
    from .search import SearchIndex
    __all__ += ["SearchIndex"]
except ModuleNotFoundError:
    pass

from .interface import MemoryEntry, MemoryStore
from .store import save_conversation_memory

__all__ = [
    "MemoryEntry",
    "MemoryStore",
    "save_conversation_memory",
]

try:
    from .dream import run_dream, DreamReport
    __all__ += ["run_dream", "DreamReport"]
except ModuleNotFoundError:
    pass

try:
    from .compile import run_compilation, assemble_memory
    __all__ += ["run_compilation", "assemble_memory"]
except ModuleNotFoundError:
    pass

try:
    from .search import SearchIndex
    __all__ += ["SearchIndex"]
except ModuleNotFoundError:
    pass

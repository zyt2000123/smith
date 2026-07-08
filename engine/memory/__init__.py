from .interface import MemoryEntry, MemoryStore
from .store import FileMemoryStore, save_conversation_memory

__all__ = [
    "MemoryEntry",
    "MemoryStore",
    "FileMemoryStore",
    "save_conversation_memory",
]

try:
    from .dream import DreamConsolidator, DreamReport
    __all__ += ["DreamConsolidator", "DreamReport"]
except ModuleNotFoundError:
    pass

try:
    from .compile import run_compilation, assemble_memory
    __all__ += ["run_compilation", "assemble_memory"]
except ModuleNotFoundError:
    pass

try:
    from .search import SearchIndex, create_jina_embed_fn
    __all__ += ["SearchIndex", "create_jina_embed_fn"]
except ModuleNotFoundError:
    pass

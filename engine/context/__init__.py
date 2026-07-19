"""Model-input context lifecycle: assembly, budgeting, and session compaction."""

from .assembler import AssembledPrompt, PromptAssembler, PromptLayer, PromptManifest
from .compression import (
    CONTEXT_DISPLAY_WINDOW,
    compact_history,
    compress,
    estimate_tokens,
    needs_compaction,
    prompt_budget_for_llm,
)

__all__ = (
    "AssembledPrompt",
    "CONTEXT_DISPLAY_WINDOW",
    "PromptAssembler",
    "PromptLayer",
    "PromptManifest",
    "compact_history",
    "compress",
    "estimate_tokens",
    "needs_compaction",
    "prompt_budget_for_llm",
)

from __future__ import annotations

"""Knowledge search tool provider — stub for Hub knowledge search."""

TOOL_META = {
    "name": "search_knowledge",
    "description": "Search the knowledge hub for relevant documents, guides, and references.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query string"
            },
            "top_k": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 5
            },
            "category": {
                "type": "string",
                "description": "Optional category filter (e.g., 'api-docs', 'architecture', 'guides')"
            }
        },
        "required": ["query"]
    }
}


async def execute(
    *, query: str, top_k: int = 5, category: str | None = None
) -> str:
    # Stub implementation — will be connected to the Hub's knowledge index.
    # In production, this queries the vector store / full-text index in the Hub.
    return (
        f"[search_knowledge stub] query={query!r}, top_k={top_k}, "
        f"category={category!r}\n"
        f"No results — knowledge hub not connected. "
        f"Connect via Hub configuration to enable knowledge search."
    )

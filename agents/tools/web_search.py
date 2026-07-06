"""Web search tool provider — DuckDuckGo HTML endpoint, no API key required.

Provider 字段预留：后续可接 tavily / brave / bing_browser（对齐 OpenHanako 分层）。
"""

import asyncio
import html
import re
import urllib.parse
import urllib.request

TOOL_META = {
    "name": "web_search",
    "description": (
        "Search the web and return a list of results (title, URL, snippet). "
        "Use this to DISCOVER pages, then use web_fetch to read a specific URL."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keywords"
            },
            "max_results": {
                "type": "integer",
                "description": "Max results to return (default 5, max 10)",
                "default": 5
            },
            "provider": {
                "type": "string",
                "description": "Search provider (currently only 'duckduckgo')",
                "default": "duckduckgo"
            }
        },
        "required": ["query"]
    }
}

_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S
)
_SNIPPET_RE = re.compile(
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', re.S
)
_TAG_RE = re.compile(r"<[^>]+>")


def _decode_ddg_url(href: str) -> str:
    """DDG 结果链接是 //duckduckgo.com/l/?uddg=<encoded> 跳转，解出真实 URL。"""
    if "uddg=" in href:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        if qs.get("uddg"):
            return qs["uddg"][0]
    return href


def _clean(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text)).strip()


async def execute(*, query: str, max_results: int = 5, provider: str = "duckduckgo") -> str:
    max_results = min(max(1, max_results), 10)
    if provider != "duckduckgo":
        return f"Error: provider '{provider}' not supported yet. Use 'duckduckgo'."

    def _fetch() -> str:
        # GET 会触发 DDG 反爬 anomaly 页，POST 表单可正常返回结果
        data = urllib.parse.urlencode({"q": query}).encode()
        req = urllib.request.Request(
            "https://html.duckduckgo.com/html/",
            data=data,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read(512 * 1024).decode("utf-8", errors="replace")

    loop = asyncio.get_event_loop()
    try:
        page = await loop.run_in_executor(None, _fetch)
    except Exception as e:
        return f"Error: search request failed: {e}"

    links = _RESULT_RE.findall(page)
    snippets = [_clean(s) for s in _SNIPPET_RE.findall(page)]

    if not links:
        return f"No results for '{query}' (or search engine blocked the request)."

    lines = [f"Search results for: {query}"]
    for i, (href, title) in enumerate(links[:max_results]):
        real_url = _decode_ddg_url(href)
        snippet = snippets[i] if i < len(snippets) else ""
        lines.append(f"\n{i + 1}. {_clean(title)}\n   {real_url}\n   {snippet}")
    return "\n".join(lines)

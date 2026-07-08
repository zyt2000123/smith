"""Web fetch tool provider — headless-browser rendering via crawl4ai, markdown output.

JS 渲染页面（SPA / 动态加载）也能抓到正文；crawl4ai 不可用或失败时退回 urllib 原始抓取。
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request

TOOL_META = {
    "name": "web_fetch",
    "description": (
        "Fetch a URL and return its main content as clean markdown "
        "(renders JavaScript via headless browser, works on SPAs). "
        "Use web_search first to discover URLs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch"
            },
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds (default 30, max 60)",
                "default": 30
            }
        },
        "required": ["url"]
    }
}

MAX_CHARS = 40_000
MAX_TIMEOUT = 60
BLOCKED_SCHEMES = {"file", "ftp", "data"}
BLOCKED_HOSTS = {"localhost"}


def _blocked_ip_reason(host: str) -> str | None:
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None

    if ip.is_loopback:
        return "loopback address"
    if ip.is_private:
        return "private network address"
    if ip.is_link_local:
        return "link-local address"
    if ip.is_multicast:
        return "multicast address"
    if ip.is_reserved:
        return "reserved address"
    if ip.is_unspecified:
        return "unspecified address"
    return None


def _validate_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme in BLOCKED_SCHEMES:
        return f"scheme '{scheme}' is not allowed. Only http/https supported."
    if scheme not in {"http", "https"}:
        return "URL must start with http:// or https://"
    if not parsed.hostname:
        return "URL must include a hostname"

    host = parsed.hostname.rstrip(".").lower()
    if host in BLOCKED_HOSTS or host.endswith(".localhost"):
        return "localhost targets are not allowed"

    reason = _blocked_ip_reason(host)
    if reason:
        return f"host resolves to a blocked {reason}"

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        return f"could not resolve host '{host}': {e}"

    for info in infos:
        sockaddr = info[4]
        resolved_host = sockaddr[0]
        reason = _blocked_ip_reason(resolved_host)
        if reason:
            return f"host resolves to a blocked {reason}: {resolved_host}"

    return None


async def execute(*, url: str, timeout: int = 30) -> str:
    timeout = min(max(1, timeout), MAX_TIMEOUT)

    validation_error = _validate_url(url)
    if validation_error:
        return f"Error: {validation_error}"

    try:
        return await _fetch_browser(url, timeout)
    except Exception as e:
        raw = await _fetch_plain(url, timeout)
        return f"[browser fetch failed: {type(e).__name__}: {e}; fell back to plain HTTP]\n{raw}"


async def _fetch_browser(url: str, timeout: int) -> str:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

    browser_cfg = BrowserConfig(headless=True, verbose=False)
    run_cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=timeout * 1000,
        verbose=False,
    )
    # ponytail: 每次调用起一个浏览器实例（1-2s 开销）；高频场景可改为模块级共享实例
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        result = await crawler.arun(url=url, config=run_cfg)

    if not result.success:
        raise RuntimeError(result.error_message or "crawl failed")

    md = str(result.markdown or "").strip()
    if not md:
        raise RuntimeError("empty content after rendering")

    truncated = len(md) > MAX_CHARS
    if truncated:
        md = md[:MAX_CHARS]
    header = f"[fetched via headless browser, markdown, {len(md)} chars"
    header += ", truncated]" if truncated else "]"
    return f"{header}\n{md}"


async def _fetch_plain(url: str, timeout: int) -> str:
    """urllib 兜底：无浏览器环境或渲染失败时仍可抓静态页。"""

    def _fetch():
        req = urllib.request.Request(url, headers={"User-Agent": "AgentSmith/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read(MAX_CHARS + 1)
                truncated = len(data) > MAX_CHARS
                text = data[:MAX_CHARS].decode("utf-8", errors="replace")
                return f"[status={resp.status}{', truncated' if truncated else ''}]\n{text}"
        except urllib.error.HTTPError as e:
            return f"HTTP Error: {e.code} {e.reason}"
        except urllib.error.URLError as e:
            return f"URL Error: {e.reason}"

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch)

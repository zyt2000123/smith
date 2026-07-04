"""Web fetch tool provider — fetches URL content with timeout and size limits."""

import asyncio
import urllib.request
import urllib.error

TOOL_META = {
    "name": "web_fetch",
    "description": "Fetch content from a URL. Returns text content with size limits.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch"
            },
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds (default 15, max 30)",
                "default": 15
            }
        },
        "required": ["url"]
    }
}

MAX_CONTENT = 50 * 1024  # 50KB
MAX_TIMEOUT = 30
BLOCKED_SCHEMES = {"file", "ftp", "data"}


async def execute(*, url: str, timeout: int = 15) -> str:
    timeout = min(max(1, timeout), MAX_TIMEOUT)

    scheme = url.split("://")[0].lower() if "://" in url else ""
    if scheme in BLOCKED_SCHEMES:
        return f"Error: scheme '{scheme}' is not allowed. Only http/https supported."

    if not url.startswith(("http://", "https://")):
        return "Error: URL must start with http:// or https://"

    def _fetch():
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AgentSmith/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")
                data = resp.read(MAX_CONTENT + 1)
                truncated = len(data) > MAX_CONTENT
                if truncated:
                    data = data[:MAX_CONTENT]
                text = data.decode("utf-8", errors="replace")
                status = resp.status
                return status, content_type, text, truncated
        except urllib.error.HTTPError as e:
            return e.code, "", f"HTTP Error: {e.code} {e.reason}", False
        except urllib.error.URLError as e:
            return 0, "", f"URL Error: {e.reason}", False
        except TimeoutError:
            return 0, "", f"Error: request timed out after {timeout}s", False

    loop = asyncio.get_event_loop()
    status, content_type, text, truncated = await loop.run_in_executor(
        None, _fetch
    )

    header = f"[status={status}, content_type={content_type}]"
    if truncated:
        header += f" (truncated to {MAX_CONTENT} bytes)"
    return f"{header}\n{text}"

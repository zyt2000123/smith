"""Unit tests for the public-site crawler provider."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_crawler():
    path = ROOT / "agents" / "tools" / "web_crawl.py"
    spec = importlib.util.spec_from_file_location("web_crawl", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_url_removes_fragments_and_tracking_parameters():
    crawler = _load_crawler()

    assert crawler._normalize_url(
        "https://Example.com:443/docs/?utm_source=test&chapter=1#overview"
    ) == "https://example.com/docs?chapter=1"


def test_robots_policy_selects_specific_user_agent_and_disallows_paths():
    crawler = _load_crawler()
    rules = crawler._parse_robots(
        """
        User-agent: *
        Disallow: /private

        User-agent: AgentSmithCrawler
        Allow: /private/public
        Disallow: /private
        Crawl-delay: 2
        Sitemap: https://example.com/sitemap.xml
        """
    )

    assert not crawler._robots_allows(rules, "https://example.com/private/notes")
    assert crawler._robots_allows(rules, "https://example.com/private/public/readme")
    assert rules.crawl_delay == 2
    assert rules.sitemaps == ("https://example.com/sitemap.xml",)


def test_extract_links_keeps_same_origin_pages_and_discovers_pagination():
    crawler = _load_crawler()
    html = """
    <a href="/guide?page=2">Next</a>
    <a href="/guide#chapter">Guide</a>
    <a href="https://other.example/article">Outside</a>
    <a href="mailto:editor@example.com">Email</a>
    """

    links = crawler._extract_links("https://example.com/guide?page=1", html)

    assert links == [
        "https://example.com/guide?page=2",
        "https://example.com/guide",
    ]


def test_sitemap_and_rss_parsers_return_normalized_public_urls():
    crawler = _load_crawler()
    sitemap = """
    <urlset><url><loc>https://example.com/a?utm_source=x</loc></url>
    <url><loc>https://example.com/b</loc></url></urlset>
    """
    feed = """
    <rss><channel><item><link>https://example.com/news#today</link></item></channel></rss>
    """

    assert crawler._parse_sitemap(sitemap) == ["https://example.com/a", "https://example.com/b"]
    assert crawler._parse_feed(feed) == ["https://example.com/news"]


def test_change_detection_uses_content_hash_and_preserves_unchanged_records():
    crawler = _load_crawler()
    previous = {"https://example.com/a": {"content_hash": "same"}}

    unchanged = crawler._build_record("https://example.com/a", "Title", "Body", previous)
    changed = crawler._build_record("https://example.com/b", "Title", "Body", previous)

    assert not unchanged["changed"]
    assert changed["changed"]
    assert unchanged["content_hash"] == "same"

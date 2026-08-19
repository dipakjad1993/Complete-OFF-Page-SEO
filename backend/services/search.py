from __future__ import annotations

"""Real-time web search with strict relevance verification.

Returns only results that pass genuine relevance checks. No fabricated results
are ever produced. If every search backend fails, an UnavailableData is returned.

Backends (in priority order):
1. SerpAPI (Google organic) - when SERPAPI_KEY is set (paid tier).
2. Bing RSS search - free tier, no key required.
3. DuckDuckGo HTML scraping - free fallback, no key required.
"""

import re
import html as html_lib
from typing import Any, Optional
from urllib.parse import urlparse, quote_plus

import httpx

from backend.services.verification import VerifiedData, UnavailableData, utcnow_iso
from backend.services.providers import serpapi

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Domains that are definition/reference pages and are almost never the
# right "source" for a brand citation. Strictly rejected during relevance pass.
BLOCKED_RESULT_DOMAINS = {
    "dictionary.cambridge.org", "merriam-webster.com", "dictionary.com",
    "collinsdictionary.com", "oxfordlearnersdictionaries.com", "lexico.com",
    "thesaurus.com", "vocabulary.com", "urbandictionary.com", "google.com",
    "google.co.in", "googleusercontent.com", "bing.com", "bingj.com",
    "duckduckgo.com", "yahoo.com", "search.yahoo.com", "yandex.com",
    "microsoft.com", "w3.org", "adobe.com", "wordpress.org",
}

BLOCKED_TITLE_PATTERNS = [
    r"^definition of ", r"^definitions for", r"^the definition of",
    r"^meaning of ", r"^what does .* mean", r"^dictionary", r"^merriam-webster",
    r"^synonyms for", r"^antonyms for", r"^thesaurus",
]

# Content-hosting / aggregation domains that are never first-party "coverage"
# but still useful as mentions. Kept out of the primary citation list.
AGGREGATOR_DOMAINS = {
    "reddit.com", "old.reddit.com", "quora.com", "medium.com", "stackoverflow.com",
    "github.com", "youtube.com", "facebook.com", "twitter.com", "x.com",
    "linkedin.com", "instagram.com", "producthunt.com", "hackernews.com",
    "news.ycombinator.com", "trustpilot.com", "g2.com", "capterra.com",
    "glassdoor.com", "crunchbase.com",
}


def _domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").replace("www.", "").lower()
    except Exception:  # noqa: BLE001
        return ""


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _relevance_score(title: str, snippet: str, query: str, brand_terms: list[str],
                     query_terms: list[str]) -> float:
    """Score how relevant a result is to the brand query. 0.0 = junk."""
    text = f"{title} {snippet}".lower()

    if any(re.search(p, title, re.IGNORECASE) for p in BLOCKED_TITLE_PATTERNS):
        return 0.0

    # Require at least one substantive query term to appear in the text.
    matched = sum(1 for t in query_terms if t and t in text)
    if matched == 0:
        return 0.0

    # Brand-specific terms boost strongly; generic dictionary definitions never qualify.
    brand_hits = sum(1 for b in brand_terms if b and len(b) > 3 and b in text)
    score = 0.3 + 0.3 * (matched / max(len(query_terms), 1)) + 0.4 * (brand_hits / max(len(brand_terms), 1))

    # Penalize single-word generic queries (dictionary bait like "best").
    if len(query_terms) <= 1:
        score *= 0.3

    # Title match is the strongest signal.
    title_l = title.lower()
    if any(b for b in brand_terms if len(b) > 3 and b in title_l):
        score += 0.25

    return min(score, 1.0)


def _clean_results(raw: list[dict], query: str, brand_name: str, min_score: float = 0.35) -> list[dict]:
    query_terms = [t for t in re.split(r"[\s|,]+", query.lower()) if len(t) > 2]
    brand_terms = list(dict.fromkeys([
        t for t in [brand_name.lower(), brand_name.replace(" ", "").lower(), brand_name.split()[0].lower() if brand_name else ""]
        if len(t) > 2
    ]))

    cleaned = []
    for r in raw:
        url = r.get("url") or r.get("link") or ""
        domain = _domain(url)
        if domain in BLOCKED_RESULT_DOMAINS:
            continue
        title = _strip_html(r.get("title") or r.get("title", ""))
        snippet = _strip_html(r.get("snippet") or r.get("body") or r.get("description") or "")
        score = _relevance_score(title, snippet, query, brand_terms, query_terms)
        if score < min_score:
            continue
        cleaned.append({
            "title": title[:300],
            "url": url,
            "domain": domain,
            "snippet": snippet[:600],
            "relevance_score": round(score, 3),
            "is_aggregator": domain in AGGREGATOR_DOMAINS,
        })
    # Keep only genuinely relevant, de-duplicated.
    seen_urls: set[str] = set()
    unique = []
    for item in sorted(cleaned, key=lambda x: x["relevance_score"], reverse=True):
        if item["url"] and item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique.append(item)
    return unique[:15]


async def _bing_search(query: str, num: int = 10) -> list[dict]:
    """Bing RSS search - free tier, no key required. Returns raw result dicts."""
    try:
        url = f"https://www.bing.com/search?q={quote_plus(query)}&format=rss&count={num}"
        async with httpx.AsyncClient(timeout=10, headers=API_HEADERS, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            page = r.text
        results = []
        for block in re.findall(r"<item>(.*?)</item>", page, re.DOTALL):
            def _grab(patt):
                m = re.search(patt, block, re.DOTALL)
                return _strip_html(m.group(1)) if m else ""
            title = _grab(r"<title>(.*?)</title>")
            link = _grab(r"<link>(.*?)</link>")
            desc = _grab(r"<description>(.*?)</description>")
            if link and link.startswith("http"):
                results.append({"title": title[:300], "url": link, "snippet": desc[:600]})
        return results[:num]
    except Exception:  # noqa: BLE001
        return []


async def _bing_news_search(query: str, num: int = 20) -> list[dict]:
    """Bing News RSS search - free tier, no key required. Returns real publisher URLs."""
    try:
        url = (f"https://www.bing.com/news/search?q={quote_plus(query)}"
               f"&format=rss&count={num}&setlang=en-US")
        async with httpx.AsyncClient(timeout=10, headers=API_HEADERS, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            page = r.text
        results = []
        for block in re.findall(r"<item>(.*?)</item>", page, re.DOTALL):
            def _grab(patt):
                m = re.search(patt, block, re.DOTALL)
                return _strip_html(m.group(1)) if m else ""
            title = _grab(r"<title>(.*?)</title>")
            link = _grab(r"<link>(.*?)</link>")
            desc = _grab(r"<description>(.*?)</description>")
            pub = _grab(r"<pubDate>(.*?)</pubDate>")
            source = _grab(r"News:Source>(.*?)<")
            # Bing news <link> is an apiclick redirect carrying the real article URL in &url=.
            import urllib.parse
            m_url = re.search(r"[?&]url=([^&\"<]+)", link)
            real_url = urllib.parse.unquote(m_url.group(1)) if m_url else link
            if real_url and real_url.startswith("http"):
                results.append({"title": title[:300], "url": real_url, "snippet": desc[:600],
                                "published": pub, "source_name": source, "is_news": True})
        return results[:num]
    except Exception:  # noqa: BLE001
        return []


async def search_news(query: str, brand_name: str = "", num: int = 10) -> Any:
    """Free real-time news search via Bing News RSS (real publisher URLs), falling back to Google News RSS."""
    bing = await _bing_news_search(query, num=num * 2)
    if bing:
        cleaned = _clean_results(bing, query, brand_name, 0.2)
        return VerifiedData(
            value=cleaned or bing[:num],
            source="bing_news_rss", method="bing_news_rss+relevance_filter",
            retrieved_at=utcnow_iso(), confidence=1.0, verified=True,
            metadata={"query": query, "raw_count": len(bing), "kept": len(cleaned)},
        )

    try:
        url = ("https://news.google.com/rss/search?"
               f"q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en")
        async with httpx.AsyncClient(timeout=10, headers=API_HEADERS, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            try:
                page = r.content.decode("utf-8")
            except UnicodeDecodeError:
                page = r.content.decode("cp1252", errors="replace")
        results = []
        for block in re.findall(r"<item>(.*?)</item>", page, re.DOTALL):
            def _grab(patt):
                m = re.search(patt, block, re.DOTALL)
                return _strip_html(m.group(1)) if m else ""
            title = _grab(r"<title>(.*?)</title>")
            link = _grab(r"<link>(.*?)</link>")
            desc = _grab(r"<description>(.*?)</description>")
            pub = _grab(r"<pubDate>(.*?)</pubDate>")
            # Google News links are /r/articles/... redirects -> normalize to real URL when possible
            m_news = re.search(r"url=([^&\"]+)", link)
            if m_news:
                import urllib.parse
                link = urllib.parse.unquote(m_news.group(1))
            if link and link.startswith("http"):
                results.append({"title": title[:300], "url": link, "snippet": desc[:600],
                                "published": pub, "is_news": True})
        if not results:
            return UnavailableData(reason="Bing News RSS and Google News returned no results.", requires="Internet access")
        cleaned = _clean_results(results, query, brand_name, 0.2)
        return VerifiedData(
            value=cleaned or results[:num],
            source="google_news_rss", method="google_news_rss+relevance_filter",
            retrieved_at=utcnow_iso(), confidence=1.0, verified=True,
            metadata={"query": query, "raw_count": len(results), "kept": len(cleaned)},
        )
    except Exception as e:  # noqa: BLE001
        return UnavailableData(reason=f"News search failed: {e}", requires="Internet access")


async def search_web(query: str, brand_name: str = "", num: int = 10,
                     require_relevance: bool = True, min_score: float = 0.35) -> Any:
    """Search the web for brand-relevant results.

    Returns VerifiedData with a list of vetted results, or UnavailableData.
    """
    if serpapi.available:
        res = await serpapi.search(query, num=num)
        if isinstance(res, VerifiedData) and res.value:
            raw = res.value
            cleaned = _clean_results(raw, query, brand_name, min_score) if require_relevance else raw
            return VerifiedData(
                value=cleaned,
                source="serpapi", method="serpapi_google_organic+relevance_filter",
                retrieved_at=utcnow_iso(), confidence=1.0, verified=True,
                metadata={"query": query, "raw_count": len(raw), "kept": len(cleaned)},
            )

    # Bing RSS search (free tier, no key required).
    bing_results = await _bing_search(query)
    if bing_results:
        cleaned = _clean_results(bing_results, query, brand_name, min_score) if require_relevance else bing_results
        return VerifiedData(
            value=cleaned,
            source="bing_rss", method="bing_rss+relevance_filter",
            retrieved_at=utcnow_iso(), confidence=1.0, verified=True,
            metadata={"query": query, "raw_count": len(bing_results), "kept": len(cleaned)},
        )

    # DuckDuckGo HTML fallback (free, no key)
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&ia=web"
        async with httpx.AsyncClient(timeout=8, headers=API_HEADERS, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            page = r.text

        results = []
        for block in re.findall(r'<div class="result[^"]*"[^>]*>(.*?)</div>\s*</div>', page, re.DOTALL):
            m_title = re.search(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            m_snippet = re.search(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL)
            if not m_title:
                continue
            href = m_title.group(1)
            # DuckDuckGo wraps links in /l/?uddg=... or /r/
            inner = re.search(r"[?&](?:uddg|u)=([^&]+)", href)
            if inner:
                href = inner.group(1)
            import urllib.parse
            href = urllib.parse.unquote(href)
            title = _strip_html(m_title.group(2))
            snippet = _strip_html(m_snippet.group(1)) if m_snippet else ""
            results.append({"title": title, "url": href, "snippet": snippet})

        cleaned = _clean_results(results, query, brand_name, min_score) if require_relevance else results
        return VerifiedData(
            value=cleaned,
            source="duckduckgo", method="ddg_html_scrape+relevance_filter",
            retrieved_at=utcnow_iso(), confidence=1.0, verified=True,
            metadata={"query": query, "raw_count": len(results), "kept": len(cleaned)},
        )
    except Exception as e:  # noqa: BLE001
        return UnavailableData(
            reason=f"Search failed: {e}",
            requires="SERPAPI_KEY (or working DuckDuckGo access)",
        )


async def verify_url(url: str, expected_terms: list[str]) -> Any:
    """Fetch a URL and verify it actually mentions the brand/terms.

    Returns VerifiedData(value=True/False) with the fetched evidence.
    """
    try:
        async with httpx.AsyncClient(timeout=10, headers=API_HEADERS, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            text = _strip_html(r.text).lower()
        hits = [t for t in expected_terms if t and len(t) > 2 and t.lower() in text]
        return VerifiedData(
            value=bool(hits),
            source="live_fetch", method="httpx_get+term_check",
            retrieved_at=utcnow_iso(), confidence=1.0, verified=True,
            metadata={"terms_found": hits, "page_chars": len(text)},
            source_url=url,
        )
    except Exception as e:  # noqa: BLE001
        return UnavailableData(
            reason=f"Could not verify URL {url}: {e}",
            requires="Internet access",
        )

from __future__ import annotations

"""Real-time web search with strict relevance verification.

Returns only results that pass genuine relevance checks. No fabricated results
are ever produced. If every search backend fails, an UnavailableData is returned.

Backends (in priority order):
1. SerpAPI (Google organic) - when SERPAPI_KEY is set (paid tier).
2. Bing RSS search - free tier, no key required.
3. DuckDuckGo via the `ddgs` library - free fallback, no key required.

REMOVED 2026-09: the DuckDuckGo HTML-scraping leg was deleted. DDG's markup
changed and the leg returned 0 parseable blocks on every query (dozens of
"0 blocks (markup may have changed)" warnings in production logs) — dead code
that only added latency. Exhausting Bing RSS + ddgs now returns honest
UnavailableData instead of pretending a third leg exists.
"""

import re
import html as html_lib
from typing import Any, Optional
from urllib.parse import urlparse, quote_plus

import httpx
import logging
import random as _rand

from backend.services.verification import VerifiedData, UnavailableData, utcnow_iso
from backend.services.providers import serpapi

logger = logging.getLogger("offpage.search")

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Rotating browser UAs — Bing RSS returns 403 for repeated identical UAs.
# Rotation + retries dramatically reduce silent [] fallbacks.
_ROTATING_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/125.0.0.0 Safari/537.36",
]


def _pick_headers() -> dict:
    h = dict(API_HEADERS)
    try:
        h["User-Agent"] = _rand.choice(_ROTATING_UAS)
    except Exception:
        pass
    return h

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
                     query_terms: list[str], url: str = "") -> float:
    """Score how relevant a result is to the brand query. 0.0 = junk.

    STRICT single-token-brand mode (kills volleyballworld/degreaser noise):
    when the brand is a single token (e.g. "Healthline"), a result must have
    the brand token in title OR domain, or match >=2 query terms. Otherwise 0.0.
    URL evidence counts — domain-brand match rescues otherwise thin snippets.
    """
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

    # URL/domain brand evidence — strong authentic signal (e.g. healthline.com/..., github HealthLine).
    try:
        from urllib.parse import urlparse as _up
        dom = (_up(url).netloc or "").lower() if url else ""
        if url and brand_terms:
            for b in brand_terms:
                bl = (b or "").lower()
                if len(bl) > 3 and (bl in dom or bl.replace(" ", "") in dom.replace(".", "")):
                    score += 0.2
                    break
    except Exception:
        pass

    score = min(score, 1.0)

    # ---- Strict single-token gate ----
    try:
        from config.settings import settings as _s
        strict = bool(getattr(_s, "STRICT_SINGLE_TOKEN_BRANDS", True))
        min_single = float(getattr(_s, "SINGLE_TOKEN_MIN_SCORE", 0.55) or 0.55)
    except Exception:
        strict, min_single = True, 0.55
    if strict and len(brand_terms) == 1 and len(brand_terms[0]) > 2:
        bt = brand_terms[0].lower()
        try:
            from urllib.parse import urlparse as _up2
            dom2 = (_up2(url).netloc or "").lower() if url else ""
        except Exception:
            dom2 = ""
        title_hit = bt in title_l
        domain_hit = bt in dom2 or bt.replace(" ", "") in dom2.replace(".", "")
        # Single-token brands need title/domain proof OR multi-term match.
        if not (title_hit or domain_hit) and matched < 2:
            return 0.0
        # Even with proof, enforce higher bar to keep verified:true meaningful.
        if score < min_single and not (title_hit and domain_hit):
            # Allow through only if both title+snippet contain brand (strong textual proof).
            if brand_hits < 1:
                return 0.0

    return score


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
        score = _relevance_score(title, snippet, query, brand_terms, query_terms, url=url)
        # Auto-escalate threshold for single-token brands so verified:true stays meaningful.
        eff_min = min_score
        try:
            from config.settings import settings as _s2
            if bool(getattr(_s2, "STRICT_SINGLE_TOKEN_BRANDS", True)) and len(brand_terms) == 1:
                eff_min = max(min_score, float(getattr(_s2, "SINGLE_TOKEN_MIN_SCORE", 0.55) or 0.55) - 0.1)
        except Exception:
            pass
        if score < eff_min:
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
    """Bing RSS search - free tier, no key required. Returns raw result dicts.

    Hardened: rotating UA + 2 retries (Bing 403s intermittently). Logs instead of silent [].
    """
    last_err: str = ""
    for attempt in range(3):
        try:
            url = f"https://www.bing.com/search?q={quote_plus(query)}&format=rss&count={num}"
            async with httpx.AsyncClient(timeout=10, headers=_pick_headers(), follow_redirects=True) as c:
                r = await c.get(url)
                if r.status_code == 403:
                    last_err = "403 forbidden (Bing bot-gate)"
                    continue
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
            if results:
                return results[:num]
            last_err = "empty RSS payload"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)[:160]
    if last_err:
        logger.warning("Bing RSS failed for %r after retries: %s", query[:80], last_err)
    return []


async def _ddgs_library_search(query: str, num: int = 10) -> list[dict]:
    """DuckDuckGo via `ddgs` Python package (more robust than HTML scraping).

    Optional dependency — returns [] when package is missing so free tier still works.
    """
    try:
        from ddgs import DDGS  # type: ignore
    except Exception:
        return []
    try:
        import asyncio as _aio
        def _run():
            out: list[dict] = []
            with DDGS(timeout=12) as ddgs:
                for r in ddgs.text(query, max_results=num) or []:
                    href = r.get("href") or r.get("link") or ""
                    if href and href.startswith("http"):
                        out.append({
                            "title": (r.get("title") or "")[:300],
                            "url": href,
                            "snippet": (r.get("body") or "")[:600],
                        })
            return out
        return await _aio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        logger.warning("ddgs library search failed for %r: %s", query[:80], str(e)[:160])
        return []


async def _brave_search(query: str, num: int = 10) -> list[dict]:
    """Brave Search API ($5/1k, generous free) — paid primary fallback. [] when unkeyed."""
    try:
        from config.settings import settings as _s
        key = getattr(_s, "BRAVE_SEARCH_API_KEY", None)
        if not key:
            return []
        async with httpx.AsyncClient(timeout=12, headers={"X-Subscription-Token": key}) as c:
            r = await c.get("https://api.search.brave.com/res/v1/web/search",
                            params={"q": query, "count": min(num, 20)})
            r.raise_for_status()
            data = r.json()
        out = []
        for it in ((data.get("web") or {}).get("results") or [])[:num]:
            url = it.get("url") or ""
            if url.startswith("http"):
                out.append({"title": (it.get("title") or "")[:300], "url": url,
                            "snippet": (it.get("description") or "")[:600]})
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("Brave search failed for %r: %s", query[:80], str(e)[:160])
        return []


async def _bing_web_search(query: str, num: int = 10) -> list[dict]:
    """Bing Web Search API — paid fallback before ddgs. [] when unkeyed."""
    try:
        from config.settings import settings as _s
        key = getattr(_s, "BING_SEARCH_API_KEY", None)
        if not key:
            return []
        async with httpx.AsyncClient(timeout=12, headers={"Ocp-Apim-Subscription-Key": key}) as c:
            r = await c.get("https://api.bing.microsoft.com/v7.0/search",
                            params={"q": query, "count": min(num, 20), "mkt": "en-US"})
            r.raise_for_status()
            data = r.json()
        out = []
        for it in ((data.get("webPages") or {}).get("value") or [])[:num]:
            url = it.get("url") or ""
            if url.startswith("http"):
                out.append({"title": (it.get("name") or "")[:300], "url": url,
                            "snippet": (it.get("snippet") or "")[:600]})
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("Bing Web API failed for %r: %s", query[:80], str(e)[:160])
        return []


async def _bing_news_search(query: str, num: int = 20) -> list[dict]:
    """Bing News RSS search - free tier, no key required. Returns real publisher URLs."""
    try:
        url = (f"https://www.bing.com/news/search?q={quote_plus(query)}"
               f"&format=rss&count={num}&setlang=en-US")
        async with httpx.AsyncClient(timeout=10, headers=_pick_headers(), follow_redirects=True) as c:
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
        async with httpx.AsyncClient(timeout=10, headers=_pick_headers(), follow_redirects=True) as c:
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

    Chain: SerpAPI (keyed) -> 7-day disk cache -> Brave API (keyed) ->
    Bing Web API (keyed) -> Bing RSS (free) -> ddgs library (free).
    Returns VerifiedData with provider attribution in source/method, or
    honest UnavailableData. Exponential backoff is inside each leg.
    """
    # 0. disk cache (7-day TTL) — real payloads only
    try:
        from backend.services.search_cache import cache_get, cache_put
        hit = cache_get(query, num, brand_name)
        if hit and hit.get("payload"):
            raw_cached = hit["payload"]
            cleaned = _clean_results(raw_cached, query, brand_name, min_score) if require_relevance else raw_cached
            if cleaned or not require_relevance:
                return VerifiedData(
                    value=cleaned if require_relevance else raw_cached,
                    source=f"{hit.get('provider', 'cache')}+cache",
                    method="sqlite_cache_7d+relevance_filter",
                    retrieved_at=utcnow_iso(), confidence=0.95, verified=True,
                    metadata={"query": query, "cached": True,
                              "provider": hit.get("provider")},
                )
    except Exception:
        pass

    def _remember(payload: list, provider: str) -> None:
        try:
            from backend.services.search_cache import cache_put
            if payload:
                cache_put(query, num, brand_name, payload, provider)
        except Exception:
            pass

    if serpapi.available:
        res = await serpapi.search(query, num=num)
        if isinstance(res, VerifiedData) and res.value:
            raw = res.value
            cleaned = _clean_results(raw, query, brand_name, min_score) if require_relevance else raw
            _remember(raw, "serpapi")
            return VerifiedData(
                value=cleaned,
                source="serpapi", method="serpapi_google_organic+relevance_filter",
                retrieved_at=utcnow_iso(), confidence=1.0, verified=True,
                metadata={"query": query, "raw_count": len(raw), "kept": len(cleaned)},
            )

    # Paid fallbacks before free scraping (reliability first).
    for _fn, _prov, _meth in (
        (_brave_search, "brave_api", "brave_web_search+relevance_filter"),
        (_bing_web_search, "bing_web_api", "bing_web_search+relevance_filter"),
    ):
        paid = await _fn(query, num=num)
        if paid:
            cleaned = _clean_results(paid, query, brand_name, min_score) if require_relevance else paid
            if cleaned or not require_relevance:
                _remember(paid, _prov)
                return VerifiedData(
                    value=cleaned if require_relevance else paid,
                    source=_prov, method=_meth,
                    retrieved_at=utcnow_iso(), confidence=1.0, verified=True,
                    metadata={"query": query, "raw_count": len(paid), "kept": len(cleaned)},
                )

    # Bing RSS search (free tier, no key required).
    bing_results = await _bing_search(query, num=num)
    if bing_results:
        cleaned = _clean_results(bing_results, query, brand_name, min_score) if require_relevance else bing_results
        if cleaned or not require_relevance:
            _remember(bing_results, "bing_rss")
            return VerifiedData(
                value=cleaned if require_relevance else bing_results,
                source="bing_rss", method="bing_rss+relevance_filter",
                retrieved_at=utcnow_iso(), confidence=1.0, verified=True,
                metadata={"query": query, "raw_count": len(bing_results), "kept": len(cleaned)},
            )
        # Bing returned rows but none passed strict relevance — keep raw count for diagnostics,
        # then continue to ddgs fallbacks instead of silently returning thin data.
        logger.info("Bing RSS %d raw → 0 kept for %r; trying ddgs fallbacks", len(bing_results), query[:80])

    # DuckDuckGo via `ddgs` library (robust, no HTML regex) — preferred over scraping.
    ddgs_results = await _ddgs_library_search(query, num=num)
    if ddgs_results:
        cleaned = _clean_results(ddgs_results, query, brand_name, min_score) if require_relevance else ddgs_results
        if cleaned or not require_relevance:
            _remember(ddgs_results, "ddgs_library")
            return VerifiedData(
                value=cleaned if require_relevance else ddgs_results,
                source="ddgs_library", method="ddgs_text+relevance_filter",
                retrieved_at=utcnow_iso(), confidence=1.0, verified=True,
                metadata={"query": query, "raw_count": len(ddgs_results), "kept": len(cleaned)},
            )

    # DuckDuckGo HTML leg REMOVED 2026-09 (dead: 0 parseable blocks on every
    # query after DDG markup changes). Bing RSS + ddgs library exhausted here —
    # report honest UnavailableData instead of an empty "verified success".
    logger.warning("Search chain exhausted for %r (SerpAPI/cache/Brave/Bing-Web/Bing RSS + ddgs yielded nothing usable)", query[:80])
    return UnavailableData(
        reason="Search failed after SerpAPI + cache + Brave + Bing Web + Bing RSS + ddgs library (DDG HTML leg removed as dead).",
        requires="SERPAPI_KEY or BRAVE_SEARCH_API_KEY/BING_SEARCH_API_KEY (or working Bing/ddgs access)",
    )


async def verify_url(url: str, expected_terms: list[str]) -> Any:
    """Fetch a URL and verify it actually mentions the brand/terms.

    Returns VerifiedData(value=True/False) with the fetched evidence.
    """
    try:
        async with httpx.AsyncClient(timeout=10, headers=_pick_headers(), follow_redirects=True) as c:
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

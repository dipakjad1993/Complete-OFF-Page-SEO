"""Free, no-API-key data sources used across the 35-module engine.

Everything here returns REAL live data from public endpoints. No keys, no
fabrication. Each helper returns a list of plain dicts (or None on failure)
and is wrapped by the caller into VerifiedData/UnavailableData.
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus, urlencode

import httpx

API_HEADERS = {
    "User-Agent": "CompleteOffPageSEO/2.0 (contact@completeseo.com)",
    "Accept": "application/json",
}


def _strip(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    import html as html_lib
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


async def github_search(query: str, limit: int = 8) -> list[dict] | None:
    """Search GitHub repositories/code for the brand (rate-limited but free)."""
    try:
        async with httpx.AsyncClient(timeout=10, headers=API_HEADERS, follow_redirects=True) as c:
            r = await c.get(f"https://api.github.com/search/repositories?q={quote_plus(query)}&sort=stars&per_page={limit}")
            if r.status_code != 200:
                return None
            data = r.json()
        out = []
        for it in (data.get("items") or [])[:limit]:
            out.append({
                "url": it.get("html_url", ""),
                "title": f"{it.get('full_name', '')} — {it.get('description') or ''}"[:300],
                "snippet": (it.get("description") or "")[:600],
                "domain": "github.com",
                "stars": it.get("stargazers_count"),
                "source": "github_api",
            })
        return out
    except Exception:  # noqa: BLE001
        return None


async def stackexchange_search(query: str, limit: int = 6) -> list[dict] | None:
    """Search Stack Overflow for the brand (free API, no key for basic usage)."""
    try:
        params = urlencode({"q": query, "site": "stackoverflow", "pagesize": limit, "sort": "relevance"})
        async with httpx.AsyncClient(timeout=10, headers=API_HEADERS, follow_redirects=True) as c:
            r = await c.get(f"https://api.stackexchange.com/2.3/search/advanced?{params}")
            if r.status_code != 200:
                return None
            data = r.json()
        out = []
        for it in (data.get("items") or [])[:limit]:
            out.append({
                "url": it.get("link", ""),
                "title": _strip(it.get("title", ""))[:300],
                "snippet": _strip(it.get("title", ""))[:300],
                "domain": "stackoverflow.com",
                "score": it.get("score"),
                "source": "stackexchange_api",
            })
        return out
    except Exception:  # noqa: BLE001
        return None


async def hn_search(query: str, limit: int = 8) -> list[dict] | None:
    """Search Hacker News via Algolia (free, no key)."""
    try:
        params = urlencode({"query": query, "tags": "story", "hitsPerPage": limit})
        async with httpx.AsyncClient(timeout=10, headers=API_HEADERS, follow_redirects=True) as c:
            r = await c.get(f"https://hn.algolia.com/api/v1/search?{params}")
            if r.status_code != 200:
                return None
            data = r.json()
        out = []
        for it in (data.get("hits") or [])[:limit]:
            url = it.get("url") or f"https://news.ycombinator.com/item?id={it.get('objectID', '')}"
            out.append({
                "url": url,
                "title": _strip(it.get("title", ""))[:300],
                "snippet": f"{it.get('points') or 0} points · {it.get('num_comments') or 0} comments",
                "domain": "news.ycombinator.com",
                "source": "hn_algolia",
            })
        return out
    except Exception:  # noqa: BLE001
        return None


async def itunes_podcast_search(query: str, limit: int = 8) -> list[dict] | None:
    """Find real podcasts via the public iTunes Search API (free, no key)."""
    try:
        params = urlencode({"term": query, "media": "podcast", "limit": limit})
        async with httpx.AsyncClient(timeout=10, headers=API_HEADERS, follow_redirects=True) as c:
            r = await c.get(f"https://itunes.apple.com/search?{params}")
            if r.status_code != 200:
                return None
            data = r.json()
        out = []
        for it in (data.get("results") or [])[:limit]:
            out.append({
                "url": it.get("feedUrl") or it.get("collectionViewUrl") or "",
                "title": f"{it.get('collectionName') or ''} — {it.get('artistName') or ''}"[:300],
                "snippet": _strip(it.get("primaryGenreName") or "")[:200],
                "domain": "podcasts.apple.com",
                "source": "itunes_search_api",
            })
        return out
    except Exception:  # noqa: BLE001
        return None


async def rdap_domain_lookup(domain: str) -> dict | None:
    """Look up domain registration data via public RDAP (free, no key)."""
    try:
        async with httpx.AsyncClient(timeout=10, headers=API_HEADERS, follow_redirects=True) as c:
            r = await c.get(f"https://rdap.org/domain/{domain}")
            if r.status_code != 200:
                return None
            data = r.json()
        events = {e.get("eventAction"): e.get("eventDate") for e in (data.get("events") or []) if e.get("eventAction")}
        registrar = None
        for ent in (data.get("entities") or []):
            vcard = (ent.get("vcardArray") or [[], []])[1]
            for prop in vcard:
                if isinstance(prop, list) and prop and prop[0] == "fn" and len(prop) > 3:
                    registrar = prop[3]
                    break
            if registrar:
                break
        return {
            "domain": domain,
            "registrar": registrar,
            "created": events.get("registration"),
            "last_changed": events.get("last changed"),
            "expiration": events.get("expiration"),
            "source": "rdap",
        }
    except Exception:  # noqa: BLE001
        return None


async def openalex_search(query: str, limit: int = 6) -> list[dict] | None:
    """Search scholarly works via OpenAlex (free, no key)."""
    try:
        params = urlencode({"search": query, "per-page": limit, "select": "title,doi,publication_date"})
        async with httpx.AsyncClient(timeout=10, headers=API_HEADERS, follow_redirects=True) as c:
            r = await c.get(f"https://api.openalex.org/works?{params}")
            if r.status_code != 200:
                return None
            data = r.json()
        out = []
        for it in (data.get("results") or [])[:limit]:
            out.append({
                "url": it.get("doi") or "",
                "title": _strip(it.get("title") or "")[:300],
                "snippet": f"Published {it.get('publication_date') or 'unknown date'}",
                "domain": "openalex.org",
                "source": "openalex_api",
            })
        return out
    except Exception:  # noqa: BLE001
        return None


async def free_sources_for(query: str, limit: int = 6) -> list[dict]:
    """Run all free specialized sources for a query and merge unique real results."""
    github, so, hn = await asyncio_gather_safe([
        github_search(query, limit),
        stackexchange_search(query, limit),
        hn_search(query, limit),
    ])
    merged: list[dict] = []
    seen: set[str] = set()
    for group in (github or [], so or [], hn or []):
        for item in group:
            if item.get("url") and item["url"] not in seen:
                seen.add(item["url"])
                merged.append(item)
    return merged[:limit * 2]


async def asyncio_gather_safe(coros):
    import asyncio
    return await asyncio.gather(*coros)
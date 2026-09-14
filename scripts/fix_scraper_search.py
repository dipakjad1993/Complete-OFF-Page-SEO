import pathlib
p = pathlib.Path("backend/api/website_scraper.py")
lines = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
new_fn = '''async def search_web(query, client, max_results=8):
    """Delegate to the central provider chain (SerpAPI -> cache -> Brave ->
    Bing Web -> Bing RSS -> ddgs) with provider attribution. The old
    Google-HTML / DDG-HTML / DDG-Lite scraping legs were removed in v2026.3:
    they broke on markup changes and caused log spam. Returns the legacy
    [{title, body, href, domain}] shape so callers are unchanged.
    """
    try:
        from backend.services.search import search_web as _central
        from backend.services.verification import is_verified
        res = await _central(query, brand_name="", num=max_results, require_relevance=False)
        if is_verified(res):
            out = []
            for r in (res.value or [])[:max_results]:
                url = r.get("url") or r.get("link") or ""
                if not url.startswith("http"):
                    continue
                out.append({"title": (r.get("title") or "")[:300],
                            "body": (r.get("snippet") or r.get("body") or r.get("description") or "")[:600],
                            "href": url, "domain": r.get("domain") or extract_domain(url)})
            if out:
                return out[:max_results]
    except Exception as e:  # noqa: BLE001
        _log_swallow("search.central", e, query)
    # Last-resort: Bing RSS direct (free, no key) so intake never hard-fails.
    try:
        from urllib.parse import quote_plus
        import httpx as _hx
        async with _hx.AsyncClient(timeout=10, follow_redirects=True, verify=False) as _c:
            resp = await _c.get(
                f"https://www.bing.com/search?q={quote_plus(query)}&format=rss&count={max_results}",
                headers=SEARCH_HEADERS)
            if resp.status_code == 200 and resp.text.strip().startswith("<?xml"):
                from bs4 import BeautifulSoup as _BS
                soup = _BS(resp.text, "xml")
                out = []
                for item in soup.find_all("item")[:max_results]:
                    title = item.title.get_text(strip=True) if item.title else ""
                    link = item.link.get_text(strip=True) if item.link else ""
                    desc = item.find("description").get_text(" ", strip=True) if item.find("description") else ""
                    if title and link.startswith("http"):
                        out.append({"title": title[:300], "body": desc[:600],
                                    "href": link, "domain": extract_domain(link)})
                return out[:max_results]
    except Exception as e:  # noqa: BLE001
        _log_swallow("search.bing_rss_fallback", e, query)
    return []


'''
assert lines[78].startswith("async def search_web"), repr(lines[78])
assert lines[210].strip().startswith("return unique"), repr(lines[210])
lines[78:211] = [new_fn]
p.write_text("".join(lines), encoding="utf-8")
print("replaced; new line count:", len(lines))

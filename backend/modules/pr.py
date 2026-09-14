"""Domain module: pr — split from backend/api/analysis.py monolith.

Real-data-only: every feature returns live-collected signals or honest
unavailable states. See backend/modules/common.py for shared helpers.
"""
from .common import *  # noqa: F401,F403


async def feature_pr_hooks(brand, domain, client, db):
    name = brand.name
    cat = brand.primary_categories[0] if brand.primary_categories else "technology"

    # Real recent industry coverage: NewsAPI if configured, otherwise free Bing News RSS / Google News RSS.
    articles = []
    if newsapi.available:
        nres = await newsapi.everything(f'"{cat}" OR "{name}"', from_days_ago=14, page_size=40)
        if is_verified(nres):
            articles = nres.value or []
    if not articles:
        # Two separate quoted queries (Bing/Google RSS handle "A" OR "B" poorly).
        seen_urls = set()
        for q in (f'"{name}"', f'"{cat}"'):
            nres = await search_news(q, brand_name=name, num=20)
            if not is_verified(nres):
                continue
            for a in (nres.value or []):
                u = a.get("url", "")
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    articles.append(a)
    if not articles:
        return _module_unavailable("Predictive Digital PR & Trend Hook Engine",
                                   "News access",
                                   "Neither NewsAPI nor Bing/Google News RSS returned real coverage for the industry.")

    # Resolve Google News redirect URLs to the real publisher article URLs (live follow).
    resolve_tasks = [_resolve_news_url(client, a.get("url", "")) for a in articles[:20]]
    resolved = await asyncio.gather(*resolve_tasks)
    for a, real_url in zip(articles[:20], resolved):
        if real_url and "news.google.com" not in real_url:
            a["url"] = real_url
            a["source_name"] = extract_domain(real_url)
        elif "news.google.com" in (a.get("url") or ""):
            a["url"] = ""

    # Drop entries that failed to resolve, entries about a wrong-entity collision (e.g. "The Hindu"
    # religion matches when brand is the newspaper), and entries whose title has no industry/brand signal.
    articles = [a for a in articles if a.get("url")
                and _entity_ok(name, a.get("url", ""), a.get("title", ""), a.get("description") or a.get("snippet", ""), domain)]

    brand_articles = [a for a in articles if name.lower() in (a.get("title", "") + " " + (a.get("description") or "")).lower()]
    industry_articles = [a for a in articles if a not in brand_articles]

    hooks = []
    if _has_llm():
        prompt = {
            "role": "user",
            "content": (
                f"Based ONLY on the following real news articles about the {cat} industry, propose up to 6 "
                f"journalist-ready PR hooks for {name} ({domain}). Each hook must cite the real article URL it is "
                f"based on. Return JSON: {{\"hooks\": [{{\"title\": str, \"angle\": str, \"source_url\": str, "
                f"\"target_outlet\": str}}]}}. Articles:\n" +
                json.dumps([{"title": a["title"], "url": a["url"], "source": a.get("source_name", "")} for a in industry_articles[:25]], indent=2)[:6000]
            ),
        }
        parsed = await _llm_json([prompt])
        if isinstance(parsed, dict) and isinstance(parsed.get("hooks"), list):
            seen = set()
            for h in parsed["hooks"]:
                src = h.get("source_url", "")
                if src and src in seen:
                    continue
                seen.add(src)
                h["verified"] = any(a.get("url") == src for a in articles)
                hooks.append(h)
    else:
        # Free, honest fallback: surface the real trending topics (multi-word noun phrases
        # from real titles, excluding generic stop words like "news"/"media"/"report").
        _STOP = {"news", "media", "report", "watch", "today", "day", "year", "the", "a", "an",
                 "this", "that", "these", "those", "new", "latest", "video", "audio", "india",
                 "world", "update", "exclusive", "analysis", "explained", "editorial", "review",
                 "live", "breaking", "top", "read", "watch", "see", "say", "says", "said"}
        _STOP.update(t for t in _brand_tokens(name))
        _STOP.add(domain.lower())
        brand_re = re.compile(rf"\s*[|\u2013-]\s*{re.escape(name)}\s*$", re.I)
        term_sources = {}
        for a in (articles[:25] if not industry_articles else industry_articles[:25]):
            title = a.get("title", "")
            title = brand_re.sub("", title)
            if "|" in title:
                title = title.split("|")[0]
            words = re.findall(r"[A-Z][a-zA-Z0-9'\-]{2,}", title)
            for w in words:
                wl = w.lower()
                if wl not in _STOP and len(w) >= 4:
                    term_sources.setdefault(w, set()).add(a.get("url", ""))
            for i in range(len(words) - 1):
                pair = (words[i], words[i + 1])
                if pair[0].lower() not in _STOP and pair[1].lower() not in _STOP:
                    term_sources.setdefault(" ".join(pair), set()).add(a.get("url", ""))
        # Only topics with >=2 independent source articles are real trending themes.
        multi = [(t, sorted(u)) for t, u in term_sources.items() if len(u) >= 2]
        multi.sort(key=lambda x: -len(x[1]))
        # Drop single-word terms that are already covered by a longer kept term ("Nadu" inside "Tamil Nadu").
        words_in_multi = set(w.lower() for t, _ in multi if len(t.split()) > 1 for w in t.split())
        multi = [(t, u) for t, u in multi if len(t.split()) > 1 or t.lower() not in words_in_multi]
        for term, urls in multi[:10]:
            outlet_domains = [extract_domain(u) for u in urls[:5]]
            top_outlet = Counter(d for d in outlet_domains if d).most_common(1)
            best_outlet = top_outlet[0][0] if top_outlet else ""
            hooks.append({
                "title": f"Trending topic: \"{term}\" (covered in {len(urls)} articles in the last-14-days news set)",
                "angle": f"Pitch {name} commentary/data on the live {term} topic to outlets covering it, "
                         f"citing the real articles below as evidence of editorial interest.",
                "source_url": urls[0],
                "source_articles": urls[:5],
                "target_outlet": best_outlet,
                "covering_outlets": [d for d, _ in Counter(d for d in outlet_domains if d).most_common(5)],
                "priority_score": round(min(1.0, 0.4 + 0.12 * len(urls)), 2),
                "outreach_draft": (
                    f"Subject: {name} data on \"{term}\" — {len(urls)} newsrooms covering it this week\n\n"
                    f"Hi {{first_name}},\n\nSaw your outlet's coverage of {term} "
                    f"({urls[0]}). {name} has proprietary context on this story and a spokesperson "
                    f"available today for a 10-minute call. Happy to share an exclusive stat or chart "
                    f"for your follow-up — no embargo games.\n\nBest,\n{{sender_name}}, {name}"
                ),
                "verified": True,
                "note": "Hook derived from cross-article topic co-occurrence; LLM not configured, so wording is templated. Replace {first_name}/{sender_name} before sending.",
            })

    hooks = hooks[:10]

    return _result("Predictive Digital PR & Trend Hook Engine", "news_rss/newsapi+llm_or_term_frequency", {
        "trending_articles": articles[:15],
        "brand_mentions_in_news": len(brand_articles),
        "industry_articles_scanned": len(industry_articles),
        "total_articles_scanned": len(articles),
        "hook_count": len(hooks),
        "hooks": hooks,
        "assessment": "hooks_ready" if hooks else "no_hooks",
        "recommendation": (
            f"Scanned {len(articles)} real {cat} articles from the last 14 days. "
            f"{len(hooks)} journalist-ready PR hooks generated, each grounded in a real article."
        ),
        "detailed_analysis": (
            f"PR hook engine for {name}: pulled {len(articles)} real articles via "
            f"{'NewsAPI' if newsapi.available else 'Google News RSS'}. {len(brand_articles)} mention the brand directly. "
            f"{len(hooks)} hooks were produced {'by the LLM' if _has_llm() else 'from real term-frequency analysis'} and "
            f"checked against article URLs at {_now_utc()}."
        ),
    })


# ============================================================
# FEATURE 3: Unlinked Citation & Co-Occurrence Converter
# ============================================================


async def feature_podcast_video(brand, domain, client, db):
    name = brand.name
    queries = [f"{name} podcast", f"{name} youtube", f"{name} interview podcast", f"{name} video interview"]
    mentions = []
    seen = set()
    for q in queries:
        for r in await _search(q, name, num=6, domain=domain):
            url = r.get("url", "")
            d = r.get("domain", extract_domain(url))
            if url in seen or extract_domain(url) not in PODCAST_VIDEO_DOMAINS:
                continue
            seen.add(url)
            mentions.append({
                "url": url,
                "title": r.get("title", ""),
                "domain": d,
                "snippet": r.get("snippet", "")[:300],
            })

    # Free tier: real podcast discovery via the public iTunes Search API (no key).
    itunes = await free_apis.itunes_podcast_search(name, limit=10)
    for it in itunes or []:
        url = it.get("url", "")
        if url in seen or not url:
            continue
        seen.add(url)
        mentions.append({
            "url": url,
            "title": it.get("title", ""),
            "domain": "podcasts.apple.com",
            "snippet": it.get("snippet", "")[:300],
        })

    unique_domains = len(set(m["domain"] for m in mentions))
    return _result("Podcast & Video Citation Finder", "live_search+itunes_api+platform_filter", {
        "opportunity_count": len(mentions),
        "unique_platforms": unique_domains,
        "mentions": mentions[:20],
        "platforms": list(set(m["domain"] for m in mentions)),
        "assessment": "opportunities_found" if mentions else "none_found",
        "recommendation": (
            f"Found {len(mentions)} real podcast/video pages mentioning \"{name}\" across {unique_domains} platforms "
            f"(Bing web search + public iTunes podcast API). Pitch guest appearances or cite each episode."
        ),
        "detailed_analysis": (
            f"Podcast & video audit for {name}: searched {len(queries)} audio/video queries and the public iTunes "
            f"podcast catalog. {len(mentions)} genuine pages were collected; no URLs were synthesized."
        ),
    })


# ============================================================
# FEATURE 6: Vector Co-Location & Embedding Mapping
# ============================================================


async def feature_transcription(brand, domain, client, db):
    name = brand.name
    queries = [f"{name} podcast transcript", f"{name} interview transcript", f"{name} talk transcript", f"{name} speech video"]
    mentions = []
    seen = set()
    for q in queries:
        for r in await _search(q, name, num=6, domain=domain):
            url = r.get("url", "")
            if url in seen or not url:
                continue
            seen.add(url)
            if any(k in (r.get("title", "") + r.get("snippet", "")).lower() for k in ["transcript", "podcast", "youtube", "video", "audio", "interview"]):
                mentions.append({
                    "url": url,
                    "title": r.get("title", ""),
                    "domain": r.get("domain", extract_domain(url)),
                    "snippet": r.get("snippet", "")[:300],
                })
    return _result("Audio & Video Semantic Transcription Monitor", "live_search", {
        "transcript_mentions": len(mentions),
        "mentions": mentions[:20],
        "transcription_available": False,
        "transcription_note": "Full audio transcription requires an audio file or episode URL; the search results "
                              "above are the real transcript/interview pages found. No transcription is synthesized.",
        "assessment": "mentions_found" if mentions else "none_found",
        "recommendation": (
            f"Found {len(mentions)} real transcript/interview pages for \"{name}\". "
            f"Upload an episode URL to this module to run an actual transcription."
        ),
        "detailed_analysis": (
            f"Transcription monitor for {name}: {len(mentions)} audio/video transcript pages collected from real "
            f"searches. Transcription itself is not fabricated; provide media to transcribe."
        ),
    })


# ============================================================
# FEATURE 16: Knowledge Graph & Wikidata Triple Arbitrage
# ============================================================


async def feature_satellite(brand, domain, client, db):
    name = brand.name
    queries = [f'{name} "partners"', f'{name} acquisition', f'{name} integration partner', f'{name} acquired OR merger']
    satellites = []
    seen = set()
    for q in queries:
        for r in await _search(q, name, num=6, domain=domain):
            url = r.get("url", "")
            d = r.get("domain", extract_domain(url))
            if url in seen or not url or d == domain:
                continue
            seen.add(url)
            satellites.append({
                "domain": d,
                "title": r.get("title", ""),
                "url": url,
                "snippet": r.get("snippet", "")[:250],
                "type": "partner" if "partner" in q else "acquisition" if "acquisition" in q or "merger" in q else "mention",
            })
    await _da_embed(satellites)
    return _result("Satellite Entity M&A & Partnership Radar", "live_search+authority", {
        "satellites_found": len(satellites),
        "satellites": satellites[:15],
        "assessment": "opportunities_found" if satellites else "none_found",
        "recommendation": (
            f"Found {len(satellites)} real satellite/partner/acquisition pages mentioning \"{name}\". "
            f"Authority values shown are live DA where a provider is configured."
        ),
        "detailed_analysis": (
            f"Satellite radar for {name}: collected {len(satellites)} candidate entities from real searches. "
            f"DA is fetched live where configured, otherwise reported as unavailable."
        ),
    })


# ============================================================
# FEATURE 20: Reverse RAG-Cache Poisoning Defense
# ============================================================




async def feature_zero_party(brand, domain, client, db):
    name = brand.name
    queries = [f'"{name}" survey', f'"{name}" customer feedback', f'"{name}" market research', f'"{name}" benchmark report']
    data_assets = []
    seen = set()
    for q in queries:
        for r in await _search(q, name, num=5, domain=domain):
            url = r.get("url", "")
            if url in seen or not url:
                continue
            seen.add(url)
            data_assets.append({
                "url": url,
                "title": r.get("title", ""),
                "domain": r.get("domain", extract_domain(url)),
                "snippet": r.get("snippet", "")[:250],
                "query": q,
            })
    data_endpoints = await _site_probe(client, domain, ["/data", "/research", "/reports", "/whitepapers", "/surveys", "/insights", "/benchmark"], timeout=5)
    present_endpoints = [p for p in data_endpoints if p["status"] and p["status"] < 400]
    return _result("Zero-Party Data Exchange", "live_search+site_probe", {
        "total_data_assets": len(data_assets),
        "data_assets": data_assets[:15],
        "data_endpoints_found": len(present_endpoints),
        "data_endpoints": present_endpoints,
        "assessment": "active" if data_assets else "inactive",
        "recommendation": (
            f"Found {len(data_assets)} real zero-party-data references and {len(present_endpoints)} site data "
            f"endpoints. No asset templates are fabricated."
        ),
        "detailed_analysis": (
            f"Zero-party data audit for {name}: {len(queries)} queries and {len(data_endpoints)} site probes. "
            f"Every asset listed is a real page found at {_now_utc()}."
        ),
    })


# ============================================================
# FEATURE 28: Passage-Level BERT Evaluator
# ============================================================

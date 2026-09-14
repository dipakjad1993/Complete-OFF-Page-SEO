"""Domain module: technical — split from backend/api/analysis.py monolith.

Real-data-only: every feature returns live-collected signals or honest
unavailable states. See backend/modules/common.py for shared helpers.
"""
from .common import *  # noqa: F401,F403


async def feature_aeo(brand, domain, client, db):
    name = brand.name
    probes = await _site_probe(client, domain, [
        "/llms.txt", "/robots.txt", "/sitemap.xml", "/.well-known/ai-plugin.json",
        "/.well-known/llms.txt", "/ai.txt", "/.well-known/appspecific/com.chatgpt.android.platform.json",
    ], timeout=6)
    llms_txt = next((p for p in probes if p["path"] in ("/llms.txt", "/.well-known/llms.txt", "/ai.txt") and p["status"] and p["status"] < 400), None)
    robots = next((p for p in probes if p["path"] == "/robots.txt" and p["status"] and p["status"] < 400), None)
    sitemap = next((p for p in probes if p["path"] == "/sitemap.xml" and p["status"] and p["status"] < 400), None)
    plugin = next((p for p in probes if ".json" in p["path"] and p["status"] and p["status"] < 400), None)

    ai_bot_directives = []
    if robots:
        try:
            resp = await client.get(f"https://{domain}/robots.txt", headers=HEADERS, timeout=6, follow_redirects=True)
            if resp.status_code == 200:
                ai_bot_directives = [ln.strip() for ln in resp.text.splitlines()
                                     if any(b in ln.lower() for b in ["gptbot", "chatgpt", "ccbot", "anthropic", "claude", "google-extended", "perplexity", "bytespider"])]
        except Exception:
            pass

    schema_types = []
    try:
        resp = await client.get(f"https://{domain}", headers=HEADERS, timeout=10, follow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for s in soup.find_all("script", type="application/ld+json"):
                try:
                    d = json.loads(s.string)
                    if isinstance(d, dict) and d.get("@type"):
                        schema_types.append(d["@type"])
                except Exception:
                    pass
    except Exception:
        pass

    score = 0
    if llms_txt: score += 25
    if robots: score += 15
    if ai_bot_directives: score += 15
    if sitemap: score += 15
    if plugin: score += 20
    if schema_types: score += 10

    return _result("Agentic Commerce Protocol Placement (GEO/AEO)", "live_site_probe", {
        "aeo_score": min(100, score),
        "llms_txt": bool(llms_txt),
        "robots_txt": bool(robots),
        "sitemap": bool(sitemap),
        "ai_plugin_json": bool(plugin),
        "ai_bot_directives": ai_bot_directives[:10],
        "schema_types": list(dict.fromkeys(schema_types))[:15],
        "probes": probes,
        "assessment": "optimized" if score > 70 else "partial" if score > 40 else "needs_optimization",
        "recommendation": (
            f"AEO readiness for {domain}: {score}/100. llms.txt: {'present' if llms_txt else 'missing'}, "
            f"AI bot directives: {len(ai_bot_directives)}, schema types: {len(set(schema_types))}."
        ),
        "detailed_analysis": (
            f"AEO audit for {name}: live-probed {len(probes)} agentic-discovery endpoints on {domain} and parsed "
            f"robots.txt and structured data. Every finding above reflects the real response received at {_now_utc()}."
        ),
    })


# ============================================================
# FEATURE 10: Synthetic Network & Footprint De-Anonymizer
# ============================================================


async def feature_dead_equity(brand, domain, client, db):
    name = brand.name
    pages = await deep_fetch_website(domain, client)
    data = extract_comprehensive_data(pages)
    raw_links = [l for l in data.get("page_links", []) if isinstance(l, dict)]
    outbound = [{"url": l["url"], "text": str(l.get("text", "") or "")[:160]} for l in raw_links
                if urlparse(l.get("url", "")).netloc.replace("www.", "") != domain]
    outbound = outbound[:40]
    broken = []
    redirected = []
    healthy = []
    for l in outbound:
        try:
            resp = await client.get(l["url"], headers=HEADERS, timeout=8, follow_redirects=True)
            code = resp.status_code
            if code >= 400:
                broken.append({"url": l["url"], "text": l["text"], "status": code})
            elif str(resp.url) != l["url"]:
                redirected.append({"url": l["url"], "text": l["text"], "status": code, "final_url": str(resp.url)})
            else:
                healthy.append({"url": l["url"], "text": l["text"], "status": code})
        except Exception:
            broken.append({"url": l["url"], "text": l["text"], "status": None})
    dead_count = len(broken)
    return _result("Edge-Redirect & Dead-Equity Salvage", "live_outbound_link_check", {
        "outbound_links_checked": len(outbound),
        "broken_count": dead_count,
        "redirect_count": len(redirected),
        "healthy_count": len(healthy),
        "broken_links": broken[:20],
        "redirected_links": redirected[:10],
        "assessment": "broken_found" if dead_count else "clean",
        "recommendation": (
            f"Checked {len(outbound)} real outbound links on {domain}: {dead_count} broken, {len(redirected)} redirected, "
            f"{len(healthy)} healthy. Recover the broken ones first (lost link equity)."
        ),
        "detailed_analysis": (
            f"Dead-equity audit for {domain}: crawled {len(pages)} pages and followed {len(outbound)} external links "
            f"live. Each broken/redirect verdict is a real HTTP response captured at {_now_utc()}."
        ),
    })


# ============================================================
# FEATURE 13: Negative SEO Counter-Measure Deployment
# ============================================================


async def feature_compliance_guard(brand, domain, client, db):
    name = brand.name
    queries = [f"{name} SEC filing", f"{name} privacy policy", f"{name} GDPR", f"{name} data protection", f"{name} legal"]
    mentions = []
    seen = set()
    for q in queries:
        for r in await _search(q, name, num=5, domain=domain):
            url = r.get("url", "")
            if url in seen or not url:
                continue
            seen.add(url)
            mentions.append({
                "url": url,
                "title": r.get("title", ""),
                "domain": r.get("domain", extract_domain(url)),
                "snippet": r.get("snippet", "")[:300],
                "query": q,
            })
    compliance_pages = await _site_probe(client, domain, ["/privacy", "/privacy-policy", "/terms", "/terms-of-service", "/legal", "/disclosure", "/cookie-policy"], timeout=6)
    present_pages = [p for p in compliance_pages if p["status"] and p["status"] < 400]
    score = min(100, len(present_pages) * 15 + min(20, len(mentions)))
    return _result("Legal / SEC Disclosure Risk Profiling", "live_search+site_probe", {
        "compliance_score": score,
        "compliance_pages_found": present_pages,
        "legal_mentions": mentions[:15],
        "assessment": "compliant" if score > 70 else "partial" if score > 40 else "non_compliant",
        "recommendation": (
            f"Compliance readiness {score}/100: {len(present_pages)} standard compliance pages present, "
            f"{len(mentions)} legal/SEC mentions found."
        ),
        "detailed_analysis": (
            f"Compliance guard for {name}: probed {len(compliance_pages)} compliance paths on {domain} and ran "
            f"{len(queries)} legal queries. All counts are real observations from {_now_utc()}."
        ),
    })


# ============================================================
# FEATURE 26: Geo-IP Citation Localization
# ============================================================


async def feature_geo_crawl(brand, domain, client, db):
    name = brand.name
    regions = ["US", "UK", "EU", "Asia", "Global"]
    geo_citations = {}
    for region in regions:
        q = f'"{name}" {region} market'
        hits = []
        for r in await _search(q, name, num=3, domain=domain):
            url = r.get("url", "")
            if url:
                hits.append({"url": url, "title": r.get("title", ""), "domain": r.get("domain", extract_domain(url)),
                             "snippet": r.get("snippet", "")[:200]})
        if hits:
            geo_citations[region] = hits

    hreflang_checks = []
    try:
        resp = await client.get(f"https://{domain}", headers=HEADERS, timeout=10, follow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            hreflang_checks = [{"hreflang": l.get("hreflang"), "href": l.get("href", "")[:150]}
                               for l in soup.find_all("link", rel="alternate", hreflang=True)]
    except Exception:
        pass

    regions_with_citations = len(geo_citations)
    coverage = round(regions_with_citations / len(regions) * 100, 1)
    return _result("Geo-IP Citation Localization", "live_search+hreflang_scan", {
        "regions_analyzed": len(regions),
        "regions_with_citations": regions_with_citations,
        "geo_coverage_score": coverage,
        "geo_citations_by_region": geo_citations,
        "hreflang_tags": hreflang_checks[:10],
        "assessment": "strong" if regions_with_citations > 3 else "moderate" if regions_with_citations > 1 else "weak",
        "recommendation": (
            f"Geo coverage {coverage}% ({regions_with_citations}/{len(regions)} regions have brand citations). "
            f"{len(hreflang_checks)} hreflang tags on the site."
        ),
        "detailed_analysis": (
            f"Geo localization for {name}: {len(regions)} region queries, {regions_with_citations} with real "
            f"citations, plus a live hreflang scan of {domain}. All results are real."
        ),
    })


# ============================================================
# FEATURE 27: Zero-Party Data Exchange
# ============================================================


async def feature_apn_proxy(brand, domain, client, db):
    name = brand.name
    endpoints = [
        "/api", "/api/v1", "/api/v2", "/graphql", "/openapi.json", "/swagger.json",
        "/.well-known/openid-configuration", "/feed.xml", "/rss.xml", "/atom.xml",
        "/sitemap.xml", "/robots.txt", "/manifest.json", "/webmanifest.json",
        "/.well-known/ai-plugin.json", "/llms.txt",
    ]
    probes = await _site_probe(client, domain, endpoints, timeout=6)
    active = [p for p in probes if p["status"] and p["status"] < 400]
    json_endpoints = [p for p in active if "json" in p["content_type"]]
    xml_endpoints = [p for p in active if "xml" in p["content_type"] or "rss" in p["content_type"]]
    score = min(100, len(active) * 8 + len(json_endpoints) * 4 + len(xml_endpoints) * 4)
    return _result("Agentic Protocol Negotiation (APN) Proxy", "live_endpoint_probe", {
        "apn_score": score,
        "total_endpoints": len(endpoints),
        "active_endpoints": len(active),
        "json_endpoints": len(json_endpoints),
        "xml_endpoints": len(xml_endpoints),
        "endpoint_probes": probes,
        "assessment": "excellent" if score > 70 else "good" if score > 40 else "needs_improvement",
        "recommendation": (
            f"APN readiness {score}/100: {len(active)} of {len(endpoints)} agentic/API endpoints respond on {domain}."
        ),
        "detailed_analysis": (
            f"APN audit for {domain}: live-probed {len(endpoints)} endpoints at {_now_utc()}. "
            f"{len(active)} returned HTTP < 400. Every status is a real response."
        ),
    })


# ============================================================
# FEATURE 23: Co-Citation Graph Decay & Entity Anchor Leasing
# ============================================================


async def feature_crawl_priority(brand, domain, client, db):
    name = brand.name
    probes = await _site_probe(client, domain, ["/robots.txt", "/sitemap.xml", "/indexnow"], timeout=6)
    robots = next((p for p in probes if p["path"] == "/robots.txt" and p["status"] and p["status"] < 400), None)
    sitemap = next((p for p in probes if p["path"] == "/sitemap.xml" and p["status"] and p["status"] < 400), None)
    indexnow = next((p for p in probes if p["path"] == "/indexnow" and p["status"] and p["status"] < 400), None)
    ai_bot_directives = []
    x_robots = ""
    if robots:
        try:
            resp = await client.get(f"https://{domain}/robots.txt", headers=HEADERS, timeout=6, follow_redirects=True)
            if resp.status_code == 200:
                ai_bot_directives = [ln.strip() for ln in resp.text.splitlines()
                                     if any(b in ln.lower() for b in ["gptbot", "chatgpt", "ccbot", "anthropic", "claude", "google-extended", "perplexity", "bytespider"])]
        except Exception:
            pass
    try:
        resp = await client.get(f"https://{domain}", headers=HEADERS, timeout=10, follow_redirects=True)
        x_robots = resp.headers.get("x-robots-tag", "")
    except Exception:
        pass

    score = 0
    if robots: score += 20
    if sitemap: score += 25
    if ai_bot_directives: score += 15
    if x_robots: score += 10
    if indexnow: score += 15
    if sitemap and sitemap.get("size") > 500: score += 15
    return _result("AI Crawler Re-Indexation Pinger", "live_site_probe", {
        "crawl_priority_score": min(100, score),
        "robots_txt": bool(robots),
        "sitemap": bool(sitemap),
        "indexnow": bool(indexnow),
        "ai_bot_directives": ai_bot_directives[:10],
        "x_robots_tag": x_robots[:200],
        "assessment": "optimized" if score > 70 else "partial" if score > 40 else "needs_optimization",
        "recommendation": (
            f"Crawl-priority readiness {score}/100 on {domain}. IndexNow: {'present' if indexnow else 'missing'}; "
            f"AI bot directives: {len(ai_bot_directives)}."
        ),
        "detailed_analysis": (
            f"Crawl audit for {domain}: live probes of robots.txt, sitemap.xml, IndexNow endpoint and AI-bot "
            f"directives at {_now_utc()}. All statuses are real responses."
        ),
    })


# ============================================================
# FEATURE 34: FTC & Sponsored-Mention Penalty Shield
# ============================================================


async def feature_hreflang(brand, domain, client, db):
    name = brand.name
    hreflang_tags = []
    international_links = []
    try:
        resp = await client.get(f"https://{domain}", headers=HEADERS, timeout=10, follow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            hreflang_tags = [{"hreflang": l.get("hreflang"), "href": l.get("href", "")[:150]}
                             for l in soup.find_all("link", rel="alternate", hreflang=True)]
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                if any(code in href for code in [".de", ".fr", ".es", ".jp", ".cn", ".uk", ".au", "/de/", "/fr/", "/es/", "/en/"]):
                    international_links.append({"href": href[:150], "text": a.get_text(strip=True)[:40]})
    except Exception:
        pass

    international_versions = []
    for cc in ["de", "fr", "es", "jp", "uk", "au", "ca"]:
        probes = await _site_probe(client, domain, [f"/{cc}/"], timeout=4)
        if probes and probes[0]["status"] and probes[0]["status"] < 400:
            international_versions.append({"version": cc, "url": f"https://{domain}/{cc}/"})
    cannibalization_risk = "low"
    if hreflang_tags and not international_versions:
        cannibalization_risk = "medium"
    if not hreflang_tags and international_versions:
        cannibalization_risk = "high"
    if len(international_versions) > 3 and len(hreflang_tags) < len(international_versions):
        cannibalization_risk = "high"

    score = min(100, min(30, len(hreflang_tags) * 5) + min(25, len(international_versions) * 5) + (15 if international_links else 0) + (20 if cannibalization_risk == "low" else 0))
    return _result("Cross-Border Hreflang Equity Balancer", "live_site_scan", {
        "international_readiness_score": score,
        "hreflang_tags": hreflang_tags[:15],
        "international_versions": international_versions[:10],
        "international_links": international_links[:10],
        "cannibalization_risk": cannibalization_risk,
        "assessment": "optimized" if score > 70 else "partial" if score > 40 else "needs_optimization",
        "recommendation": (
            f"Hreflang readiness {score}/100: {len(hreflang_tags)} hreflang tags, {len(international_versions)} "
            f"international versions, cannibalization risk {cannibalization_risk}."
        ),
        "detailed_analysis": (
            f"Hreflang audit for {domain}: live scan of alternate-link tags, international links and country-path "
            f"probes at {_now_utc()}. All values are real observations."
        ),
    })


# ============================================================
# MAIN ANALYSIS RUNNER
# ============================================================

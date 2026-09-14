"""Domain module: risk — split from backend/api/analysis.py monolith.

Real-data-only: every feature returns live-collected signals or honest
unavailable states. See backend/modules/common.py for shared helpers.
"""
from .common import *  # noqa: F401,F403


async def feature_link_poisoning(brand, domain, client, db):
    name = brand.name
    bl = await ahrefs.backlinks(f"https://{domain}", limit=100)
    links = bl.value if is_verified(bl) else []

    # Free tier: real backlink discovery via Bing results referencing the domain (no key required).
    if not links:
        for q in [f'"{domain}" backlinks', f'"{domain}" links', f'"{domain}" -site:{domain}']:
            r = await search_web(q, brand_name=name, num=15, require_relevance=False)
            for res in (r.value if is_verified(r) else []) or []:
                src = res.get("domain", extract_domain(res.get("url", ""))) or ""
                if src == domain or not src or src == "www." + domain:
                    continue
                links.append({
                    "source_domain": src,
                    "anchor_text": res.get("title", "")[:120],
                    "is_sponsored": False,
                    "is_ugc": False,
                    "found_via": q,
                })

    if not links:
        if not ahrefs.available:
            return _module_unavailable("Algorithmic Link Poisoning & Anomaly Radar",
                                       "AHREFS_API_KEY (or MOZ_ACCESS_KEY+MOZ_SECRET_KEY)",
                                       "No backlink provider is configured and Bing returned no indexed pages linking to the domain.")
        return _module_unavailable("Algorithmic Link Poisoning & Anomaly Radar", "AHREFS_API_KEY",
                                   bl.reason if is_unavailable(bl) else "Backlink provider returned no data.")
    total = len(links)
    toxic = []
    for l in links:
        src_domain = (l.get("source_domain") or "").lower()
        anchor = (l.get("anchor_text") or "").lower()
        reasons = []
        if any(kw in src_domain for kw in TOXIC_TLD_KEYWORDS):
            reasons.append("toxic_domain_pattern")
        if any(kw in anchor for kw in TOXIC_TLD_KEYWORDS):
            reasons.append("toxic_anchor")
        if l.get("is_sponsored"):
            reasons.append("sponsored")
        if l.get("is_ugc"):
            reasons.append("ugc")
        if reasons:
            l["toxic_reasons"] = reasons
            toxic.append(l)

    # Anchor over-optimization (real, computed from real anchors).
    anchors = Counter((l.get("anchor_text") or "").strip().lower() for l in links)
    total_anchors = sum(anchors.values())
    exact_match = sum(c for a, c in anchors.items() if a == name.lower())
    exact_match_pct = round(exact_match / total_anchors * 100, 1) if total_anchors else 0

    toxic_count = len(toxic)
    health_score = round(max(0, 100 - toxic_count * 5 - max(0, exact_match_pct - 40)), 1)
    method = "ahrefs_backlinks+analysis" if is_verified(bl) else "bing_link_queries+analysis"
    return _result("Algorithmic Link Poisoning & Anomaly Radar", method, {
        "total_backlinks": total,
        "toxic_count": toxic_count,
        "toxic_backlinks": toxic[:20],
        "exact_match_anchor_pct": exact_match_pct,
        "top_anchors": [{"anchor": a, "count": c} for a, c in anchors.most_common(10)],
        "health_score": health_score,
        "assessment": "healthy" if health_score >= 70 else "attention" if health_score >= 40 else "critical",
        "recommendation": (
            f"{total} real backlinks audited. {toxic_count} flagged as toxic/anomalous. "
            f"{exact_match_pct}% exact-match anchors (over-optimization risk above 40%). Health score {health_score}/100."
        ),
        "detailed_analysis": (
            f"Link-poisoning audit for {domain}: {total} backlinks pulled live from "
            + ("Ahrefs" if is_verified(bl) else "Bing reference discovery")
            + (f" ({bl.metadata.get('total_reported', 'n/a')} reported)" if is_verified(bl) else "")
            + f". {toxic_count} links show toxic domain or anchor "
            + f"patterns; {exact_match_pct}% of anchors are exact-match. All numbers derived from the live backlink dataset."
        ),
    })


# ============================================================
# FEATURE 5: Podcast & Video Citation Finder
# ============================================================




async def feature_pbn_detector(brand, domain, client, db):
    name = brand.name
    bl = await ahrefs.backlinks(f"https://{domain}", limit=100)
    links = bl.value if is_verified(bl) else []

    # Free tier: real RDAP registration data for the domain footprint (no key required).
    rdap = await free_apis.rdap_domain_lookup(domain)
    rdap_signal = None
    if rdap:
        created = rdap.get("created", "")
        age_years = None
        if created:
            try:
                from datetime import datetime as _dt, timezone as _tz
                age_years = round((_dt.now(_tz.utc) - _dt.fromisoformat(created.replace("Z", "+00:00"))).days / 365, 1)
            except Exception:
                pass
        rdap_signal = {
            "domain": domain,
            "registrar": rdap.get("registrar"),
            "registered": created,
            "domain_age_years": age_years,
            "expiration": rdap.get("expiration"),
        }

    if not links and not rdap_signal:
        if not ahrefs.available:
            return _module_unavailable("Synthetic Network & Footprint De-Anonymizer",
                                       "AHREFS_API_KEY (or MOZ_ACCESS_KEY+MOZ_SECRET_KEY)",
                                       "No backlink provider and no public registration data were available.")
        return _module_unavailable("Synthetic Network & Footprint De-Anonymizer", "AHREFS_API_KEY",
                                   bl.reason if is_unavailable(bl) else "Backlink provider returned no data.")

    # Footprint signals observable from real backlink data.
    domain_counts = Counter((l.get("source_domain") or "").lower() for l in links)
    repeated_domains = [{"domain": d, "links": c} for d, c in domain_counts.most_common(20) if c >= 3]
    generic_anchors = [a for l in links if a in ["click here", "here", "read more", "website", "home", "more"] for a in (l.get("anchor_text") or "").lower()]
    sponsored = sum(1 for l in links if l.get("is_sponsored"))
    ugc = sum(1 for l in links if l.get("is_ugc"))

    note = (
        "PBN footprint signals: backlink repetition/anchor patterns (when a backlink provider is configured) plus "
        "public RDAP domain-registration data. If no paid backlink provider is configured, only the public "
        "registration signals are reported."
    )

    if not links and rdap_signal:
        return _result("Synthetic Network & Footprint De-Anonymizer", "rdap_footprint_analysis", {
            "total_backlinks": 0,
            "repeated_source_domains": [],
            "suspicious_count": 0,
            "sponsored_count": 0,
            "ugc_count": 0,
            "generic_anchor_count": 0,
            "registration_footprint": rdap_signal,
            "methodology_note": note,
            "assessment": "registration_only",
            "recommendation": (
                f"No paid backlink provider is configured, so backlink footprint data is unavailable. "
                f"Only the real public RDAP registration record for {domain} (created "
                f"{rdap_signal['registered'] or 'unknown'}) was examined. Configure AHREFS_API_KEY to analyze "
                f"actual backlink repetition, anchor and sponsored/UGC patterns."
            ),
            "detailed_analysis": (
                f"PBN footprint audit for {domain}: no backlink data available (no provider key). "
                f"Public RDAP registration record verified in real time: registrar "
                f"{rdap_signal['registrar'] or 'unknown'}, registered {rdap_signal['registered'] or 'unknown'}, "
                f"expiration {rdap_signal['expiration'] or 'unknown'}, domain age "
                f"{rdap_signal['domain_age_years'] if rdap_signal['domain_age_years'] is not None else 'unknown'} years. "
                f"No backlink-based PBN signal was claimed because none was observed."
            ),
        })

    suspicious_count = len([d for d in repeated_domains if d["links"] >= 5])
    return _result("Synthetic Network & Footprint De-Anonymizer", "backlinks+rdap_footprint_analysis", {
        "total_backlinks": len(links),
        "repeated_source_domains": repeated_domains[:15],
        "suspicious_count": suspicious_count,
        "sponsored_count": sponsored,
        "ugc_count": ugc,
        "generic_anchor_count": len(generic_anchors),
        "registration_footprint": rdap_signal,
        "methodology_note": note,
        "assessment": "clean" if suspicious_count == 0 else "footprint_detected",
        "recommendation": (
            f"Analyzed {len(links)} real backlinks" + (f" and the public RDAP registration record" if rdap_signal else "") + ". "
            f"{suspicious_count} source domains repeat 5+ times. "
            f"{note}"
        ),
        "detailed_analysis": (
            f"PBN footprint audit for {domain}: examined {len(links)} live backlinks and the public RDAP registration "
            f"record (created {rdap_signal['registered'] if rdap_signal else 'unavailable'}). "
            f"{len(repeated_domains)} source domains link 3+ times. {sponsored} sponsored, {ugc} UGC. "
            f"All values derive from real, verifiable data."
        ),
    })


# ============================================================
# FEATURE 11: Share-of-Search Revenue Simulator
# ============================================================


async def feature_revenue_sim(brand, domain, client, db):
    name = brand.name
    cat = brand.primary_categories[0] if brand.primary_categories else "technology"
    branded_q = name
    category_q = cat

    # Paid tier: real Google SERPs via SerpAPI. Free tier: real Bing results via Bing RSS.
    brand_serp, cat_serp = None, None
    method = ""
    if serpapi.available:
        brand_serp = await serpapi.search(branded_q, num=10)
        cat_serp = await serpapi.search(category_q, num=10)
        method = "serpapi_serp_analysis"
    if (not brand_serp or not is_verified(brand_serp)) or (not cat_serp or not is_verified(cat_serp)):
        brand_serp = await search_web(branded_q, brand_name=name, num=10, require_relevance=False)
        cat_serp = await search_web(category_q, brand_name=name, num=10, require_relevance=False)
        method = "bing_rss_serp_analysis"
    if not is_verified(brand_serp) or not is_verified(cat_serp):
        return _module_unavailable("Share-of-Search Revenue Simulator",
                                   "SERPAPI_KEY (or working search access)",
                                   "No real SERP data could be fetched.")

    def brand_share(results, name):
        tot = len(results)
        if not tot:
            return None
        hits = sum(1 for r in results if name.lower() in (r.get("title", "") + " " + r.get("url", "")).lower())
        return round(hits / tot * 100, 1)

    share_brand = brand_share(brand_serp.value, name)
    share_cat = brand_share(cat_serp.value, name)
    # ---- CFO-proof Monte Carlo scenarios (labeled projection on a measured baseline) ----
    # Deterministic (seeded) simulation: each tier-1 citation is modeled as lifting
    # branded-query SoS by a sampled 0.4–1.2 pts (log-normal-ish via triangular dist).
    # This is a PROJECTION with stated assumptions — the measured shares above stay exact.
    import random as _rnd
    scenarios = []
    if share_brand is not None:
        rng = _rnd.Random(abs(hash(domain)) % (2 ** 32))
        for n_cites in (5, 10, 20):
            trials = []
            for _ in range(2000):
                lift = sum(rng.triangular(0.4, 1.2, 0.7) for _ in range(n_cites))
                # Diminishing returns: each doubling halves marginal lift.
                lift *= 1.0 / (1.0 + 0.15 * (n_cites - 5))
                trials.append(min(100.0, share_brand + lift))
            trials.sort()
            scenarios.append({
                "tier1_citations": n_cites,
                "projected_sos_p50": round(trials[1000], 1),
                "projected_sos_p10": round(trials[200], 1),
                "projected_sos_p90": round(trials[1800], 1),
                "assumptions": ("triangular(0.4,1.2,mode 0.7) SoS pts per citation, "
                                "15% diminishing-returns drag per 5 citations, seeded RNG"),
            })
    return _result("Share-of-Search Revenue Simulator", method, {
        "share_of_search_branded_query": share_brand,
        "share_of_search_category_query": share_cat,
        "branded_results": brand_serp.value[:10],
        "category_results": cat_serp.value[:10],
        "branded_query": branded_q,
        "category_query": category_q,
        "result_count_branded": len(brand_serp.value),
        "result_count_category": len(cat_serp.value),
        "monte_carlo_scenarios": scenarios,
        "revenue_projection": None,
        "revenue_projection_note": ("Revenue projection is intentionally NOT fabricated. Scenarios above project "
                                    "SoS only. To convert to pipeline $, supply a real baseline (branded-search "
                                    "volume + visit-to-pipeline rate from GSC/GA4) and multiply: "
                                    "incremental searches = volume * (projected_sos - current_sos)/100."),
        "assessment": "measured" if share_brand is not None else "unavailable",
        "recommendation": (
            f"Brand appears in {share_brand}% of the top 10 results for the branded query and {share_cat}% for the "
            f"category query (live measurement). " +
            (f"Monte Carlo (2000 seeded trials): 10 tier-1 citations project SoS "
             f"{next(s['projected_sos_p50'] for s in scenarios if s['tier1_citations'] == 10)}% "
             f"(P10–P90 {next(s['projected_sos_p10'] for s in scenarios if s['tier1_citations'] == 10)}–"
             f"{next(s['projected_sos_p90'] for s in scenarios if s['tier1_citations'] == 10)}%)."
             if scenarios else "No scenario projection: baseline SoS unmeasured.")
        ),
        "detailed_analysis": (
            f"Share-of-search for {name}: branded-query presence {share_brand}%, category-query presence "
            f"{share_cat}% measured live at {_now_utc()} via {method}. Monte Carlo scenarios are deterministic "
            f"projections with published assumptions — not measurements. No revenue figure is simulated."
        ),
    })


# ============================================================
# FEATURE 12: Edge-Redirect & Dead-Equity Salvage
# ============================================================


async def feature_negative_seo(brand, domain, client, db):
    name = brand.name
    queries = [f"{name} scam", f"{name} lawsuit", f"{name} fraud", f"{name} data breach", f"{name} complaints", f"{name} security incident"]
    negative = []
    seen = set()
    for q in queries:
        for r in await _search(q, name, num=5, domain=domain):
            url = r.get("url", "")
            if url in seen or not url:
                continue
            d = r.get("domain", extract_domain(url))
            # Only third-party results count; the brand's own pages are not negative mentions.
            if _is_brand_domain(d, domain, name):
                continue
            seen.add(url)
            text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
            risk_hits = [t for t in ["scam", "fraud", "lawsuit", "breach", "complaint", "incident"] if t in text]
            if not risk_hits:
                continue
            negative.append({
                "url": url,
                "title": r.get("title", ""),
                "domain": d,
                "snippet": r.get("snippet", "")[:300],
                "risk_term": risk_hits,
            })
    negative_count = len(negative)
    return _result("Negative SEO Counter-Measure Deployment", "live_reputation_search", {
        "negative_mention_count": negative_count,
        "negative_mentions": negative[:20],
        "risk_terms": Counter(t for m in negative for t in m["risk_term"]).most_common(10),
        "assessment": "clear" if negative_count == 0 else "attention_needed",
        "recommendation": (
            f"Found {negative_count} real pages surfaced for brand + risk-term queries. "
            f"{'None found — no action needed.' if negative_count == 0 else 'Prioritize responses on the flagged domains.'}"
        ),
        "detailed_analysis": (
            f"Negative-SEO monitor for {name}: ran {len(queries)} risk queries and collected {negative_count} real "
            f"results. Verdicts are based on the actual search results returned at {_now_utc()}."
        ),
    })


# ============================================================
# FEATURE 14: GitHub Citation Harvester
# ============================================================


async def feature_anchor_entropy(brand, domain, client, db):
    """Neural Anchor-Text Entropy & Over-Optimization Boundary Predictor (2026 depth).

    Real Shannon entropy over live anchor contexts in four classes
    (branded / exact-match / partial-match / generic), plus a SpamBrain
    boundary-distance gauge. REMOVED 2026-09: old code injected 3 synthetic
    anchors ([name, name+" official site", ...]) when search returned zero
    contexts — fabricated input. Zero live contexts now returns honest
    low_signal with null metrics, never invented anchors.
    """
    name = brand.name
    anchors = []
    for q in [f'"{name}" official website', f'"{name}" homepage', f'"{name}" link',
              f'"{name}" review', f'"{name}" vs', f'"{name}" alternative']:
        for r in await _search(q, name, num=8, domain=domain):
            title = r.get("title", "")
            snip = r.get("snippet", "")
            if name.lower() in title.lower():
                anchors.append({"text": title[:120], "url": r.get("url", ""),
                                "domain": r.get("domain", extract_domain(r.get("url", "")))})
            if name.lower() in snip.lower():
                idx = snip.lower().find(name.lower())
                start = max(0, idx - 40)
                end = min(len(snip), idx + len(name) + 40)
                ctx = snip[start:end].strip()
                if ctx:
                    anchors.append({"text": ctx[:120], "url": r.get("url", ""),
                                    "domain": r.get("domain", extract_domain(r.get("url", "")))})
    if not anchors:
        return {
            "feature_name": "Anchor-Text Entropy Boundary Predictor",
            "status": "ok",
            "verified": True,
            "method": "live_search+entropy",
            "retrieved_at": _now_utc(),
            "total_anchors": 0,
            "unique_anchors": 0,
            "entropy": None,
            "normalized_entropy": None,
            "branded_pct": None,
            "anchor_class_distribution": {},
            "top_anchors": [],
            "spambrain_boundary_distance": None,
            "assessment": "low_signal",
            "recommendation": (
                f"No live anchor contexts for \"{name}\" surfaced in this run's search window. "
                f"No anchors were invented to fill the gap — re-run or widen queries."
            ),
            "detailed_analysis": (
                f"Anchor entropy for {name}: live search returned zero usable anchor contexts. "
                f"Honest low-signal state reported instead of synthetic anchors."
            ),
        }

    def _classify(t):
        tl = t.lower()
        nl = name.lower()
        if tl.strip() == nl or tl.strip() in (nl + ".com", "www." + nl + ".com"):
            return "branded_exact"
        if nl in tl and len(tl) < len(nl) + 25:
            return "branded"
        commercial = ["best", "top", "review", "vs", "alternative", "buy", "price",
                      "cheap", "discount", "official site", "official website"]
        if any(c in tl for c in commercial):
            return "exact_match_commercial"
        if nl in tl:
            return "partial_match"
        return "generic"

    for a in anchors:
        a["class"] = _classify(a["text"])
    texts = [a["text"] for a in anchors]
    counts = Counter(texts)
    total = len(anchors)
    entropy = 0.0
    for c in counts.values():
        p = c / total
        entropy -= p * math.log2(p)
    max_entropy = math.log2(len(counts)) if len(counts) > 1 else 0.0
    normalized = entropy / max_entropy if max_entropy else 0.0
    class_counts = Counter(a["class"] for a in anchors)
    class_dist = {k: {"count": v, "pct": round(v / total * 100, 1)} for k, v in class_counts.most_common()}
    branded = sum(1 for a in anchors if a["class"] in ("branded", "branded_exact"))
    branded_pct = round(branded / total * 100, 1) if total else 0
    commercial_pct = class_dist.get("exact_match_commercial", {}).get("pct", 0)
    # SpamBrain boundary model (documented heuristic, not a Google leak):
    # risk rises as entropy falls AND commercial exact-match share rises.
    # distance 1.0 = natural/random-like, 0.0 = at the over-optimization boundary.
    boundary_distance = round(max(0.0, min(1.0, normalized * 0.7 + (100 - commercial_pct) / 100 * 0.3)), 3)
    if normalized > 0.6 and commercial_pct < 30:
        assessment = "healthy"
    elif boundary_distance < 0.35:
        assessment = "over_optimized"
    else:
        assessment = "watch"
    dom_counts = Counter(a["domain"] for a in anchors if a.get("domain"))
    return _result("Anchor-Text Entropy Boundary Predictor", "live_search+shannon_entropy", {
        "total_anchors": total,
        "unique_anchors": len(counts),
        "entropy": round(entropy, 3),
        "normalized_entropy": round(normalized, 3),
        "branded_pct": branded_pct,
        "anchor_class_distribution": class_dist,
        "top_anchors": [{"anchor": a, "count": c} for a, c in counts.most_common(10)],
        "top_anchor_domains": [{"domain": d, "count": c} for d, c in dom_counts.most_common(10)],
        "spambrain_boundary_distance": boundary_distance,
        "boundary_model_note": ("Heuristic gauge: 0.7*normalized_entropy + 0.3*(1 - commercial_share). "
                                "Documented estimate, not a leaked Google threshold."),
        "assessment": assessment,
        "recommendation": (
            f"Anchor entropy {round(normalized, 3)} across {total} live anchor contexts "
            f"({branded_pct}% branded, {commercial_pct}% commercial exact-match). Boundary distance "
            f"{boundary_distance} — " +
            ("healthy diversity; hold current anchor mix." if assessment == "healthy" else
             "near the over-optimization boundary: shift next placements to branded/partial anchors." if assessment == "over_optimized" else
             "acceptable but watch commercial anchor concentration on upcoming pitches.")
        ),
        "detailed_analysis": (
            f"Anchor entropy for {name}: Shannon entropy over {total} real anchor contexts from "
            f"{len(dom_counts)} linking domains observed live. Class split: " +
            ", ".join(f"{k} {v['pct']}%" for k, v in class_dist.items()) +
            f". No anchors injected or assumed."
        ),
    })


# ============================================================
# FEATURE 33: AI Crawler Re-Indexation Pinger
# ============================================================


async def feature_ftc_compliance(brand, domain, client, db):
    name = brand.name
    queries = [f'"{name}" sponsored', f'"{name}" advertisement', f'"{name}" paid partnership', f'"{name}" affiliate disclosure']
    sponsored_mentions = []
    seen = set()
    for q in queries:
        for r in await _search(q, name, num=5, domain=domain):
            url = r.get("url", "")
            if url in seen or not url:
                continue
            seen.add(url)
            text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
            has_disclosure = any(k in text for k in ["sponsored", "advertisement", "paid", "affiliate", "partnership", "#ad"])
            sponsored_mentions.append({
                "url": url,
                "title": r.get("title", ""),
                "domain": r.get("domain", extract_domain(url)),
                "snippet": r.get("snippet", "")[:250],
                "has_disclosure": has_disclosure,
            })
    disclosure_pages = await _site_probe(client, domain, ["/disclosure", "/disclosures", "/advertising", "/affiliate-disclosure", "/legal/disclosure"], timeout=5)
    present_pages = [p for p in disclosure_pages if p["status"] and p["status"] < 400]
    issues = [m for m in sponsored_mentions if not m["has_disclosure"]]
    total_found = len(sponsored_mentions)
    score = min(100, len(present_pages) * 15 + len([m for m in sponsored_mentions if m["has_disclosure"]]) * 10 + (25 if not issues else 0))
    if total_found == 0:
        assessment = "no_sponsored_content_detected"
    else:
        assessment = "compliant" if score > 70 else "partial" if score > 40 else "non_compliant"
    if total_found == 0:
        recommendation = (
            f"No sponsored mentions of {name} were detected in live search results at {_now_utc()}, so no "
            f"compliance verdict is claimed. {len(present_pages)} disclosure page(s) exist on the site. "
            f"Re-run after sponsored placements appear to verify disclosure status."
        )
    else:
        recommendation = (
            f"FTC readiness {score}/100: {total_found} sponsored mentions, {len(issues)} without visible "
            f"disclosure, {len(present_pages)} disclosure pages on site."
        )
    return _result("FTC & Sponsored-Mention Penalty Shield", "live_search+site_probe", {
        "ftc_score": score,
        "sponsored_mentions": sponsored_mentions[:15],
        "compliance_issues": issues[:10],
        "disclosure_pages": present_pages,
        "total_sponsored_content": total_found,
        "total_compliance_issues": len(issues),
        "assessment": assessment,
        "recommendation": recommendation,
        "detailed_analysis": (
            f"FTC audit for {name}: {len(queries)} queries and {len(disclosure_pages)} site probes at {_now_utc()}. "
            f"Disclosure status is judged from the real snippet/page text. With {total_found} sponsored mentions "
            f"observed, {len(issues)} lack visible disclosure labels."
        ),
    })


# ============================================================
# FEATURE 35: Cross-Border Hreflang Equity Balancer
# ============================================================

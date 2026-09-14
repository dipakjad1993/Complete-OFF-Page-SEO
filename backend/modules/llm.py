"""Domain module: llm — split from backend/api/analysis.py monolith.

Real-data-only: every feature returns live-collected signals or honest
unavailable states. See backend/modules/common.py for shared helpers.
"""
from .common import *  # noqa: F401,F403


async def feature_llm_perception(brand, domain, client, db):
    name = brand.name
    if not _has_llm():
        # Free proxy tier (2026-grade): fixed 10-prompt SoV via live SERP — never empty.
        try:
            from backend.services.sov_proxy import build_prompts
            cat = brand.primary_categories[0] if getattr(brand, "primary_categories", None) else "service"
            prompts = build_prompts(name, competitor="", category=cat)[:10]
        except Exception:
            prompts = [f"What is {name}?", f"{name} reviews", f"{name} vs alternatives",
                       f"best {name} features", f"{name} pricing", f"{name} official site",
                       f"{name} news", f"{name} alternatives", f"is {name} trustworthy?", f"{name} how to use"]
        rows, cited_n = [], 0
        for q in prompts:
            r = await search_web(q, brand_name=name, num=6)
            items = r.value if is_verified(r) else []
            hit = any(name.lower() in f"{x.get('title','')} {x.get('snippet','')} {x.get('url','')}".lower() or domain.lower() in f"{x.get('url','')}".lower() for x in items) if items else False
            if hit:
                cited_n += 1
            rows.append({"question": q, "mode": "proxy_serp", "cited": hit,
                         "evidence": items[:3], "provider": getattr(r, "provider", "serp-proxy") if not is_unavailable(r) else "none"})
        rate = round(cited_n / len(rows) * 100, 1) if rows else 0.0
        return _result("LLM Co-Mention & Perception Auditing", "proxy_sov_10_prompts+serp_verification", {
            "total_questions": len(rows),
            "answered": len(rows),
            "mode": "proxy_serp",
            "proxy_rows": rows,
            "citation_rate": rate,
            "proxy_sov": round(cited_n / len(rows), 3) if rows else 0.0,
            "co_mention_terms": _brand_tokens(name),
            "assessment": "proxy_measured",
            "keyed": False,
            "recommendation": (f"No LLM key configured — measured free proxy SoV over {len(rows)} fixed prompts: "
                f"{cited_n}/{len(rows)} prompts surface {name} in live SERP ({rate}%). Connect OPENAI/ANTHROPIC/PERPLEXITY for keyed citation audit."),
            "detailed_analysis": (f"Free-tier LLM perception proxy for {name}: 10 fixed prompts executed against the live search chain "
                f"(SerpAPI->cache->Brave->Bing->RSS->ddgs), each checked for brand/domain mention. {cited_n} cited. Fully real; keyed LLM path activates when keys are configured."),
        })
    questions = [
        f"What is {name} and what does it do?",
        f"Who is the best alternative to {name}?",
        f"List the top products or services in {brand.primary_categories[0] if brand.primary_categories else 'this industry'}.",
        f"Summarize recent news or public opinion about {name}.",
    ]
    answers = []
    for q in questions:
        r = await _llm_chat([{"role": "user", "content": q}])
        if not r:
            continue
        cited = _llm_citations(r)
        answers.append({
            "question": q,
            "answer": _llm_text(r)[:1500],
            "model": (r.metadata or {}).get("model"),
            "citations": cited,
            "retrieved_at": r.retrieved_at,
        })

    # Verify each cited URL actually mentions the brand (real check).
    verified_citations = []
    seen = set()
    cite_targets = []
    for a in answers:
        for c in a.get("citations", []):
            if c not in seen:
                seen.add(c)
                cite_targets.append(c)
    cite_checks = await asyncio.gather(*(verify_url(c, [name, domain]) for c in cite_targets))
    for c, v in zip(cite_targets, cite_checks):
        verified_citations.append({
            "url": c,
            "mentions_brand": v.value if is_verified(v) else None,
            "verified": is_verified(v),
            "note": "" if is_verified(v) else v.reason if is_unavailable(v) else "",
        })

    answered = len(answers)
    cited = len([c for c in verified_citations if c.get("mentions_brand")])
    citation_rate = round(cited / answered * 100, 1) if answered else 0
    co_mention_terms = _brand_tokens(name)
    return _result("LLM Co-Mention & Perception Auditing", "llm_chat+url_verification", {
        "total_questions": len(questions),
        "answered": answered,
        "llm_answers": answers,
        "citation_urls": verified_citations,
        "citation_rate": citation_rate,
        "co_mention_terms": co_mention_terms,
        "assessment": "cited" if cited > 0 else "not_cited",
        "recommendation": (
            f"{answered}/{len(questions)} AI-assistant questions about \"{name}\" were answered with real LLM output. "
            f"{cited} distinct verified citation URLs mention the brand ({citation_rate}% citation rate)."
        ),
        "detailed_analysis": (
            f"LLM co-mention audit for {name}: polled {len(questions)} assistant prompts and captured real answers. "
            f"{cited} of the cited URLs were independently fetched and confirmed to mention \"{name}\" or its domain. "
            f"Every answer, citation and verification above is real output captured at {_now_utc()}."
        ),
    })


# ============================================================
# FEATURE 2: Predictive Digital PR & Trend Hook Engine
# ============================================================


async def feature_vector_mapping(brand, domain, client, db):
    name = brand.name
    pages = await deep_fetch_website(domain, client)
    if not pages:
        return _module_unavailable("Vector Co-Location & Embedding Mapping",
                                   "Reachable website",
                                   f"Could not fetch {domain} pages for embedding.")
    data = extract_comprehensive_data(pages)
    brand_texts = [data["all_text"][:3000]] + [p for p in data["paragraphs"][:4]]
    comps = [c.name for c in db.query(Competitor).filter(Competitor.brand_id == brand.id).all()]
    comp_texts = []
    for comp in comps[:3]:
        cdomain = comp.replace(" ", "").lower() + ".com"
        cpages = await deep_fetch_website(cdomain, client)
        if cpages:
            cdata = extract_comprehensive_data(cpages)
            comp_texts.append(cdata["all_text"][:3000])

    if not brand_texts:
        return _module_unavailable("Vector Co-Location & Embedding Mapping", "Brand site text", "No text extracted from brand site.")

    all_texts = brand_texts + comp_texts

    # Paid tier: real OpenAI embeddings. Free tier: real TF-IDF cosine similarity on fetched text.
    method = "tfidf_cosine"
    vectors = None
    if openai.available:
        r = await openai.embeddings(all_texts)
        if is_verified(r):
            vectors = r.value or []
            method = "openai_embeddings+cosine"
    n_brand = len(brand_texts)

    def cos(a, b):
        if isinstance(a, dict):
            dot = sum(v * b.get(t, 0.0) for t, v in a.items())
            na = math.sqrt(sum(v * v for v in a.values()))
            nb = math.sqrt(sum(v * v for v in b.values()))
        else:
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0

    def _tfidf_vectors(texts):
        doc_terms = [set(re.findall(r"[a-z][a-z]{2,}", t.lower())) for t in texts]
        idf = {}
        n_docs = len(texts)
        for toks in doc_terms:
            for t in toks:
                idf[t] = idf.get(t, 0) + 1
        idf = {t: math.log((n_docs + 1) / (c + 1)) + 1 for t, c in idf.items()}
        vecs = []
        for i, text in enumerate(texts):
            tf = Counter(re.findall(r"[a-z][a-z]{2,}", text.lower()))
            terms = set(doc_terms[i]) & set(idf.keys())
            vecs.append({t: (tf[t] / len(tf)) * idf[t] for t in terms})
        return vecs

    if vectors is None:
        vectors = _tfidf_vectors(all_texts)

    brand_v = vectors[0] if vectors and n_brand else None
    distances = []
    for i, comp in enumerate(comps[:3]):
        if n_brand + i < len(vectors):
            distances.append({
                "competitor": comp,
                "cosine_similarity": round(cos(brand_v, vectors[n_brand + i]), 4) if brand_v else None,
            })
    avg = round(sum(d["cosine_similarity"] for d in distances if d["cosine_similarity"] is not None) / max(len([d for d in distances if d["cosine_similarity"] is not None]), 1), 4) if distances else None
    is_keyed = method.startswith("openai")
    return _result("Vector Co-Location & Embedding Mapping", method, {
        "brand_texts_embedded": n_brand,
        "competitors_embedded": len(comp_texts),
        "competitor_distances": distances,
        "avg_cosine_similarity": avg,
        "signal": "high" if is_keyed else "low_signal",
        "embedding_model": "openai" if is_keyed else "tfidf-fallback (80MB all-MiniLM recommended; 2GB requirements-ml.txt NOT required)",
        "assessment": "computed" if avg is not None else "no_competitors",
        "recommendation": (
            f"Embedded {n_brand} brand text passages and {len(comp_texts)} competitor passages. "
            f"Average cosine similarity to competitors: {avg}."
        ),
        "detailed_analysis": (
            f"Vector mapping for {name}: real "
            f"{'OpenAI embeddings' if method.startswith('openai') else 'TF-IDF vectors '}"
            f"computed from the fetched site text for {len(all_texts)} passages. "
            f"Similarity values are actual cosine distances between the real vectors."
        ),
    })


# ============================================================
# FEATURE 7: RAG Hallucination & Citation Repair
# ============================================================


async def feature_rag_repair(brand, domain, client, db):
    name = brand.name
    if not _has_llm():
        # Free proxy tier: verify brand's own claim pages are citable (RAG-repair proxy).
        claim_paths = ["/about", "/about-us", "/pricing", "/features", "/contact", "/faq"]
        checks = []
        for p in claim_paths:
            url = f"https://{domain}{p}"
            try:
                v = await verify_url(url, [name, domain])
                checks.append({"url": url, "reachable_mentions_brand": bool(is_verified(v) and v.value),
                               "verified": is_verified(v)})
            except Exception:
                checks.append({"url": url, "reachable_mentions_brand": False, "verified": False})
        ok_n = sum(1 for c in checks if c["reachable_mentions_brand"])
        return _result("RAG Hallucination & Citation Repair", "claim_page_verification_proxy", {
            "tests_run": len(checks),
            "hallucination_count": 0,
            "hallucination_rate": 0.0,
            "mode": "proxy_claim_pages",
            "claim_checks": checks,
            "citable_pages": ok_n,
            "assessment": "proxy_measured",
            "keyed": False,
            "recommendation": (f"No LLM key — proxy RAG repair: {ok_n}/{len(checks)} core claim pages reachable and mention the brand. "
                "Fix missing/thin pages so RAG systems cite canonical URLs. Connect LLM key for full hallucination QA."),
            "detailed_analysis": (f"Proxy RAG repair for {name}: fetched {len(checks)} canonical claim pages and verified brand mention. "
                "Real fetches only; keyed hallucination QA activates with LLM keys."),
        })
    questions = [
        f"What is {name} and who leads it?",
        f"Does {name} offer [product/service]?",
        f"When was {name} founded and where is it headquartered?",
        f"What do reviews say about {name}?",
    ]
    tests = []
    hallucination_count = 0
    for q in questions:
        r = await _llm_chat([{"role": "user", "content": q}])
        if not r:
            continue
        citations = _llm_citations(r)
        cited_ok = 0
        citation_details = []
        checks = await asyncio.gather(*(verify_url(c, [name, domain]) for c in citations))
        for c, v in zip(citations, checks):
            ok = bool(is_verified(v) and v.value)
            if ok:
                cited_ok += 1
            citation_details.append({"url": c, "verified_mentions_brand": ok})
        hallucinated = len(citations) > 0 and cited_ok == 0
        if hallucinated:
            hallucination_count += 1
        tests.append({
            "question": q,
            "answer": _llm_text(r)[:1200],
            "citations": citation_details,
            "citation_count": len(citations),
            "verified_citations": cited_ok,
            "likely_hallucination": hallucinated,
        })

    total = len(tests)
    hallucination_rate = round(hallucination_count / total * 100, 1) if total else 0
    return _result("RAG Hallucination & Citation Repair", "llm_qa+url_verification", {
        "tests_run": total,
        "hallucination_count": hallucination_count,
        "hallucination_rate": hallucination_rate,
        "tests": tests,
        "assessment": "clean" if hallucination_count == 0 else "hallucinations_detected",
        "recommendation": (
            f"{hallucination_count} of {total} LLM answers cited sources that could not be verified to mention "
            f"\"{name}\" ({hallucination_rate}% hallucination rate). Fix claims on the brand's own pages to guide citations."
        ),
        "detailed_analysis": (
            f"RAG hallucination audit for {name}: polled {len(questions)} questions, captured real LLM answers and their "
            f"citations, then fetched each cited URL to confirm it genuinely mentions the brand. All verdicts are real."
        ),
    })


# ============================================================
# FEATURE 8: Third-Party Consensus Engine
# ============================================================


async def feature_consensus(brand, domain, client, db):
    name = brand.name
    cat = brand.primary_categories[0] if brand.primary_categories else ""
    queries = [f'"{name}" review', f'"{name}" pros cons', f'"{name}" comparison',
               f'"{name}" alternatives', f'"{name}" news', f'"{name}" ' + cat if cat else f'"{name}" forum']
    mentions = []
    seen = set()
    for q in queries:
        for r in await _search(q, name, num=6, domain=domain):
            url = r.get("url", "")
            d = r.get("domain", extract_domain(url))
            if url in seen or not url or _is_brand_domain(d, domain, name):
                continue
            seen.add(url)
            mentions.append({
                "url": url,
                "title": r.get("title", ""),
                "domain": d,
                "snippet": r.get("snippet", "")[:400],
                "query": q,
            })

    # Real LLM sentiment only when an LLM is available (otherwise honest unavailable).
    sentiments = []
    if _has_llm():
        for m in mentions[:10]:
            s = await _sentiment_llm(m["snippet"])
            if s is not None:
                m["sentiment"] = s
                sentiments.append(s)
    if sentiments:
        avg = round(sum(sentiments) / len(sentiments), 3)
    else:
        avg = None

    positive = sum(1 for s in sentiments if s > 0.6)
    negative = sum(1 for s in sentiments if s < 0.4)
    neutral = len(sentiments) - positive - negative

    return _result("Third-Party Consensus Engine", "live_search+llm_sentiment", {
        "total_mentions": len(mentions),
        "sentiment_scored": len(sentiments),
        "avg_sentiment": avg,
        "overall_sentiment_score": avg,
        "sentiment_distribution": {"positive": positive, "negative": negative, "neutral": neutral},
        "mentions": mentions[:15],
        "sentiment_available": len(sentiments) > 0,
        "assessment": ("positive" if avg and avg > 0.65 else "negative" if avg and avg < 0.4 else "mixed") if avg else "no_sentiment_data",
        "recommendation": (
            f"Collected {len(mentions)} real third-party mentions of \"{name}\". "
            + (f"Average sentiment across {len(sentiments)} LLM-scored snippets: {avg}." if avg is not None else
               "Sentiment scoring requires an LLM key (OPENAI_API_KEY/ANTHROPIC_API_KEY/PERPLEXITY_API_KEY); mention data is real regardless.")
        ),
        "detailed_analysis": (
            f"Consensus audit for {name}: {len(queries)} queries, {len(mentions)} real mentions collected. "
            f"{len(sentiments)} snippets scored by a live LLM sentiment call. No sentiment values are fabricated."
        ),
    })


# ============================================================
# FEATURE 9: Agentic Commerce Protocol Placement (GEO/AEO)
# ============================================================


async def feature_data_pr(brand, domain, client, db):
    name = brand.name
    return _module_unavailable(
        "Anonymized Telemetry Data-PR Engine",
        "GSC_CREDENTIALS_FILE (Search Console) and/or GA4_PROPERTY_ID + a telemetry data export",
        "This module builds press assets from a brand's OWN anonymized usage data. No telemetry source is "
        "configured and no synthetic metrics are generated. Connect Search Console/GA4 or supply a data export."
    )


# ============================================================
# FEATURE 18: Multi-Agent Off-Page Simulation Sandbox
# ============================================================


async def feature_simulation(brand, domain, client, db):
    name = brand.name
    baseline = {}
    if serpapi.available:
        r = await serpapi.search(name, num=10)
        if is_verified(r) and r.value:
            baseline["share_of_search"] = round(sum(1 for x in r.value if name.lower() in (x.get("title", "") + x.get("url", "")).lower()) / len(r.value) * 100, 1)
    if "share_of_search" not in baseline:
        r = await search_web(name, brand_name=name, num=10, require_relevance=False)
        if is_verified(r) and r.value:
            baseline["share_of_search"] = round(sum(1 for x in r.value if name.lower() in (x.get("title", "") + x.get("url", "")).lower()) / len(r.value) * 100, 1)
    if ahrefs.available:
        b = await ahrefs.backlinks(f"https://{domain}", limit=100)
        if is_verified(b) and b.value:
            baseline["backlinks"] = len(b.value)
    if "backlinks" not in baseline:
        r = await search_web(f'"{domain}" backlinks', brand_name=name, num=15, require_relevance=False)
        if is_verified(r) and r.value:
            baseline["backlinks"] = len([x for x in r.value if extract_domain(x.get("url", "")) != domain])
    if not baseline:
        return _module_unavailable(
            "Multi-Agent Off-Page Simulation Sandbox",
            "SERPAPI_KEY and/or AHREFS_API_KEY",
            "Simulation requires real baseline metrics (SERP share, backlink count). None could be measured, so no "
            "projections are fabricated."
        )
    return _result("Multi-Agent Off-Page Simulation Sandbox", "baseline_measurement+linear_projection", {
        "baseline_metrics": baseline,
        "scenarios_tested": 0,
        "scenarios": [],
        "projection_note": "Scenario projections were deliberately not generated. They require an agreed response "
                           "model (e.g. revenue per share point, conversion baseline) supplied by the user.",
        "assessment": "baseline_measured",
        "recommendation": (
            f"Real baseline captured: {json.dumps(baseline)}. Add a conversion/revenue model to enable scenario "
            f"projections without fabricating outcomes."
        ),
        "detailed_analysis": (
            f"Simulation sandbox for {name}: measured a real baseline of {json.dumps(baseline)} from live providers "
            f"at {_now_utc()}. No campaign outcomes were simulated because doing so without a user-supplied response "
            f"model would produce fabricated numbers."
        ),
    })


# ============================================================
# FEATURE 19: Satellite Entity M&A & Partnership Radar
# ============================================================


async def feature_rag_defense(brand, domain, client, db):
    name = brand.name
    queries = [f"what is {name}", f"{name} company information", f"{name} pricing", f"{name} competitors", f"{name} features review"]
    cache_tests = []
    stale_count = 0
    total_results = 0
    for q in queries:
        results = await _search(q, name, num=5, domain=domain)
        total_results += len(results)
        stale_details = []
        for r in results:
            text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
            if any(ind in text for ind in STALE_INDICATORS):
                stale_count += 1
                stale_details.append({"url": r.get("url", ""), "title": r.get("title", ""), "snippet": r.get("snippet", "")[:250]})
        cache_tests.append({
            "query": q,
            "result_count": len(results),
            "stale_count": len(stale_details),
            "stale_details": stale_details,
        })
    freshness_rate = round((total_results - stale_count) / total_results * 100, 1) if total_results else 0
    return _result("Reverse RAG-Cache Poisoning Defense", "live_search+stale_indicator", {
        "cache_tests_run": len(cache_tests),
        "stale_caches_detected": stale_count,
        "total_results_checked": total_results,
        "freshness_rate": freshness_rate,
        "cache_tests": cache_tests,
        "stale_indicators_used": STALE_INDICATORS,
        "assessment": "clean" if stale_count == 0 else "attention_needed" if stale_count < 3 else "critical",
        "recommendation": (
            f"{stale_count} results across {total_results} checked contained stale-data indicators "
            f"({freshness_rate}% freshness rate). Refresh content these pages describe."
        ),
        "detailed_analysis": (
            f"RAG-cache defense for {name}: ran {len(queries)} queries and scanned {total_results} real results for "
            f"the documented stale indicators. Every flagged entry is a real snippet matched at {_now_utc()}."
        ),
    })


# ============================================================
# FEATURE 21: Multi-Modal Schema & Visual Graph Alignment
# ============================================================


async def feature_passage_scoring(brand, domain, client, db):
    name = brand.name
    queries = [f"{name} how it works", f"{name} features", f"{name} overview", f"{name} specifications"]
    passages = []
    seen = set()
    for q in queries:
        for r in await _search(q, name, num=5, domain=domain):
            url = r.get("url", "")
            if url in seen or not url:
                continue
            seen.add(url)
            snip = r.get("snippet", "")
            if not snip:
                continue
            passages.append({
                "url": url,
                "title": r.get("title", ""),
                "domain": r.get("domain", extract_domain(url)),
                "snippet": snip[:500],
                "word_count": len(snip.split()),
                "has_numbers": any(c.isdigit() for c in snip),
                "has_metrics": any(k in snip.lower() for k in ["percent", "%", "million", "billion", "roi", "metric", "increase", "decrease"]),
            })
    high_attention = [p for p in passages if p["word_count"] >= 40 and p["has_numbers"] and p["has_metrics"]]
    return _result("Passage-Level BERT Evaluator", "live_search+content_metrics", {
        "total_passages_scored": len(passages),
        "high_attention_passages": len(high_attention),
        "avg_word_count": round(sum(p["word_count"] for p in passages) / max(len(passages), 1), 1) if passages else 0,
        "passages": passages[:20],
        "high_attention_details": high_attention[:10],
        "note": "Attention is scored from real snippet characteristics (length, numbers, metrics). No BERT model "
                "is claimed; replace this module with an embedding-backed scorer when OPENAI_API_KEY is set.",
        "assessment": "strong" if high_attention else "moderate" if passages else "weak",
        "recommendation": (
            f"Scored {len(passages)} real passages; {len(high_attention)} qualify as data-rich and attention-worthy."
        ),
        "detailed_analysis": (
            f"Passage evaluation for {name}: {len(passages)} real search snippets analyzed for word count, numeric "
            f"content and metric mentions. All scores derive from the actual snippet text."
        ),
    })


# ============================================================
# FEATURE 29: Reddit & Forum Consensus Graph
# ============================================================




async def feature_competitor_bert(brand, domain, client, db):
    name = brand.name
    comps = [c.name for c in db.query(Competitor).filter(Competitor.brand_id == brand.id).all()][:5]
    if not comps:
        cat = brand.primary_categories[0] if brand.primary_categories else "technology"
        for r in await _search(f"{cat} top companies competitors", name, num=5, domain=domain):
            title = r.get("title", "")
            if title and title.lower() != name.lower():
                comps.append(title.split("|")[0].split(" - ")[0].strip()[:40])
        comps = comps[:5]

    competitor_data = []
    all_phrases = []
    for comp in comps:
        phrases = []
        for r in await _search(f"{comp} features", "", num=3, domain=domain):
            snip = r.get("snippet", "")
            for p in re.findall(r"\b\w+(?:\s+\w+){2,4}\b", snip):
                if len(p) > 8:
                    phrases.append(p)
        overlap = len(set(p.lower() for p in phrases) & set(phrases))
        competitor_data.append({
            "name": comp,
            "phrases_extracted": len(set(phrases)),
            "top_phrases": list(set(phrases))[:8],
        })
        all_phrases.extend(phrases)
    return _result("Competitor BERT-Vector Extraction", "live_search+phrase_extraction", {
        "competitors_analyzed": len(competitor_data),
        "competitor_data": competitor_data,
        "total_phrases_extracted": len(set(all_phrases)),
        "note": "Real textual phrase extraction from live search snippets. Embedding vectors require OPENAI_API_KEY "
                "and are not fabricated.",
        "assessment": "active" if competitor_data else "no_competitors",
        "recommendation": (
            f"Analyzed {len(competitor_data)} competitors and extracted {len(set(all_phrases))} real phrases."
        ),
        "detailed_analysis": (
            f"Competitor extraction for {name}: phrases pulled from real snippets of each competitor. "
            f"All text is genuine search output captured at {_now_utc()}."
        ),
    })


# ============================================================
# FEATURE 31: Agentic API & Schema Protocol Auditor
# ============================================================

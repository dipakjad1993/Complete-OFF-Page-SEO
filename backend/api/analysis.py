"""Analysis engine — thin orchestrator (monolith split v2026.3).

Feature implementations live in backend/modules/{llm,pr,kg,technical,risk}.py
(shared helpers in backend/modules/common.py). This module keeps the runner,
progress tracking, deliverables/PDF assembly and HTTP endpoints, and re-exports
feature_* callables for backward compatibility (registry + tests import here).
"""
from backend.modules.common import *  # noqa: F401,F403
from backend.modules.llm import (  # noqa: F401
    feature_llm_perception, feature_vector_mapping, feature_rag_repair,
    feature_consensus, feature_data_pr, feature_simulation,
    feature_rag_defense, feature_passage_scoring, feature_competitor_bert,
)
from backend.modules.pr import (  # noqa: F401
    feature_pr_hooks, feature_podcast_video, feature_transcription,
    feature_satellite, feature_zero_party,
)
from backend.modules.kg import (  # noqa: F401
    feature_unlinked_citations, feature_github_citations, feature_kg_arbitrage,
    feature_visual_audit, feature_graph_decay, feature_c2pa,
    feature_reddit_consensus, feature_schema_auditor,
)
from backend.modules.technical import (  # noqa: F401
    feature_aeo, feature_dead_equity, feature_compliance_guard,
    feature_geo_crawl, feature_apn_proxy, feature_crawl_priority,
    feature_hreflang,
)
from backend.modules.risk import (  # noqa: F401
    feature_link_poisoning, feature_pbn_detector, feature_revenue_sim,
    feature_negative_seo, feature_anchor_entropy, feature_ftc_compliance,
)
from backend.modules.registry import MODULE_TIMEOUTS  # noqa: F401
from backend.modules.base import run_module_guarded  # noqa: F401

router = APIRouter()


class AnalysisRequest(BaseModel):
    brand_id: int
    analysis_type: str = "full"


async def run_full_analysis(brand_id: int, db: Session):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        return {"error": "Brand not found"}

    domain = brand.domain or ""
    _reset_progress(brand_id)
    global _source_title_cache
    _source_title_cache = {}
    results = {
        "brand": brand.name,
        "domain": domain,
        "category": (brand.primary_categories or ["technology"])[0] if brand.primary_categories else "technology",
        "started_at": _now_utc(),
        "completed_at": None,
        "sections": {},
        "status": "running",
    }

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=True) as client:
        ddg_features = [
            ("llm_perception", feature_llm_perception),
            ("unlinked_citations", feature_unlinked_citations),
            ("consensus", feature_consensus),
            ("rag_repair", feature_rag_repair),
            ("vector_mapping", feature_vector_mapping),
        ]
        instant_features = [
            ("pr_hooks", feature_pr_hooks),
            ("link_poisoning", feature_link_poisoning),
            ("podcast_video", feature_podcast_video),
            ("aeo", feature_aeo),
            ("pbn_detector", feature_pbn_detector),
            ("revenue_sim", feature_revenue_sim),
            ("dead_equity", feature_dead_equity),
            ("negative_seo", feature_negative_seo),
            ("github_citations", feature_github_citations),
            ("transcription", feature_transcription),
            ("kg_arbitrage", feature_kg_arbitrage),
            ("data_pr", feature_data_pr),
            ("simulation", feature_simulation),
            ("satellite", feature_satellite),
            ("rag_defense", feature_rag_defense),
            ("visual_audit", feature_visual_audit),
            ("apn_proxy", feature_apn_proxy),
            ("graph_decay", feature_graph_decay),
            ("c2pa", feature_c2pa),
            ("compliance_guard", feature_compliance_guard),
            ("geo_crawl", feature_geo_crawl),
            ("zero_party", feature_zero_party),
            ("passage_scoring", feature_passage_scoring),
            ("reddit_consensus", feature_reddit_consensus),
            ("competitor_bert", feature_competitor_bert),
            ("schema_auditor", feature_schema_auditor),
            ("anchor_entropy", feature_anchor_entropy),
            ("crawl_priority", feature_crawl_priority),
            ("ftc_compliance", feature_ftc_compliance),
            ("hreflang", feature_hreflang),
        ]

        features = ddg_features + instant_features

        MODULE_LABELS = {
            "llm_perception": "LLM Co-Mention & Perception Auditing",
            "pr_hooks": "Predictive Digital PR & Trend Hook Engine",
            "unlinked_citations": "Unlinked Citation & Co-Occurrence Converter",
            "link_poisoning": "Algorithmic Link Poisoning & Anomaly Radar",
            "podcast_video": "Podcast & Video Citation Finder",
            "vector_mapping": "Vector Co-Location & Embedding Mapping",
            "rag_repair": "RAG Hallucination & Citation Repair",
            "consensus": "Third-Party Consensus Engine",
            "aeo": "Agentic Commerce Protocol Placement (GEO/AEO)",
            "pbn_detector": "Synthetic Network & Footprint De-Anonymizer",
            "revenue_sim": "Share-of-Search Revenue Simulator",
            "dead_equity": "Edge-Redirect & Dead-Equity Salvage",
            "negative_seo": "Negative SEO Counter-Measure Deployment",
            "github_citations": "GitHub Citation Harvester",
            "transcription": "Audio & Video Semantic Transcription Monitor",
            "kg_arbitrage": "Knowledge Graph & Wikidata Triple Arbitrage",
            "data_pr": "Anonymized Telemetry Data-PR Engine",
            "simulation": "Multi-Agent Off-Page Simulation Sandbox",
            "satellite": "Satellite Entity M&A & Partnership Radar",
            "rag_defense": "Reverse RAG-Cache Poisoning Defense",
            "visual_audit": "Multi-Modal Schema & Visual Graph Alignment",
            "apn_proxy": "Agentic Protocol Negotiation (APN) Proxy",
            "graph_decay": "Co-Citation Graph Decay & Anchor Leasing",
            "c2pa": "Cryptographic Entity-Origin Proof Signing",
            "compliance_guard": "Legal / SEC Disclosure Risk Profiling",
            "geo_crawl": "Geo-IP Citation Localization",
            "zero_party": "Zero-Party Data Exchange",
            "passage_scoring": "Passage-Level BERT Evaluator",
            "reddit_consensus": "Reddit & Forum Consensus Graph",
            "competitor_bert": "Competitor BERT-Vector Extraction",
            "schema_auditor": "Agentic API & Schema Protocol Auditor",
            "anchor_entropy": "Anchor-Text Entropy Boundary Predictor",
            "crawl_priority": "AI Crawler Re-Indexation Pinger",
            "ftc_compliance": "FTC & Sponsored-Mention Penalty Shield",
            "hreflang": "Cross-Border Hreflang Equity Balancer",
        }

        import time as _time

        async def run_feature(key, func):
            from backend.modules.base import breaker_allows, breaker_record
            _mstart = _time.time()
            _timeout = MODULE_TIMEOUTS.get(key, MODULE_TIMEOUT_SECS)
            if not breaker_allows(key):
                return key, {"feature_name": key, "status": "unavailable", "data_status": "unavailable",
                         "requires": "Live data source", "verified": False, "score": None,
                         "assessment": "circuit_open",
                         "recommendation": f"{MODULE_LABELS.get(key, key)} skipped: circuit open after 3 consecutive failures (5-min cooldown).",
                         "detailed_analysis": "Registry circuit-breaker open. No live call attempted; no data fabricated.",
                         "runtime_secs": 0.0}
            for _attempt in range(2):  # 1 retry with backoff
                try:
                    r = await asyncio.wait_for(func(brand, domain, client, db), timeout=_timeout)
                    r["runtime_secs"] = round(_time.time() - _mstart, 1)
                    r.setdefault("provider", r.get("method") or "free-tier")
                    breaker_record(key, True)
                    return key, r
                except asyncio.TimeoutError:
                    if _attempt == 0:
                        await asyncio.sleep(1)
                        continue
                    r = {"feature_name": key, "status": "unavailable", "data_status": "unavailable",
                         "requires": "Live data source", "verified": False, "score": None,
                         "assessment": "no data",
                         "recommendation": f"{MODULE_LABELS.get(key, key)} exceeded {_timeout}s without returning live data. This is a real-time module; it reported no results rather than fabricating any.",
                         "detailed_analysis": f"No live data was produced within {_timeout}s for \"{MODULE_LABELS.get(key, key)}\". No numbers were fabricated — the module surfaced only what it could fetch in real time.",
                         "runtime_secs": round(_time.time() - _mstart, 1)}
                    return key, r
                except Exception as e:
                    import traceback
                    from backend.modules.base import breaker_record as _br
                    _br(key, False)
                    r = {"error": str(e), "feature_name": key, "traceback": traceback.format_exc(),
                         "assessment": "error", "status": "error", "verified": False,
                         "recommendation": f"Feature encountered an error: {str(e)[:200]}",
                         "detailed_analysis": f"Error occurred during {key} analysis: {str(e)[:500]}.",
                         "runtime_secs": round(_time.time() - _mstart, 1)}
                    return key, r
            r = {"feature_name": key, "status": "unavailable", "data_status": "unavailable",
                 "requires": "Live data source", "verified": False, "score": None,
                 "assessment": "no data",
                 "recommendation": f"{MODULE_LABELS.get(key, key)} did not return live data.",
                 "detailed_analysis": "Retries exhausted; no numbers fabricated.",
                 "runtime_secs": round(_time.time() - _mstart, 1)}
            return key, r

        _run_start = _time.time()
        done_count = 0
        total = len(features)
        _update_progress(brand_id, status="running", total_modules=total, modules={})

        BATCH_SIZE = 14
        for i in range(0, len(features), BATCH_SIZE):
            batch = features[i:i + BATCH_SIZE]
            batch_keys = [key for key, _func in batch]
            for key in batch_keys:
                mods = dict(_progress.get(brand_id, {}).get("modules", {}))
                mods[key] = {"status": "active", "runtime_secs": 0, "label": MODULE_LABELS.get(key, key)}
                _update_progress(brand_id, modules=mods)
            _update_progress(brand_id, current_module=batch[0][0], current_module_label=MODULE_LABELS.get(batch[0][0], batch[0][0]), module_index=done_count)
            tasks = [run_feature(key, func) for key, func in batch]
            batch_results = await asyncio.gather(*tasks)
            for key, result in batch_results:
                results["sections"][key] = result
                mods = dict(_progress.get(brand_id, {}).get("modules", {}))
                mods[key] = {"status": "done" if "error" not in result else "error",
                             "runtime_secs": result.get("runtime_secs"), "label": MODULE_LABELS.get(key, key)}
                _update_progress(brand_id, modules=mods)
            done_count += len(batch)
            elapsed = _time.time() - _run_start
            per_done = elapsed / done_count if done_count else 0
            eta = per_done * (total - done_count)
            _update_progress(brand_id, current_module=batch[0][0], current_module_label=MODULE_LABELS.get(batch[0][0], batch[0][0]),
                             module_index=done_count, elapsed_secs=round(elapsed, 1), eta_secs=round(eta, 1),
                             avg_per_module_secs=round(per_done, 1))
            if i + BATCH_SIZE < len(features):
                await asyncio.sleep(0.1)

        _update_progress(brand_id, status="completed", module_index=total, elapsed_secs=round(_time.time() - _run_start, 1),
                         eta_secs=0, current_module="", current_module_label="")

    results["completed_at"] = _now_utc()

    # ---- Enrich each section: verified sources, key findings, actions ----
    brand_name = results.get("brand", "")
    brand_domain = results.get("domain", "")
    brand_category = results.get("category", "technology")
    for key, section in results["sections"].items():
        if not isinstance(section, dict):
            continue

        # 1. Collect every real URL surfaced by the module, keeping only
        #    sources relevant to THIS brand.
        src_seen, raw_urls = set(), []

        def _collect(v):
            if isinstance(v, str):
                if v.startswith("http") and v not in src_seen:
                    src_seen.add(v)
                    raw_urls.append(v)
            elif isinstance(v, list):
                for it in v:
                    _collect(it)
            elif isinstance(v, dict):
                for kk, vv in v.items():
                    if kk in ("url", "href", "link", "wikipedia_url", "profile_url", "source_url") and isinstance(vv, str) and vv.startswith("http") and vv not in src_seen:
                        src_seen.add(vv)
                        raw_urls.append(vv)
                    else:
                        _collect(vv)

        _collect(section)
        cleaned = [normalize_search_url(u) for u in raw_urls if _source_keepable(normalize_search_url(u), brand_name, brand_domain, brand_category)]
        verified_srcs = []
        for u in dict.fromkeys(cleaned):
            low = u.lower()
            url_proven = (brand_domain and brand_domain in low) or (_brand_tokens(brand_name) and any(t in low for t in _brand_tokens(brand_name)))
            if url_proven or _title_matches(u, brand_name, brand_category):
                verified_srcs.append(u)
        if len(verified_srcs) < 2 and section.get("status") != "unavailable":
            try:
                fallback_queries = [f'"{brand_name}"', f'"{brand_name}" {brand_category}', f'site:{brand_domain}']
                for q in fallback_queries[:1]:
                    res = await search_web(q, brand_name=brand_name, num=6)
                    if not is_verified(res):
                        continue
                    for r in res.value:
                        u = normalize_search_url(r.get("url", ""))
                        if not u or u in src_seen or not u.startswith("http"):
                            continue
                        low = u.lower()
                        url_proven = (brand_domain and brand_domain in low) or (_brand_tokens(brand_name) and any(t in low for t in _brand_tokens(brand_name)))
                        if url_proven or _title_matches(u, brand_name, brand_category):
                            verified_srcs.append(u)
                            src_seen.add(u)
            except Exception:
                pass
        section["sources"] = [{"url": u, "domain": extract_domain(u)} for u in verified_srcs[:20]]

        # 2. Key findings: every measured number + counted list signals (up to 12).
        #    Nothing is graded on invented thresholds — values are reported raw.
        _SKIP_KEYS = {"runtime_secs", "total_queries_tested", "simulation_runs",
                      "module_index", "brand_id", "total_modules"}
        findings = []
        numeric_fields = [(k, v) for k, v in section.items()
                          if isinstance(v, (int, float)) and not isinstance(v, bool)
                          and k not in _SKIP_KEYS]
        for k, v in numeric_fields[:12]:
            label = k.replace("_", " ").title()
            pct = isinstance(v, float) or ("rate" in k or "score" in k or "coverage" in k or "health" in k
                                           or "entropy" in k or "share" in k or "similarity" in k or "sentiment" in k)
            unit = "%" if pct and abs(v) <= 100 else ""
            findings.append({"metric": label, "value": f"{round(v, 2)}{unit}"})
        # Counted list signals (e.g. hooks, opportunities, references surfaced).
        for k, v in section.items():
            if len(findings) >= 12:
                break
            if isinstance(v, list) and k not in _SKIP_KEYS and not k.startswith("_"):
                label = k.replace("_", " ").title()
                findings.append({"metric": f"{label} (count)", "value": str(len(v))})
        if not findings:
            findings.append({"metric": "Module status", "value": str(section.get("assessment", "analyzed")).title()})
        section["findings"] = findings

        # 2b. Evidence table: each finding + what it literally means. Directional
        #     language is used ONLY where semantics are certain (zero-count =
        #     none detected in the live window). No invented benchmarks.
        def _reading(metric_key: str, raw_value) -> str:
            mk = metric_key.lower()
            if section.get("status") == "unavailable":
                return "Not measurable — live source unavailable (see requires field)."
            if isinstance(raw_value, (int, float)) and raw_value == 0 and any(
                    w in mk for w in ("toxic", "suspicious", "broken", "error", "risk", "penalt")):
                return "Zero instances detected in the live window — nothing flagged."
            if "count" in mk and isinstance(raw_value, str) and raw_value.strip() == "0":
                return "No live instances surfaced in this run's search window."
            return "Observed live at retrieval time (see retrieved_at) — raw measured value, not modeled."

        evidence = []
        for k, v in numeric_fields[:12]:
            if isinstance(v, bool):
                continue
            evidence.append({"signal": k.replace("_", " ").title(),
                             "observed": round(v, 3) if isinstance(v, float) else v,
                             "reading": _reading(k, v)})
        section["evidence_table"] = evidence[:12]

        # 2c. Limitations derived from this section's own real conditions.
        limitations: list[str] = []
        if section.get("status") == "unavailable":
            limitations.append(f"Blocked: {section.get('requires', 'live source not configured')}.")
            if section.get("reason"):
                limitations.append(str(section.get("reason"))[:220])
        else:
            nsrc = len(section.get("sources") or [])
            if nsrc < 3:
                limitations.append(
                    f"Thin source window ({nsrc} verified URLs) — treat as directional; "
                    "re-run to widen coverage before acting.")
            method_tag_lim = str(section.get("method") or "")
            if ("bing" in method_tag_lim or "duckduckgo" in method_tag_lim or "ddgs" in method_tag_lim) \
                    and "serpapi" not in method_tag_lim:
                limitations.append(
                    "Free-tier search depth (no SERP API key): result counts are floor "
                    "observations, not exhaustive crawls.")
            nulls = [k for k in ("avg_sentiment", "citation_rate", "revenue_projection")
                     if k in section and section[k] is None]
            if nulls:
                limitations.append(
                    f"Not measurable without an LLM provider key: {', '.join(nulls)}. "
                    "Reported as null, never estimated.")
            try:
                if float(section.get("runtime_secs") or 0) > 60:
                    limitations.append("Long runtime reflects live-web latency, not cached data.")
            except Exception:
                pass
        section["limitations"] = limitations

        # 2d. Deterministic confidence from observable coverage (formula disclosed
        #     in methodology; no hidden scoring).
        if section.get("status") in ("unavailable", "error"):
            confidence = 0.0
        else:
            confidence = 0.6
            nsrc_c = len(section.get("sources") or [])
            if nsrc_c >= 2:
                confidence += 0.1
            if nsrc_c >= 5:
                confidence += 0.1
            if any(p in str(section.get("method") or "") for p in ("serpapi", "ahrefs", "wikidata", "rdap")):
                confidence += 0.05
            confidence = round(min(confidence, 0.95), 2)
        section["confidence"] = confidence

        # 3. Prioritized next steps (P1 = do first) + backward-compatible actions.
        rec = section.get("recommendation")
        steps: list[str] = []
        if isinstance(rec, str) and rec:
            steps = [s.strip() for s in rec.split(".") if len(s.strip()) > 25][:8]
            if not steps:
                steps = [rec.strip()[:300]]
        next_steps = []
        if section.get("status") == "unavailable" and section.get("requires"):
            next_steps.append({"step": f"Configure {section.get('requires')} to unlock this module "
                                       "with live data (until then it stays honestly unavailable).",
                               "priority": "P1"})
        for i, s in enumerate(steps):
            prio = "P1" if i < 2 else ("P2" if i < 5 else "P3")
            next_steps.append({"step": s, "priority": prio})
        section["next_steps"] = next_steps[:9]
        section["actions"] = steps[:8]

        # 3b. Executive takeaway: plain-language verdict built ONLY from measured fields.
        fname = str(section.get("feature_name") or key)
        method_tag = str(section.get("method") or "live_signal_collection")
        rt = section.get("retrieved_at") or results.get("completed_at", "")
        rts = section.get("runtime_secs", "?")
        nsrc_t = len(section.get("sources") or [])
        if section.get("status") == "unavailable":
            section["executive_takeaway"] = (
                f"{fname} for {brand_name} could not run ({section.get('requires', 'no live source')}). "
                f"No numbers were fabricated — {str(section.get('reason') or section.get('detailed_analysis') or 'source unavailable')[:200]}"
            )
        elif section.get("status") == "error":
            section["executive_takeaway"] = (
                f"{fname} for {brand_name} errored during the live run "
                f"({str(section.get('error', 'unknown error'))[:160]}). Re-run to retry; "
                "nothing was estimated in its place.")
        else:
            top = ""
            if findings:
                top = f" Headline measurement: {findings[0].get('metric')} = {findings[0].get('value')}."
            section["executive_takeaway"] = (
                f"{fname} for {brand_name}: {section.get('assessment', 'analyzed')}. "
                f"Measured live in {rts}s via {method_tag.replace('_', ' ')} "
                f"({nsrc_t} verified sources, retrieved {rt}).{top} "
                f"Confidence {confidence} (coverage-based, see methodology)."
            )

        # 4. Full methodology: collection + verification + confidence formula + limits.
        meas = []
        for item in (section.get("findings", []) or [])[:6]:
            if isinstance(item, dict):
                meas.append(f"{item.get('metric', 'metric')}={item.get('value', 'n/a')}")
        meas_txt = "; ".join(meas) or "no numeric metric measured"
        lim_txt = " ".join(limitations) if limitations else "No blocking limitations observed in this run."
        section["methodology"] = (
            f"{fname}: (1) Collection — live signals for {brand_name} gathered in real time via "
            f"{method_tag.replace('_', ' ')} at {rt} (runtime {rts}s). Measured: {meas_txt}. "
            f"(2) Verification — every reported URL passed brand-relevance gating and is listed under "
            f"sources ({nsrc_t} verified); modules lacking a live source report 'unavailable' instead of "
            f"fabricating numbers. (3) Confidence {confidence} = base 0.6 +0.1 (2+ sources) +0.1 (5+ sources) "
            f"+0.05 (premium provider), capped 0.95; 0.0 when unavailable/error. "
            f"(4) Limitations — {lim_txt}"
        )

    results["status"] = "completed"
    sections = results["sections"]

    # ---- v2026.3 governance enforcement (risk slider actually blocks tactics) ----
    try:
        from backend.services.governance import risk_config_for, gate_tactics, anchor_warnings, filter_outreach
        from backend.services.brand_config import brand_config_for as _bcf_gov
        _bcfg = _bcf_gov(brand_id)
        _gov = risk_config_for({"governance": {
            "risk_score": (_bcfg.get("risk_score", 30) if isinstance(_bcfg, dict) else 30),
            "max_outreach_per_day": (_bcfg.get("max_outreach_per_day", 10) if isinstance(_bcfg, dict) else 10),
            "blocked_domains": (_bcfg.get("blocked_domains", []) if isinstance(_bcfg, dict) else []),
            "blocked_topics": (_bcfg.get("blocked_topics", []) if isinstance(_bcfg, dict) else []),
        }})
        _tactics = ["expired_domain", "pbn", "guest_post", "digital_pr", "unlinked_outreach",
                    "podcast_pitch", "data_study"]
        _gate = gate_tactics(_tactics, _gov["risk_score"])
        _anchor_sec = sections.get("anchor_entropy", {}) if isinstance(sections.get("anchor_entropy"), dict) else {}
        _warns = anchor_warnings(float(_anchor_sec.get("commercial_ratio", 0) or 0),
                                 float(_anchor_sec.get("top_domain_share", 0) or 0))
        # Filter PR outreach drafts pre-send
        _pr_sec = sections.get("pr_hooks", {})
        if isinstance(_pr_sec, dict) and isinstance(_pr_sec.get("hooks"), list):
            try:
                _pr_sec["hooks"] = filter_outreach(
                    [{"outlet": h.get("target_outlet", ""), "topic": h.get("hook", ""), **h}
                     for h in _pr_sec["hooks"]], _gov)[:20]
            except Exception:
                pass
        results["governance"] = {"config": _gov, "tactic_gate": _gate,
                                 "anchor_warnings": _warns,
                                 "policy": "risk<40 blocks expired/PBN/paid; outreach capped + blocked domains/topics enforced."}
    except Exception as _e:
        results["governance"] = {"status": "error", "reason": str(_e)[:200]}

    # ---- Composite score: average ONLY the metrics that were actually measured ----
    def _num(section, key):
        if not isinstance(section, dict):
            return None
        if section.get("status") == "unavailable":
            return None
        v = section.get(key)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    score_parts = [v for v in [
        _num(sections.get("llm_perception"), "citation_rate"),
        _num(sections.get("unlinked_citations"), "conversion_rate"),
        _num(sections.get("link_poisoning"), "health_score"),
        _num(sections.get("consensus"), "avg_sentiment"),
        _num(sections.get("aeo"), "aeo_score"),
        _num(sections.get("revenue_sim"), "share_of_search_branded_query"),
        _num(sections.get("anchor_entropy"), "normalized_entropy"),
        _num(sections.get("kg_arbitrage"), "triple_coverage_pct"),
        _num(sections.get("schema_auditor"), "schema_score"),
        _num(sections.get("crawl_priority"), "crawl_priority_score"),
    ] if v is not None]
    overall_score = round(sum(score_parts) / len(score_parts), 1) if score_parts else None

    def _val(key, metric, default=None):
        s = sections.get(key, {})
        if not isinstance(s, dict) or s.get("status") == "unavailable":
            return default
        return s.get(metric, default)

    # Grade + coverage transparency (2026-09 fix: grade was always null and
    # scores with different denominators looked comparable when they are not).
    def _grade(score):
        if score is None:
            return None
        if score >= 80:
            return "A"
        if score >= 65:
            return "B"
        if score >= 50:
            return "C"
        if score >= 35:
            return "D"
        return "F"

    _n_ok = len([s for s in sections.values() if isinstance(s, dict) and s.get("status") == "ok"])
    _n_un = len([s for s in sections.values() if isinstance(s, dict) and s.get("status") == "unavailable"])
    _n_er = len([s for s in sections.values() if isinstance(s, dict) and s.get("status") == "error"])
    # ---- v2026.3 Entity Authority (replaces DA-clone hero) + explainable vector + proxy SoV ----
    try:
        from backend.services.entity_authority import compute_entity_authority
        from backend.services.vector_explain import vector_index as _vi
        _kg = _val("kg_arbitrage", "triple_coverage_pct")
        _kg01 = (_kg / 100.0) if isinstance(_kg, (int, float)) else None
        _aeo = _val("aeo", "aeo_score")
        _aeo01 = (_aeo / 100.0) if isinstance(_aeo, (int, float)) and _aeo <= 100 else (_aeo if isinstance(_aeo, (int, float)) else None)
        _cit = _val("llm_perception", "citation_rate")
        _vec = _val("vector_mapping", "avg_cosine_similarity")
        _sameas = None
        try:
            _sameas_n = len(((sections.get("kg_arbitrage", {}) or {}).get("sameas") or []))
            _sameas = min(1.0, _sameas_n / 5.0) if _sameas_n else None
        except Exception:
            pass
        _entity = compute_entity_authority({"kg_coverage": _kg01, "sameas": _sameas,
                                            "citation_rate": _cit, "aeo": _aeo01, "vector": _vec})
        try:
            _vec_expl = _vi(str((_val("vector_mapping", "brand_corpus") or brand_name))[:2000],
                            str((_val("vector_mapping", "seed_corpus") or brand_category))[:2000],
                            [c.get("name") for c in ((_bcfg.get("competitors", []) or []) if isinstance(_bcfg, dict) else []) if isinstance(c, dict)][:4])
        except Exception:
            _vec_expl = {"index_0_100": results["summary"].get("topical_vector_distance_index") if "summary" in results else None}
    except Exception:
        _entity, _vec_expl = {"entity_authority_0_100": overall_score, "grade": _grade(overall_score),
                              "verdict": "Fallback: legacy composite (entity inputs unavailable).",
                              "formula": "fallback", "inputs_used": {}, "inputs_missing": ["all"]}, {}
    results["summary"] = {
        "overall_score": overall_score,
        # v2026.3: hero metric renamed — Entity Authority with sub-scores, not a DA clone.
        "entity_authority": _entity.get("entity_authority_0_100"),
        "entity_grade": _entity.get("grade"),
        "entity_verdict": _entity.get("verdict"),
        "entity_inputs": _entity.get("inputs_used"),
        "entity_missing": _entity.get("inputs_missing"),
        "vector_explain": _vec_expl,
        "grade": _grade(overall_score),
        # Fixed 10-metric denominator so scores stay comparable: null metrics
        # are excluded from the average but counted here for transparency.
        "score_metrics_used": len(score_parts),
        "score_metrics_total": 10,
        "score_coverage_note": (
            f"Average of {len(score_parts)}/10 fixed score metrics actually measured. "
            f"Unmeasured metrics contribute nothing (never zero-filled or fabricated)."
        ),
        "total_mentions": _val("unlinked_citations", "total_mentions_found"),
        "unlinked_opportunities": _val("unlinked_citations", "unlinked_count"),
        "backlink_health": _val("link_poisoning", "health_score"),
        "toxic_backlinks": _val("link_poisoning", "toxic_count"),
        "rag_citation_rate": _val("llm_perception", "citation_rate"),
        "kg_coverage": _val("kg_arbitrage", "triple_coverage_pct"),
        "vector_similarity": _val("vector_mapping", "avg_cosine_similarity"),
        "sentiment": _val("consensus", "avg_sentiment"),
        "pbn_risk": _val("pbn_detector", "suspicious_count"),
        "anchor_entropy": _val("anchor_entropy", "normalized_entropy"),
        "llm_citation_rate": _val("llm_perception", "citation_rate"),
        "aeo_score": _val("aeo", "aeo_score"),
        "share_of_search": _val("revenue_sim", "share_of_search_branded_query"),
        "pr_hooks_generated": _val("pr_hooks", "hook_count"),
        "podcast_opportunities": _val("podcast_video", "opportunity_count"),
        "github_references": _val("github_citations", "github_references"),
        # ---- Output 1 (Boardroom) depth: Topical Vector Distance Index 0-100 ----
        # Converts avg competitor cosine similarity into a spatial authority score:
        # 100 = maximally co-located with market seed nodes, 0 = isolated.
        # Null-safe: None when vector_mapping is unavailable (never zero-filled).
        "topical_vector_distance_index": (
            round(_val("vector_mapping", "avg_cosine_similarity") * 100, 1)
            if isinstance(_val("vector_mapping", "avg_cosine_similarity"), (int, float)) else None
        ),
        # ---- Output 1 (Boardroom) depth: LLM Citation Share-of-Voice matrix ----
        # Brand citation rate vs each tracked competitor from live LLM answers.
        # v2026.3: free proxy_sov_free always computed alongside keyed matrix.
        "llm_citation_sov": (
            {"brand": _val("llm_perception", "citation_rate"),
             "note": "Brand citation rate across live LLM answers; competitor comparison "
                     "requires per-competitor LLM polling (enable OPENAI/PERPLEXITY key)."}
            if _val("llm_perception", "citation_rate") is not None else None
        ),
        "proxy_sov_free": None,  # filled by extended modules below (real searches, labeled proxy)
        "features_analyzed": len(features),
        "modules_unavailable": _n_un,
        "modules_ok": _n_ok,
        "modules_error": _n_er,
        "confidence_avg": (
            round(sum(s.get("confidence", 0) for s in sections.values()
                      if isinstance(s, dict) and s.get("status") == "ok")
                  / max(len([s for s in sections.values()
                             if isinstance(s, dict) and s.get("status") == "ok"]), 1), 3)
        ),
        "generated_at": results.get("completed_at"),
        "engine": settings.APP_VERSION,
        "realtime_note": "Live on-demand audit: every metric was collected live during this run (see per-module retrieved_at). "
                         "Search-result disk cache is 7-day TTL for provider reliability; re-run refreshes stale legs. "
                         "Continuously-monitored tracking requires SCHEDULE_ENABLED=true re-runs. "
                         "Nothing is cached long-term or projected except explicitly labeled projections.",
    }

    # ---- v2026.3 extended modules 36-42 (best-effort, never fail the core 35) ----
    try:
        from backend.modules.extended import EXTENDED as _EXT
        from backend.services.brand_config import brand_config_for as _bcf
        _bcfg2 = _bcf(brand_id)
        for _fn in _EXT:
            try:
                _mod = await asyncio.wait_for(_fn(brand_id, _bcfg2 or {}), timeout=75)
                _k = _mod.get("key", _fn.__name__)
                # store under sections so Appendix A + progress stay uniform
                results["sections"][_k] = _mod
                if _k == "proxy_sov" and _mod.get("status") == "ok":
                    results["summary"]["proxy_sov_free"] = _mod.get("metrics")
            except Exception:
                continue
        _n_ok2 = len([s for s in sections.values() if isinstance(s, dict) and s.get("status") == "ok"])
        results["summary"]["features_analyzed"] = len(results["sections"])
        results["summary"]["modules_ok"] = _n_ok2
        results["summary"]["extended_modules"] = 7
    except Exception:
        pass

    os.makedirs("data/analysis_results", exist_ok=True)
    _latest = f"data/analysis_results/{brand_id}_latest.json"
    # v2026.3 run-over-run snapshots: archive previous latest before overwrite (cap 10).
    try:
        if os.path.exists(_latest):
            import shutil as _sh
            _snap_dir = f"data/run_snapshots/{brand_id}"
            os.makedirs(_snap_dir, exist_ok=True)
            _stamp = (results.get("completed_at") or _now_utc()).replace(":", "-")
            _sh.copy(_latest, os.path.join(_snap_dir, f"{_stamp}.json"))
            _snaps = sorted(os.listdir(_snap_dir))
            for _old in _snaps[:-10]:
                try:
                    os.remove(os.path.join(_snap_dir, _old))
                except Exception:
                    pass
    except Exception:
        pass
    with open(_latest, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str, ensure_ascii=True)

    # v2026.3 regression alerts: KG drop / error spike vs previous snapshot -> webhooks.
    try:
        from backend.api.multi_brand import fire_alerts as _fire
        _summ = results.get("summary", {}) if isinstance(results.get("summary"), dict) else {}
        _regs = []
        try:
            _snap_dir = f"data/run_snapshots/{brand_id}"
            if os.path.isdir(_snap_dir) and sorted(os.listdir(_snap_dir)):
                _prev = json.load(open(os.path.join(_snap_dir, sorted(os.listdir(_snap_dir))[-1]),
                                       encoding="utf-8", errors="replace"))
                _ps = _prev.get("summary", {}) if isinstance(_prev.get("summary"), dict) else {}
                if isinstance(_ps.get("kg_coverage"), (int, float)) and isinstance(_summ.get("kg_coverage"), (int, float)):
                    if _summ["kg_coverage"] < _ps["kg_coverage"] - 10:
                        _regs.append(f"KG coverage regression {_ps['kg_coverage']} -> {_summ['kg_coverage']}")
                if isinstance(_ps.get("modules_error"), int) and isinstance(_summ.get("modules_error"), int):
                    if _summ["modules_error"] > _ps["modules_error"]:
                        _regs.append(f"module errors up {_ps['modules_error']} -> {_summ['modules_error']}")
        except Exception:
            pass
        await _fire(brand_id, {"overall_score": _summ.get("overall_score"),
                               "entity_authority": _summ.get("entity_authority"),
                               "regressions": _regs})
    except Exception:
        pass

    return results


@router.post("/run")
async def run_analysis(req: AnalysisRequest, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == req.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    results = await run_full_analysis(req.brand_id, db)
    if "error" in results:
        raise HTTPException(status_code=400, detail=results["error"])
    return results


# ---- Non-blocking background jobs (fixes blocking POST /run) ----
# run-async returns immediately with job_id; poll /progress/{brand_id} or /job/{job_id}.
# Uses asyncio tasks (no Redis required). For multi-worker scale, plug Celery/Redis here.
_jobs: dict[str, dict] = {}


def _job_id_for(brand_id: int) -> str:
    import uuid
    return f"{brand_id}-{uuid.uuid4().hex[:8]}"


async def _run_job(job_id: str, brand_id: int):
    from backend.core.database import SessionLocal
    _jobs[job_id] = {"job_id": job_id, "brand_id": brand_id, "status": "running",
                     "started_at": _now_utc(), "error": None}
    db = SessionLocal()
    try:
        results = await run_full_analysis(brand_id, db)
        _jobs[job_id].update({"status": "completed", "completed_at": _now_utc(),
                              "overall_score": (results.get("summary") or {}).get("overall_score")})
    except Exception as e:  # noqa: BLE001
        _jobs[job_id].update({"status": "failed", "completed_at": _now_utc(), "error": str(e)[:500]})
        try:
            _update_progress(brand_id, status="failed")
        except Exception:
            pass
    finally:
        try:
            db.close()
        except Exception:
            pass


@router.post("/run-async")
async def run_analysis_async(req: AnalysisRequest, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == req.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    job_id = _job_id_for(req.brand_id)
    _update_progress(req.brand_id, status="queued", current_module="queued",
                     current_module_label="Queued — background worker starting")
    asyncio.create_task(_run_job(job_id, req.brand_id))
    return {"job_id": job_id, "brand_id": req.brand_id, "status": "queued",
            "poll": f"/api/v1/analysis/progress/{req.brand_id}", "job": f"/api/v1/analysis/job/{job_id}"}


@router.get("/job/{job_id}")
def get_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/provider-status")
def get_provider_status():
    """Which providers are configured (booleans only — never leaks secrets)."""
    try:
        from backend.services.providers import provider_status
        from config.settings import settings as _s
        status = provider_status()
        return {"providers": status,
                "configured": _s.configured_providers,
                "strict_single_token": bool(getattr(_s, "STRICT_SINGLE_TOKEN_BRANDS", True)),
                "retrieved_at": _now_utc()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)[:300])


def _dsec(data: dict, key: str) -> dict:
    s = (data.get("sections") or {}).get(key)
    return s if isinstance(s, dict) else {}


def _dok(s: dict) -> bool:
    return isinstance(s, dict) and s.get("status") == "ok"


def _dsrc(s: dict, n: int = 12) -> list[str]:
    out = []
    for it in (s.get("sources") or [])[:n]:
        u = it.get("url") if isinstance(it, dict) else it
        if isinstance(u, str) and u.startswith("http"):
            out.append(u)
    return out


def _drows(items, *keys, limit: int = 12) -> list[dict]:
    """Project list-of-dicts to plain rows with only real values (drop empties)."""
    rows = []
    for it in (items or [])[:limit]:
        if not isinstance(it, dict):
            continue
        row = {k: it.get(k) for k in keys if it.get(k) not in (None, "", [], {})}
        if row:
            rows.append(row)
    return rows


def build_deliverables(data: dict) -> dict:
    """Compose the 5 Tool Outputs from the latest live analysis (real data only).

    Every number/URL below is copied from measured module fields. Unavailable
    modules surface as explicit no-data blocks with the required key — nothing
    is estimated or invented at this layer either.
    """
    brand = data.get("brand", "")
    domain = data.get("domain", "")
    summary = data.get("summary") or {}
    sec = lambda k: _dsec(data, k)  # noqa: E731

    sim, llm, vec = sec("revenue_sim"), sec("llm_perception"), sec("vector_mapping")
    cons = sec("consensus")
    sov_mode = "llm" if _dok(llm) else ("consensus-fallback" if _dok(cons) else "unavailable")
    avg_cos = vec.get("avg_cosine_similarity")
    vector_index = round(avg_cos * 100, 1) if isinstance(avg_cos, (int, float)) else None

    pr, unl, pod = sec("pr_hooks"), sec("unlinked_citations"), sec("podcast_video")
    dead, neg, gh = sec("dead_equity"), sec("negative_seo"), sec("github_citations")
    broken = dead.get("broken_links") or []
    atom_paths = []
    for b in broken:
        if isinstance(b, dict) and isinstance(b.get("url"), str):
            try:
                from urllib.parse import urlparse as _up
                p = _up(b["url"]).path or "/"
                if p not in atom_paths:
                    atom_paths.append(p)
            except Exception:
                pass
    worker_lines = [f"    '{p}': '/',  // TODO: point at the semantically closest live 2026 URL"
                    for p in atom_paths[:20]]
    worker_script = ("addEventListener('fetch', (e) => {\n  const u = new URL(e.request.url);\n"
                     "  const map = {\n" + ("\n".join(worker_lines) if worker_lines else "    // no broken outbound links found in this run") + "\n  };\n"
                     "  const t = map[u.pathname];\n"
                     "  if (t) return e.respondWith(Response.redirect(new URL(t, u.origin).toString(), 301));\n"
                     "  return e.respondWith(fetch(e.request));\n});")
    anti_headers = (f"# Deploy at the CDN edge on scraped / parameterised URLs for {domain or 'the brand domain'}\n"
                    "X-Robots-Tag: noindex, nofollow\n"
                    f"Link: <https://{domain or 'brand.com'}/>; rel=\"canonical\"")
    gh_attribution = (f"<!-- Attribution for {brand or 'the brand'} ({domain or 'brand domain'}) -->\n"
                      f"[{brand or 'Brand'}](https://{domain or 'brand.com'}) — {str(sec('unlinked_citations').get('executive_takeaway') or data.get('brand', ''))[:160]}\n")
    manifest = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": brand, "url": f"https://{domain}" if domain else "",
        "sameAs": _dsrc(sec("knowledge_graph") if "knowledge_graph" in (data.get("sections") or {}) else sec("kg_arbitrage"), 8),
        "knowsAbout": [k for k in [sec("kg_arbitrage").get("wikidata_label")] if k],
    }

    anchor, ftc, pbn = sec("anchor_entropy"), sec("ftc_compliance"), sec("pbn_detector")
    rag, ragd = sec("rag_repair"), sec("rag_defense")
    rag_mode = "llm" if _dok(rag) else ("cache-fallback" if _dok(ragd) else "unavailable")

    kg, hre, schema, aeo = sec("kg_arbitrage"), sec("hreflang"), sec("schema_auditor"), sec("aeo")
    comp_mon = []
    for c in (kg.get("competitor_monitor") or [])[:5]:
        if isinstance(c, dict):
            comp_mon.append({"name": c.get("name"), "domain": c.get("domain"),
                             "wikidata_id": c.get("wikidata_id"),
                             "triples_present": len(c.get("present_triples") or {}) if isinstance(c.get("present_triples"), dict) else c.get("present_triples")})

    return {
        "brand": brand, "domain": domain,
        "generated_at": data.get("completed_at"), "started_at": data.get("started_at"),
        "overall_score": summary.get("overall_score"),
        "modules_ok": summary.get("modules_ok"), "modules_unavailable": summary.get("modules_unavailable"),
        "modules_error": summary.get("modules_error"), "confidence_avg": summary.get("confidence_avg"),
        "outputs": [
            {"id": 1, "title": "The C-Suite Executive Dashboard (Boardroom View)", "blocks": [
                {"title": "Share of Search Revenue Attributor",
                 "takeaway": sim.get("executive_takeaway"), "confidence": sim.get("confidence"),
                 "limitations": sim.get("limitations") or [],
                 "metrics": {"branded_share": sim.get("share_of_search_branded_query"),
                             "category_share": sim.get("share_of_search_category_query"),
                             "revenue_projection": sim.get("revenue_projection"),
                             "revenue_note": sim.get("revenue_projection_note")},
                 "branded_top": _drows(sim.get("branded_results"), "title", "url", limit=5),
                 "category_top": _drows(sim.get("category_results"), "title", "url", limit=5),
                 "sources": _dsrc(sim)},
                {"title": "LLM Citation Share-of-Voice Matrix", "mode": sov_mode,
                 "takeaway": (llm.get("executive_takeaway") if sov_mode == "llm" else cons.get("executive_takeaway")),
                 "confidence": (llm.get("confidence") if sov_mode == "llm" else cons.get("confidence")),
                 "limitations": ((llm.get("limitations") or []) if sov_mode == "llm" else (cons.get("limitations") or [])),
                 "llm": {"citation_rate": llm.get("citation_rate"), "answered": llm.get("answered"),
                         "total_questions": llm.get("total_questions"), "answers": _drows(llm.get("llm_answers"), "question", "model", limit=5)} if sov_mode == "llm" else None,
                 "consensus_fallback": {"overall_sentiment": cons.get("overall_sentiment_score"),
                                        "distribution": cons.get("sentiment_distribution"),
                                        "mentions_count": len(cons.get("mentions") or []),
                                        "sentiment_available": cons.get("sentiment_available")} if sov_mode == "consensus-fallback" else None,
                 "requires": llm.get("requires") if sov_mode == "unavailable" else None,
                 "sources": _dsrc(llm) if sov_mode == "llm" else _dsrc(cons)},
                {"title": "Topical Vector Distance Index (0-100)",
                 "takeaway": vec.get("executive_takeaway"), "confidence": vec.get("confidence"),
                 "limitations": vec.get("limitations") or [],
                 "metrics": {"avg_cosine_similarity": avg_cos, "vector_index_0_100": vector_index,
                             "brand_texts": vec.get("brand_texts_embedded"), "competitors": vec.get("competitors_embedded")},
                 "competitors": [{"competitor": r.get("competitor"),
                                  "cosine": r.get("cosine_similarity"),
                                  "index_0_100": round(r.get("cosine_similarity") * 100, 1) if isinstance(r.get("cosine_similarity"), (int, float)) else None}
                                 for r in (vec.get("competitor_distances") or [])[:6] if isinstance(r, dict)],
                 "sources": _dsrc(vec)}]},
            {"id": 2, "title": "Human-in-the-Loop Action & Outreach Queues", "blocks": [
                {"title": "Predictive PR & Data-Hook Pitches",
                 "takeaway": pr.get("executive_takeaway"), "confidence": pr.get("confidence"),
                 "limitations": pr.get("limitations") or [],
                 "metrics": {"hook_count": pr.get("hook_count"), "articles_scanned": pr.get("total_articles_scanned"),
                             "brand_mentions": pr.get("brand_mentions_in_news")},
                 "hooks": [{"title": h.get("title"), "angle": h.get("angle"), "target_outlet": h.get("target_outlet"),
                            "source_url": h.get("source_url"), "source_articles": (h.get("source_articles") or [])[:5],
                            "verified": h.get("verified")} for h in (pr.get("hooks") or [])[:8] if isinstance(h, dict)],
                 "sources": _dsrc(pr)},
                {"title": "Unlinked Mention & Citation Conversion Deck",
                 "takeaway": unl.get("executive_takeaway"), "confidence": unl.get("confidence"),
                 "limitations": unl.get("limitations") or [],
                 "metrics": {"total_mentions": unl.get("total_mentions_found"), "unlinked": unl.get("unlinked_count"),
                             "examined": unl.get("examined"), "conversion_rate": unl.get("conversion_rate")},
                 "unlinked_items": [{"url": m.get("url"), "title": m.get("title"), "domain": m.get("domain"),
                                     "snippet": (m.get("snippet") or "")[:220], "relevance": m.get("relevance_score")}
                                    for m in (unl.get("mentions") or []) if isinstance(m, dict) and m.get("links_to_brand") is False][:10],
                 "sources": _dsrc(unl)},
                {"title": "Podcast & Video Transcript Pitch Packs",
                 "takeaway": pod.get("executive_takeaway"), "confidence": pod.get("confidence"),
                 "limitations": pod.get("limitations") or [],
                 "metrics": {"opportunities": pod.get("opportunity_count"), "platforms": pod.get("platforms"),
                             "unique_platforms": pod.get("unique_platforms")},
                 "items": _drows(pod.get("mentions"), "url", "title", "domain", "snippet", limit=10),
                 "sources": _dsrc(pod)}]},
            {"id": 3, "title": "Edge-Network & Technical Execution Rules", "blocks": [
                {"title": "Serverless Edge Redirect Payloads",
                 "takeaway": dead.get("executive_takeaway"), "confidence": dead.get("confidence"),
                 "limitations": dead.get("limitations") or [],
                 "metrics": {"broken": dead.get("broken_count"), "healthy": dead.get("healthy_count"),
                             "redirects": dead.get("redirect_count"), "checked": dead.get("outbound_links_checked")},
                 "broken_links": _drows(dead.get("broken_links"), "url", "text", "status", limit=10),
                 "redirected_links": _drows(dead.get("redirected_links"), "url", "final_url", "status", limit=10),
                 "worker_script": worker_script,
                 "worker_note": "Generated from the REAL broken paths above. Replace each '/' target with the semantically closest live URL before deploying to Cloudflare Workers / Fastly VCL.",
                 "sources": _dsrc(dead)},
                {"title": "Active Anti-Scrape & Canonical Shield Headers",
                 "takeaway": neg.get("executive_takeaway"), "confidence": neg.get("confidence"),
                 "limitations": neg.get("limitations") or [],
                 "metrics": {"negative_mentions": neg.get("negative_mention_count"), "risk_terms": neg.get("risk_terms")},
                 "sample_mentions": _drows(neg.get("negative_mentions"), "url", "title", limit=6),
                 "headers_snippet": anti_headers,
                 "sources": _dsrc(neg)},
                {"title": "Developer Ecosystem Pull-Requests",
                 "takeaway": gh.get("executive_takeaway"), "confidence": gh.get("confidence"),
                 "limitations": gh.get("limitations") or [],
                 "metrics": {"github_references": gh.get("github_references")},
                 "items": _drows(gh.get("references"), "url", "title", "domain", "snippet", limit=10),
                 "attribution_markdown": gh_attribution, "jsonld_schema": manifest,
                 "sources": _dsrc(gh)}]},
            {"id": 4, "title": "Algorithmic Defense & Compliance Risk Register", "blocks": [
                {"title": "Neural Anchor Entropy & Over-Optimization Radar",
                 "takeaway": anchor.get("executive_takeaway"), "confidence": anchor.get("confidence"),
                 "limitations": anchor.get("limitations") or [],
                 "metrics": {"entropy": anchor.get("entropy"), "normalized_entropy": anchor.get("normalized_entropy"),
                             "total_anchors": anchor.get("total_anchors"), "unique_anchors": anchor.get("unique_anchors"),
                             "branded_pct": anchor.get("branded_pct")},
                 "top_anchors": _drows(anchor.get("top_anchors"), "anchor", "count", limit=10),
                 "sources": _dsrc(anchor)},
                {"title": "FTC & Sponsored-Link Compliance Alerts",
                 "takeaway": ftc.get("executive_takeaway"), "confidence": ftc.get("confidence"),
                 "limitations": ftc.get("limitations") or [],
                 "metrics": {"sponsored_total": ftc.get("total_sponsored_content"),
                             "issues_total": ftc.get("total_compliance_issues"), "ftc_score": ftc.get("ftc_score")},
                 "sponsored": [{"url": m.get("url"), "title": m.get("title"), "domain": m.get("domain"),
                                "has_disclosure": m.get("has_disclosure")} for m in (ftc.get("sponsored_mentions") or [])[:10] if isinstance(m, dict)],
                 "issues": _drows(ftc.get("compliance_issues"), "url", "title", limit=10),
                 "disclosure_pages": ftc.get("disclosure_pages") or [],
                 "sources": _dsrc(ftc)},
                {"title": "Synthetic Network & PBN Forensic Red-Flags",
                 "takeaway": pbn.get("executive_takeaway"), "confidence": pbn.get("confidence"),
                 "limitations": pbn.get("limitations") or [],
                 "metrics": {"suspicious": pbn.get("suspicious_count"), "backlinks_total": pbn.get("total_backlinks"),
                             "sponsored": pbn.get("sponsored_count"), "ugc": pbn.get("ugc_count"),
                             "generic_anchors": pbn.get("generic_anchor_count")},
                 "registration_footprint": pbn.get("registration_footprint") or {},
                 "repeated_domains": pbn.get("repeated_source_domains") or [],
                 "sources": _dsrc(pbn)},
                {"title": "RAG Hallucination & Cache-Purge Alerts", "mode": rag_mode,
                 "takeaway": (rag.get("executive_takeaway") if rag_mode == "llm" else ragd.get("executive_takeaway")),
                 "confidence": (rag.get("confidence") if rag_mode == "llm" else ragd.get("confidence")),
                 "limitations": ((rag.get("limitations") or []) if rag_mode == "llm" else (ragd.get("limitations") or [])),
                 "cache_fallback": {"freshness_rate": ragd.get("freshness_rate"),
                                    "stale_detected": ragd.get("stale_caches_detected"),
                                    "checked": ragd.get("total_results_checked"),
                                    "indicators": ragd.get("stale_indicators_used"),
                                    "sample_tests": _drows(ragd.get("cache_tests"), "query", "result_count", "stale_count", limit=6)} if rag_mode == "cache-fallback" else None,
                 "requires": rag.get("requires") if rag_mode == "unavailable" else None,
                 "sources": _dsrc(rag) if rag_mode == "llm" else _dsrc(ragd)}]},
            {"id": 5, "title": "Global Entity & Knowledge Graph Blueprint", "blocks": [
                {"title": "Wikidata & Triple Gap Report",
                 "takeaway": kg.get("executive_takeaway"), "confidence": kg.get("confidence"),
                 "limitations": kg.get("limitations") or [],
                 "metrics": {"coverage_pct": kg.get("triple_coverage_pct"), "wikidata_id": kg.get("wikidata_id"),
                             "label": kg.get("wikidata_label"), "sitelinks": kg.get("sitelinks")},
                 "wikipedia": {"url": kg.get("wikipedia_url"), "extract": (kg.get("wikipedia_extract") or "")[:600]},
                 "present_triples": kg.get("present_triples") or {},
                 "missing_triples": _drows(kg.get("missing_triples"), "property", "label", limit=10),
                 "competitor_monitor": comp_mon,
                 "sources": _dsrc(kg)},
                {"title": "Multi-Regional Hreflang Equity Balancer",
                 "takeaway": hre.get("executive_takeaway"), "confidence": hre.get("confidence"),
                 "limitations": hre.get("limitations") or [],
                 "metrics": {"tags": hre.get("hreflang_tags"), "cannibalization_risk": hre.get("cannibalization_risk"),
                             "readiness": hre.get("international_readiness_score")},
                 "versions": hre.get("international_versions") or [], "links": hre.get("international_links") or [],
                 "sources": _dsrc(hre)},
                {"title": "Machine-to-Machine (AEO) Protocol Manifest",
                 "takeaway": aeo.get("executive_takeaway"), "confidence": aeo.get("confidence"),
                 "limitations": aeo.get("limitations") or [],
                 "metrics": {"aeo_score": aeo.get("aeo_score"), "schema_score": schema.get("schema_score"),
                             "jsonld": schema.get("jsonld_count"), "opengraph": schema.get("opengraph_count"),
                             "twitter_cards": schema.get("twitter_card_count")},
                 "probes": {"llms_txt": aeo.get("llms_txt"), "robots_txt": aeo.get("robots_txt"),
                            "sitemap": aeo.get("sitemap"), "ai_plugin_json": aeo.get("ai_plugin_json"),
                            "ai_bot_directives": aeo.get("ai_bot_directives")},
                 "schema_checks": _drows(schema.get("schema_checks"), "type", "schema_type", "count", limit=6),
                 "endpoints": _drows(schema.get("machine_readable_endpoints"), "path", "status", "content_type", limit=8),
                 "manifest": manifest,
                 "sources": _dsrc(aeo) + _dsrc(schema)}]},
        ],
    }


@router.get("/export/{brand_id}")
def export_results(brand_id: int, format: str = "json"):
    """Export latest results as json / csv / pdf (deliverables layer)."""
    import csv
    import io
    path = f"data/analysis_results/{brand_id}_latest.json"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No analysis yet. POST /run first.")
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    fmt = (format or "json").lower()
    if fmt == "json":
        from fastapi.responses import JSONResponse
        return JSONResponse(content=data)
    sections = data.get("sections", {}) or {}
    if fmt == "csv":
        from fastapi.responses import StreamingResponse
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["module", "feature_name", "status", "verified", "confidence", "method", "runtime_secs", "top_finding", "sources_count", "evidence", "sources"])
        for key, s in sorted(sections.items()):
            if not isinstance(s, dict):
                continue
            findings = s.get("findings") or []
            top = ""
            if findings and isinstance(findings[0], dict):
                top = f"{findings[0].get('metric')}: {findings[0].get('value')}"
            srcs = s.get("sources") or []
            src_urls = "; ".join([(x.get("url", "") if isinstance(x, dict) else str(x)) for x in srcs[:5]])
            w.writerow([key, s.get("feature_name", ""), s.get("status", ""), s.get("verified", ""),
                        s.get("confidence", ""), s.get("method", ""), s.get("runtime_secs", ""), top, len(srcs), top, src_urls])
        buf.seek(0)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": f"attachment; filename=brand-{brand_id}-analysis.csv"})
    if fmt == "pdf":
        # Enterprise PDF — fully aligned platypus layout with wrapped Paragraph
        # cells, KPI cover, charts (reportlab graphics), all 5 Tool Outputs and
        # a complete 35-module appendix (features + functions + subfunctions).
        from fastapi.responses import Response as _Resp
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
            from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                            TableStyle, PageBreak, KeepTogether,
                                            HRFlowable, ListFlowable, ListItem, Image)
            from reportlab.graphics.shapes import Drawing, Line, String, Rect
            from reportlab.graphics.charts.piecharts import Pie
            from reportlab.graphics.charts.barcharts import VerticalBarChart
            from reportlab.lib.colors import HexColor
            _HAS_CHARTS = True
        except ImportError:
            raise HTTPException(status_code=500, detail="PDF export requires reportlab (pip install reportlab).")

        # ---------- design tokens ----------
        NAVY = colors.HexColor("#0f2440")
        NAVY2 = colors.HexColor("#1e3a5f")
        ACCENT = colors.HexColor("#0e9fb5")
        INDIGO = colors.HexColor("#4f5df0")
        SLATE = colors.HexColor("#475569")
        LIGHT = colors.HexColor("#f1f5f9")
        BORDER = colors.HexColor("#cbd5e1")
        OK = colors.HexColor("#15803d")
        WARN = colors.HexColor("#b45309")
        ERR = colors.HexColor("#b91c1c")
        OK_BG = colors.HexColor("#dcfce7")
        WARN_BG = colors.HexColor("#fef3c7")
        ERR_BG = colors.HexColor("#fee2e2")
        PAGE_W, PAGE_H = A4
        ML = MR = 14 * mm
        USABLE = PAGE_W - ML - MR  # ~182mm

        import html as _html

        def _tx(v, limit: int = 1200) -> str:
            s = "" if v is None else (v if isinstance(v, str) else str(v))
            s = (s.replace("\u2014", "-").replace("\u2013", "-").replace("\u201c", '"')
                   .replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
                   .replace("\u2026", "...").replace("\u2192", "->").replace("\u00a0", " "))
            s = s.encode("latin-1", "replace").decode("latin-1")
            s = " ".join(s.split())
            return s[:limit]

        def _esc(v, limit: int = 1200) -> str:
            return _html.escape(_tx(v, limit), quote=False)

        styles = getSampleStyleSheet()
        sTitle = ParagraphStyle("ETitle", parent=styles["Title"], fontName="Helvetica-Bold",
                                fontSize=24, leading=28, textColor=NAVY, alignment=TA_LEFT, spaceAfter=2)
        sSubtitle = ParagraphStyle("ESub", parent=styles["Normal"], fontName="Helvetica",
                                   fontSize=9.5, leading=13.5, textColor=SLATE, spaceAfter=0)
        sH1 = ParagraphStyle("EH1", parent=styles["Heading1"], fontName="Helvetica-Bold",
                             fontSize=14, leading=17, textColor=NAVY, spaceBefore=0, spaceAfter=4)
        sH2 = ParagraphStyle("EH2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                             fontSize=11, leading=14, textColor=NAVY2, spaceBefore=8, spaceAfter=4)
        sH3 = ParagraphStyle("EH3", parent=styles["Heading3"], fontName="Helvetica-Bold",
                             fontSize=9.5, leading=12, textColor=NAVY2, spaceBefore=6, spaceAfter=3)
        sBody = ParagraphStyle("EBody", parent=styles["Normal"], fontName="Helvetica",
                               fontSize=8.6, leading=12.4, textColor=colors.HexColor("#1f2937"), alignment=TA_LEFT)
        sSmall = ParagraphStyle("ESmall", parent=styles["Normal"], fontName="Helvetica",
                                fontSize=7.6, leading=10.6, textColor=SLATE)
        sCell = ParagraphStyle("ECell", parent=styles["Normal"], fontName="Helvetica",
                               fontSize=7.8, leading=10.5, textColor=colors.HexColor("#1f2937"))
        sCellH = ParagraphStyle("ECellH", parent=sCell, fontName="Helvetica-Bold",
                                fontSize=7.8, leading=10.5, textColor=colors.white)
        sCellSmall = ParagraphStyle("ECellSm", parent=sCell, fontSize=7.2, leading=9.8)
        sMono = ParagraphStyle("EMono", parent=styles["Code"] if "Code" in styles else styles["Normal"],
                               fontName="Courier", fontSize=6.8, leading=9.2,
                               textColor=colors.HexColor("#0f172a"))
        sCaption = ParagraphStyle("ECap", parent=styles["Normal"], fontName="Helvetica-Oblique",
                                  fontSize=7.4, leading=10, textColor=SLATE, alignment=TA_CENTER)
        sKpiV = ParagraphStyle("EKpiV", parent=styles["Normal"], fontName="Helvetica-Bold",
                               fontSize=15, leading=17, textColor=NAVY, alignment=TA_CENTER)
        sKpiL = ParagraphStyle("EKpiL", parent=styles["Normal"], fontName="Helvetica",
                               fontSize=7.2, leading=9, textColor=SLATE, alignment=TA_CENTER)

        def _P(text, style=sCell):
            return Paragraph(_esc(text) or "-", style)

        def _styled_table(header: list[str], rows: list[list], widths: list,
                          header_bg=NAVY, fontsize_body: float = 7.8) -> "Table | None":
            """All cells are wrapped Paragraphs — this is what guarantees alignment."""
            if not rows:
                return None
            cell_style = ParagraphStyle(f"EB{fontsize_body}", parent=sCell,
                                        fontSize=fontsize_body, leading=fontsize_body + 2.6)
            head = [Paragraph(f"<b>{_esc(h)}</b>", sCellH) for h in header]
            body_rows = []
            for r in rows:
                body_rows.append([Paragraph(_esc(c, 900) or "-", cell_style) for c in r])
            t = Table([head] + body_rows, colWidths=widths, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), header_bg),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            return t

        def _band(text: str, bg=NAVY):
            t = Table([[Paragraph(f"<b>{_esc(text)}</b>",
                                  ParagraphStyle("EBand", parent=sCellH, fontSize=10.5, leading=13))]],
                      colWidths=[USABLE])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("ROUNDEDCORNERS", [4, 4, 4, 4]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            return t

        def _callout(label: str, text: str):
            inner = [
                [Paragraph(f"<b>{_esc(label)}</b>", ParagraphStyle("ECOL", parent=sSmall,
                             fontName="Helvetica-Bold", textColor=NAVY2)),
                 Paragraph(_esc(text, 1500), sBody)],
            ]
            t = Table(inner, colWidths=[26 * mm, USABLE - 26 * mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#93c5fd")),
                ("LINEBELOW", (0, 0), (-1, 0), 0, colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            return t

        def _status_chip(status: str) -> Paragraph:
            s = (status or "unknown").lower()
            bg = OK_BG if s == "ok" else (WARN_BG if s in ("unavailable", "no data", "no-data") else ERR_BG)
            fg = OK if s == "ok" else (WARN if s in ("unavailable", "no data", "no-data") else ERR)
            _ = bg
            label = {"ok": "●  VERIFIED — LIVE", "unavailable": "●  NO DATA — SOURCE MISSING",
                     "error": "●  ERROR — SEE DETAIL"}.get(s, f"●  {s.upper()}")
            return Paragraph(f"<b><font color='{fg.hexval()}'>{_esc(label)}</font></b>", sCell)

        def _fmt(v) -> str:
            if v is None or v == "" or v == [] or v == {}:
                return "-"
            if isinstance(v, bool):
                return "Yes" if v else "No"
            if isinstance(v, float):
                return f"{round(v, 3)}"
            if isinstance(v, (dict, list)):
                return _tx(json.dumps(v, default=str), 220)
            return _tx(v, 220)

        comp = build_deliverables(data)
        summ_all = data.get("summary") or {}
        brand = comp.get("brand") or data.get("brand") or "Brand"
        domain = comp.get("domain") or data.get("domain") or ""
        gen_at = comp.get("generated_at") or data.get("completed_at") or ""
        start_at = comp.get("started_at") or data.get("started_at") or ""
        engine = summ_all.get("engine", "") or "35-module live engine"

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=ML, rightMargin=MR,
                                topMargin=15 * mm, bottomMargin=15 * mm,
                                title=f"Off-Page SEO Intelligence Report - {brand}",
                                author="Complete Off-Page SEO Engine",
                                subject="Enterprise off-page SEO deliverables + full module appendix")
        story: list = []

        def _header_footer(canvas, _doc):
            import os as _os
            _wl = (_os.environ.get("WHITE_LABEL_BRAND") or "OFF-PAGE SEO INTELLIGENCE").strip() or "OFF-PAGE SEO INTELLIGENCE"
            canvas.saveState()
            canvas.setStrokeColor(BORDER)
            canvas.setLineWidth(0.5)
            canvas.line(ML, PAGE_H - 12 * mm, PAGE_W - MR, PAGE_H - 12 * mm)
            canvas.setFont("Helvetica-Bold", 7)
            canvas.setFillColor(NAVY)
            canvas.drawString(ML, PAGE_H - 10 * mm, _tx(f"{_wl}  |  {brand} ({domain})")[:110])
            canvas.setFont("Helvetica", 7)
            canvas.setFillColor(SLATE)
            canvas.drawRightString(PAGE_W - MR, PAGE_H - 10 * mm, _tx(f"{engine}  |  2026")[:60])
            canvas.setFont("Helvetica", 6.5)
            canvas.setFillColor(SLATE)
            canvas.drawString(ML, 10 * mm, _tx(f"Generated {gen_at}  |  Real data only - unavailable = no data, never guessed")[:120])
            canvas.drawRightString(PAGE_W - MR, 10 * mm, f"Page {_doc.page}")
            canvas.restoreState()

        # ================= COVER =================
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph("OFF-PAGE SEO INTELLIGENCE", ParagraphStyle(
            "EKicker", parent=sSmall, fontName="Helvetica-Bold", fontSize=8.5,
            leading=11, textColor=ACCENT)))
        story.append(Paragraph("Enterprise Authority Report", sTitle))
        story.append(Paragraph(f"{_esc(brand)} &nbsp;·&nbsp; {_esc(domain)} &nbsp;·&nbsp; Generated {_esc(gen_at or 'n/a')}", sSubtitle))
        story.append(Spacer(1, 2 * mm))
        story.append(HRFlowable(width="100%", thickness=0.7, color=ACCENT, spaceAfter=4 * mm, spaceBefore=2 * mm))

        ov = summ_all.get("overall_score")
        _secs_pre = data.get("sections") or {}
        _cok = sum(1 for s in _secs_pre.values() if isinstance(s, dict) and s.get("status") == "ok")
        _cun = sum(1 for s in _secs_pre.values() if isinstance(s, dict) and s.get("status") == "unavailable")
        _cer = sum(1 for s in _secs_pre.values() if isinstance(s, dict) and s.get("status") == "error")
        n_ok = comp.get("modules_ok") if comp.get("modules_ok") not in (None, "") else _cok
        n_un = comp.get("modules_unavailable") if comp.get("modules_unavailable") not in (None, "") else _cun
        n_er = comp.get("modules_error") if comp.get("modules_error") not in (None, "") else _cer
        _confs = [s.get("confidence") for s in _secs_pre.values()
                  if isinstance(s, dict) and isinstance(s.get("confidence"), (int, float))]
        conf = comp.get("confidence_avg") if comp.get("confidence_avg") not in (None, "") else (
            round(sum(_confs) / len(_confs), 1) if _confs else None)
        total_mods = len(_secs_pre) or 35
        kpi = [
            [Paragraph(f"<b>{_esc(str(ov) if ov is not None else '-')}</b>", sKpiV),
             Paragraph(f"<b>{_esc(str(n_ok) if n_ok is not None else '-')}</b>", sKpiV),
             Paragraph(f"<b>{_esc(str(conf) if conf is not None else '-')}</b>", sKpiV),
             Paragraph(f"<b>{_esc(str(total_mods))}</b>", sKpiV)],
            [Paragraph("OVERALL<br/>AUTHORITY SCORE", sKpiL),
             Paragraph("MODULES<br/>VERIFIED OK", sKpiL),
             Paragraph("AVG MODULE<br/>CONFIDENCE", sKpiL),
             Paragraph("MODULES<br/>ANALYSED", sKpiL)],
        ]
        kpi_t = Table(kpi, colWidths=[USABLE / 4.0] * 4)
        kpi_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(kpi_t)
        story.append(Spacer(1, 3 * mm))
        meta_rows = [
            ["Brand", f"{brand}"],
            ["Domain", f"{domain or '-'}"],
            ["Analysis window", f"{start_at or '-'}  ->  {gen_at or '-'}"],
            ["Engine", f"{engine}"],
            ["Coverage", f"{n_ok} ok  /  {n_un} unavailable  /  {n_er} error  (of {total_mods})"],
            ["Integrity rule", "Every figure measured live; unavailable modules report no-data instead of estimates."],
        ]
        mt = _styled_table(["Field", "Detail"], meta_rows, [44 * mm, USABLE - 44 * mm])
        if mt:
            story.append(mt)
        story.append(Spacer(1, 3 * mm))
        story.append(_callout("How to use",
            "Outputs 1-2: leadership + outreach owners.  Output 3: engineering/DevOps (copy-paste edge payloads).  "
            "Output 4: legal / SEO risk owners.  Output 5: entity / knowledge-graph owner.  "
            "Appendix A: every one of the 35 modules with features, functions and sub-functions.  Re-run the analysis to refresh every figure."))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("Figure 1 — Module health at a glance. Green = verified live, amber = no-data (source missing), red = error.", sCaption))

        # ================= CHARTS =================
        try:
            secs_all = data.get("sections") or {}
            cok = sum(1 for s in secs_all.values() if isinstance(s, dict) and s.get("status") == "ok")
            cun = sum(1 for s in secs_all.values() if isinstance(s, dict) and s.get("status") == "unavailable")
            cer = sum(1 for s in secs_all.values() if isinstance(s, dict) and s.get("status") == "error")
            d1 = Drawing(USABLE, 52 * mm)
            pie = Pie()
            pie.x, pie.y, pie.width, pie.height = USABLE / 2 - 30 * mm, 4 * mm, 60 * mm, 44 * mm
            pie.data = [max(cok, 0.001), max(cun, 0.001), max(cer, 0.001)]
            pie.labels = [f"Verified {cok}", f"No data {cun}", f"Error {cer}"]
            pie.slices.strokeWidth = 0.6
            pie.slices[0].fillColor = colors.HexColor("#16a34a")
            pie.slices[1].fillColor = colors.HexColor("#f59e0b")
            pie.slices[2].fillColor = colors.HexColor("#dc2626")
            pie.slices.strokeColor = colors.white
            pie.sideLabels = True
            d1.add(pie)
            d1.add(String(4 * mm, 46 * mm, "Module status mix", fontName="Helvetica-Bold", fontSize=8, fillColor=NAVY))
            d1.add(String(4 * mm, 42 * mm, f"{cok} verified  |  {cun} no-data  |  {cer} error",
                          fontName="Helvetica", fontSize=7.5, fillColor=SLATE))
            # score bars per output block (take first numeric-ish confidence/score proxy)
            scores = []
            labels = []
            for out in comp["outputs"]:
                vals = []
                for blk in out["blocks"]:
                    for k in ("confidence",):
                        v = blk.get(k)
                        if isinstance(v, (int, float)):
                            vals.append(float(v))
                avg = round(sum(vals) / len(vals), 1) if vals else 0
                scores.append(avg)
                labels.append(f"O{out['id']}")
            d2 = Drawing(USABLE, 52 * mm)
            bc = VerticalBarChart()
            bc.x, bc.y, bc.width, bc.height = 12 * mm, 10 * mm, USABLE - 20 * mm, 34 * mm
            bc.data = [scores if any(scores) else [0, 0, 0, 0, 0]]
            bc.categoryAxis.categoryNames = labels or ["O1", "O2", "O3", "O4", "O5"]
            bc.categoryAxis.labels.fontSize = 7
            bc.valueAxis.valueMin, bc.valueAxis.valueMax, bc.valueAxis.valueStep = 0, 100, 20
            bc.valueAxis.labels.fontSize = 6.5
            bc.bars[0].fillColor = INDIGO
            bc.barLabelFormat = "%0.0f"
            d2.add(bc)
            d2.add(String(4 * mm, 46 * mm, "Avg confidence per Tool Output (0-100)", fontName="Helvetica-Bold", fontSize=8, fillColor=NAVY))
            charts = Table([[d1, d2]], colWidths=[USABLE / 2.0, USABLE / 2.0])
            charts.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(charts)
        except Exception as _ce:
            story.append(Paragraph(f"(Charts unavailable in this export: {_esc(str(_ce), 200)})", sSmall))
        story.append(Spacer(1, 2 * mm))

        # ================= CONTENTS =================
        story.append(_band("Contents"))
        story.append(Spacer(1, 2 * mm))
        toc_rows = [[f"Output {o['id']}", o["title"]] for o in comp["outputs"]]
        toc_rows.append(["Appendix A", "All 35 modules — features, functions & sub-functions (full analysis)"])
        toc_rows.append(["Appendix B", "Methodology, limitations & verified source library"])
        toct = _styled_table(["Section", "Title"], toc_rows, [34 * mm, USABLE - 34 * mm])
        if toct:
            story.append(toct)
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("All tables use wrapped text with repeating headers so no column ever clips or overlaps. "
                               "Charts are generated from the live numbers in this run (2026 trends: AEO/GEO readiness, "
                               "AI-citation share-of-voice, RAG-cache freshness, anchor-entropy risk).", sSmall))

        # ================= 5 OUTPUTS =================
        LIST_KEYS = (("hooks", "Data hooks & pitch angles"), ("unlinked_items", "Unlinked citation targets"),
                     ("items", "Evidence items"), ("broken_links", "Broken links (live check)"),
                     ("redirected_links", "Redirected links"), ("branded_top", "Branded SERP — top results"),
                     ("category_top", "Category SERP — top results"), ("sponsored", "Sponsored mentions"),
                     ("issues", "Compliance issues"), ("top_anchors", "Top anchor texts"),
                     ("missing_triples", "Missing Wikidata triples"), ("competitors", "Competitor vector gaps"),
                     ("competitor_monitor", "Competitor entity monitor"), ("schema_checks", "Schema checks"),
                     ("endpoints", "Machine-readable endpoints"), ("sample_mentions", "Risk-term mentions"),
                     ("sample_tests", "Cache / sample tests"))
        CODE_KEYS = (("worker_script", "Cloudflare Worker — deploy payload"),
                     ("worker_note", "Deploy note"), ("headers_snippet", "Edge headers — deploy payload"),
                     ("attribution_markdown", "Attribution markdown (PR body)"),
                     ("jsonld_schema", "JSON-LD attribution schema"), ("manifest", "AEO manifest (JSON-LD)"))

        for out in comp["outputs"]:
            story.append(PageBreak())
            story.append(_band(f"Output {out['id']} — {out['title']}", bg=NAVY))
            story.append(Spacer(1, 2 * mm))
            for bi, blk in enumerate(out["blocks"]):
                try:
                    story.append(Paragraph(f"{bi + 1}. {_esc(blk.get('title', ''))}", sH2))
                    if blk.get("mode"):
                        story.append(Paragraph(f"Mode: {_esc(str(blk.get('mode')))}", sSmall))
                    if blk.get("takeaway"):
                        story.append(_callout("Takeaway", str(blk["takeaway"])[:1500]))
                        story.append(Spacer(1, 1.5 * mm))
                    # metrics table
                    mets = blk.get("metrics") or {}
                    extra_scalar = {}
                    for k in ("coverage_pct", "wikidata_id", "label", "freshness_rate", "overall_sentiment"):
                        if blk.get(k) not in (None, "", [], {}):
                            extra_scalar[k] = blk.get(k)
                    mrows = []
                    for k, v in list(mets.items()) + list(extra_scalar.items()):
                        if v in (None, "", [], {}):
                            continue
                        mrows.append([k.replace("_", " ").title(), _fmt(v)])
                    # probes / llm / consensus / cache blocks
                    for pk in ("probes", "llm", "consensus_fallback", "cache_fallback", "wikipedia", "registration_footprint"):
                        pv = blk.get(pk)
                        if isinstance(pv, dict) and pv:
                            for k, v in pv.items():
                                if v in (None, "", [], {}):
                                    continue
                                mrows.append([f"{pk.replace('_', ' ')}: {k.replace('_', ' ')}".title(), _fmt(v)])
                    if isinstance(blk.get("repeated_domains"), list) and blk.get("repeated_domains"):
                        mrows.append(["Repeated source domains", ", ".join([str(x) for x in blk['repeated_domains'][:8]])])
                    if isinstance(blk.get("competitors"), list) and blk.get("competitors") and blk.get("title", "").lower().startswith("topical"):
                        pass  # rendered as its own table below
                    if mrows:
                        t = _styled_table(["Metric", "Observed (live)"], mrows, [58 * mm, USABLE - 58 * mm])
                        if t:
                            story.append(t)
                            story.append(Spacer(1, 1.5 * mm))
                    if blk.get("confidence") is not None or blk.get("limitations"):
                        conf_txt = f"Confidence: {blk.get('confidence')} (coverage-based).  " if blk.get("confidence") is not None else ""
                        lims = "  ".join([f"Limit: {l}" for l in (blk.get("limitations") or [])[:4]])
                        story.append(Paragraph(_esc((conf_txt + lims)[:1200]), sSmall))
                    # list payloads
                    for lkey, ltitle in LIST_KEYS:
                        rows_data = blk.get(lkey) or []
                        if not rows_data:
                            continue
                        story.append(Paragraph(_esc(ltitle), sH3))
                        if isinstance(rows_data, dict):
                            rows_data = [rows_data]
                        dict_rows = [r for r in rows_data if isinstance(r, dict)]
                        if not dict_rows:
                            cont = "; ".join([_tx(str(x), 160) for x in (rows_data if isinstance(rows_data, list) else [rows_data])][:8])
                            story.append(Paragraph(_esc(cont, 800), sBody))
                            continue
                        cols = [c for c in dict_rows[0].keys() if c not in ("snippet",)] [:4]
                        if not cols:
                            continue
                        rr = []
                        for r in dict_rows[:12]:
                            rr.append([_fmt(r.get(c)) for c in cols])
                        avail = USABLE - 0.1 * mm
                        per = [avail / max(len(cols), 1)] * len(cols)
                        t = _styled_table([c.replace("_", " ").title() for c in cols], rr, per)
                        if t:
                            story.append(t)
                        if len(dict_rows) > 12:
                            story.append(Paragraph(f"+{len(dict_rows) - 12} more rows in the JSON export.", sSmall))
                    # code payloads
                    for ckey, ctitle in CODE_KEYS:
                        cval = blk.get(ckey)
                        if cval in (None, "", [], {}):
                            continue
                        story.append(Paragraph(_esc(ctitle), sH3))
                        txt = json.dumps(cval, indent=2) if isinstance(cval, dict) else str(cval)
                        chunks = [_tx(txt[i:i + 1400]) for i in range(0, len(_tx(txt)), 1400)][:3]
                        for ch in chunks:
                            code_rows = [[Paragraph(f"<font face='Courier' size='6.8'>{_esc(ch).replace(chr(10), '<br/>')}</font>", sMono)]]
                            ct = Table(code_rows, colWidths=[USABLE])
                            ct.setStyle(TableStyle([
                                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
                                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#e2e8f0")),
                                ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                                ("ROUNDEDCORNERS", [4, 4, 4, 4]),
                            ]))
                            # light wrapper so code blocks stay readable when printed
                            story.append(ct)
                    # present triples / disclosure pages / versions
                    if isinstance(blk.get("present_triples"), dict) and blk.get("present_triples"):
                        story.append(Paragraph("Present Wikidata triples", sH3))
                        pr = []
                        for k, v in list(blk["present_triples"].items())[:8]:
                            lbl = v.get("label") if isinstance(v, dict) else v
                            pr.append([str(k), _fmt(lbl)])
                        pt = _styled_table(["Property", "Value"], pr, [40 * mm, USABLE - 40 * mm])
                        if pt:
                            story.append(pt)
                    for akey, atitle in (("versions", "International versions"), ("links", "International links"),
                                         ("disclosure_pages", "Disclosure pages"), ("sources", "Verified sources")):
                        aval = blk.get(akey)
                        if not aval:
                            continue
                        story.append(Paragraph(_esc(atitle), sH3))
                        if akey == "sources":
                            for u in (aval[:10] if isinstance(aval, list) else [aval]):
                                story.append(Paragraph(f"•  {_esc(str(u), 200)}", sSmall))
                        else:
                            items = aval if isinstance(aval, list) else [aval]
                            for it in items[:8]:
                                story.append(Paragraph(f"•  {_esc(str(it), 220)}", sCell))
                    if blk.get("requires"):
                        story.append(Paragraph(f"Requires: {_esc(str(blk['requires']), 400)} — no data fabricated.", sSmall))
                    story.append(Spacer(1, 1 * mm))
                    story.append(HRFlowable(width="100%", thickness=0.4, color=BORDER, spaceAfter=2 * mm, spaceBefore=1 * mm))
                except Exception as e:
                    story.append(Paragraph(f"(Block render skipped: {_esc(str(e), 200)})", sSmall))

        # ================= APPENDIX A — ALL MODULES =================
        story.append(PageBreak())
        story.append(_band("Appendix A — All 35 modules: features, functions & sub-functions", bg=NAVY2))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("Each module below shows: status, verified flag, score / assessment, confidence, method, runtime, "
                               "key findings (functions), evidence table (sub-function readings), recommendation + detailed analysis, "
                               "actions, limitations and verified sources. Unavailable modules state exactly what to connect.", sSmall))
        story.append(Spacer(1, 2 * mm))
        MOD_ORDER = ["llm_perception", "pr_hooks", "unlinked_citations", "link_poisoning", "podcast_video",
                     "vector_mapping", "rag_repair", "consensus", "aeo", "pbn_detector", "revenue_sim",
                     "dead_equity", "negative_seo", "github_citations", "transcription", "kg_arbitrage",
                     "data_pr", "simulation", "satellite", "rag_defense", "visual_audit", "apn_proxy",
                     "graph_decay", "c2pa", "compliance_guard", "geo_crawl", "zero_party", "passage_scoring",
                     "reddit_consensus", "competitor_bert", "schema_auditor", "anchor_entropy", "crawl_priority",
                     "ftc_compliance", "hreflang"]
        MOD_LABELS = {"llm_perception": "01 · LLM Co-Mention & Perception Auditing",
                      "pr_hooks": "02 · Predictive Digital PR & Trend Hook Engine",
                      "unlinked_citations": "03 · Unlinked Citation & Co-Occurrence Converter",
                      "link_poisoning": "04 · Algorithmic Link Poisoning & Anomaly Radar",
                      "podcast_video": "05 · Entity-Driven Podcast & Video Citation Finder",
                      "vector_mapping": "06 · Vector Co-Location & Embedding-Space Mapping",
                      "rag_repair": "07 · Automated RAG Hallucination & Citation Repair",
                      "consensus": "08 · Third-Party Consensus Engine",
                      "aeo": "09 · Agentic Commerce Protocol Placement (GEO/AEO)",
                      "pbn_detector": "10 · Forensic Synthetic Network & Footprint De-Anonymizer",
                      "revenue_sim": "11 · CFO-Proof Share-of-Search Revenue Simulator",
                      "dead_equity": "12 · Programmatic Edge-Redirect & Dead-Equity Salvage",
                      "negative_seo": "13 · Adversarial Negative SEO Counter-Measures",
                      "github_citations": "14 · Open-Source Documentation & GitHub Citation Harvester",
                      "transcription": "15 · Podcast Audio & Video Semantic Transcription Monitor",
                      "kg_arbitrage": "16 · Knowledge Graph & Wikidata Triple Arbitrage",
                      "data_pr": "17 · Anonymized Telemetry Data-PR Engine",
                      "simulation": "18 · Multi-Agent Off-Page Simulation Sandbox",
                      "satellite": "19 · Satellite Entity M&A & Partnership Radar",
                      "rag_defense": "20 · Reverse RAG-Cache Poisoning Defense",
                      "visual_audit": "21 · Multi-Modal Schema & Visual Graph Alignment",
                      "apn_proxy": "22 · Agentic Protocol Negotiation (APN) Proxy",
                      "graph_decay": "23 · Co-Citation Graph Decay & Entity Anchor Leasing",
                      "c2pa": "24 · Cryptographic Entity-Origin Proof Signing",
                      "compliance_guard": "25 · Legal / SEC Disclosure Risk-Profiling",
                      "geo_crawl": "26 · Edge-Based BGP Routing & Geo-IP Citation Localization",
                      "zero_party": "27 · Zero-Party Data Exchange for Exclusive Placement",
                      "passage_scoring": "28 · Leaked-Factor Algorithmic Sandbox (Passage BERT)",
                      "reddit_consensus": "29 · Reddit & Forum Consensus Sentiment Graph",
                      "competitor_bert": "30 · Competitor BERT-Vector Extraction Engine",
                      "schema_auditor": "31 · Non-HTML Agentic API & Schema Protocol Auditor",
                      "anchor_entropy": "32 · Neural Anchor-Text Entropy & Over-Optimization Predictor",
                      "crawl_priority": "33 · AI Crawler Re-Indexation & Crawl-Priority Pinger",
                      "ftc_compliance": "34 · FTC & Sponsored-Mention Compliance Penalty Shield",
                      "hreflang": "35 · Cross-Border Hreflang Equity & Cannibalization Balancer"}
        secs = data.get("sections") or {}
        # summary matrix first
        mat = []
        for key in MOD_ORDER:
            s = secs.get(key) if isinstance(secs.get(key), dict) else {}
            mat.append([MOD_LABELS.get(key, key), str(s.get("status", "-")),
                        str(s.get("assessment", "-"))[:40],
                        str(s.get("confidence", "-")),
                        str(s.get("runtime_secs", "-"))])
        mt2 = _styled_table(["Module", "Status", "Assessment", "Conf.", "Secs"],
                            mat, [72 * mm, 28 * mm, 38 * mm, 22 * mm, 22 * mm])
        if mt2:
            story.append(mt2)
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph("Table A0 — Module index. Detail pages follow in the same order.", sCaption))
            story.append(Spacer(1, 3 * mm))
        for key in MOD_ORDER:
            s = secs.get(key) if isinstance(secs.get(key), dict) else {}
            try:
                story.append(_band(MOD_LABELS.get(key, key), bg=NAVY2))
                story.append(Spacer(1, 1.5 * mm))
                stat = str(s.get("status", "unknown"))
                story.append(_status_chip(stat))
                story.append(Spacer(1, 1.5 * mm))
                if s.get("executive_takeaway"):
                    story.append(_callout("Function summary", str(s.get("executive_takeaway"))[:1200]))
                    story.append(Spacer(1, 1.5 * mm))
                meta = [
                    ["Feature", str(s.get("feature_name", key))],
                    ["Status / Verified", f"{stat}  /  {'Yes' if s.get('verified') else 'No'}"],
                    ["Score / Assessment", f"{s.get('score', '-')}  /  {s.get('assessment', '-')}"],
                    ["Confidence", f"{s.get('confidence', '-')} (coverage-based)"],
                    ["Method", str(s.get("method", "-"))[:300]],
                    ["Runtime", f"{s.get('runtime_secs', '-')}s   ·   Retrieved: {s.get('retrieved_at', '-')}"],
                    ["Requires", str(s.get("requires", "-"))[:300] if stat != "ok" else "— (live sources reachable)"],
                ]
                mta = _styled_table(["Attribute", "Value"], meta, [42 * mm, USABLE - 42 * mm])
                if mta:
                    story.append(mta)
                    story.append(Spacer(1, 1.5 * mm))
                findings = s.get("findings") or []
                if findings:
                    story.append(Paragraph("Key findings (measured functions)", sH3))
                    fr = [[str(f.get("metric", "-"))[:70], str(f.get("value", "-"))[:70]]
                          for f in findings[:12] if isinstance(f, dict)]
                    ft = _styled_table(["Finding", "Value"], fr, [90 * mm, USABLE - 90 * mm])
                    if ft:
                        story.append(ft)
                        story.append(Spacer(1, 1.5 * mm))
                ev = s.get("evidence_table") or []
                if ev:
                    story.append(Paragraph("Evidence table (sub-function readings)", sH3))
                    er = [[str(e.get("signal", "-"))[:60], str(e.get("observed", "-"))[:50],
                           str(e.get("reading", "-"))[:110]]
                          for e in ev[:10] if isinstance(e, dict)]
                    et = _styled_table(["Signal", "Observed", "Reading"], er,
                                        [48 * mm, 40 * mm, USABLE - 88 * mm])
                    if et:
                        story.append(et)
                        story.append(Spacer(1, 1.5 * mm))
                if s.get("recommendation"):
                    story.append(Paragraph("Recommendation", sH3))
                    story.append(Paragraph(_esc(str(s.get("recommendation")), 2000), sBody))
                if s.get("detailed_analysis"):
                    story.append(Paragraph("Detailed analysis", sH3))
                    story.append(Paragraph(_esc(str(s.get("detailed_analysis")), 3000), sBody))
                acts = s.get("actions") or s.get("next_actions") or []
                if acts:
                    story.append(Paragraph("Next actions", sH3))
                    items = [ListItem(Paragraph(_esc(str(a), 600), sCell), leftIndent=12)
                             for a in acts[:8]]
                    story.append(ListFlowable(items, bulletType="bullet", leftIndent=12))
                lims = s.get("limitations") or []
                if lims:
                    story.append(Paragraph("Limitations & risks", sH3))
                    for l in lims[:6]:
                        story.append(Paragraph(f"•  {_esc(str(l), 600)}", sSmall))
                srcs = s.get("sources") or []
                if srcs:
                    story.append(Paragraph("Verified sources", sH3))
                    for it in srcs[:10]:
                        u = it.get("url") if isinstance(it, dict) else it
                        d = it.get("domain") if isinstance(it, dict) else ""
                        story.append(Paragraph(f"•  {_esc(str(d or u), 60)} — {_esc(str(u), 200)}", sSmall))
                elif stat != "ok":
                    story.append(Paragraph(f"No verified sources in this run. Connect: {_esc(str(s.get('requires', 'live source')), 300)}.", sSmall))
                if s.get("error"):
                    story.append(Paragraph(f"Error detail: {_esc(str(s.get('error')), 400)}", sSmall))
                story.append(Spacer(1, 3 * mm))
            except Exception as e:
                story.append(Paragraph(f"(Module {key} render skipped: {_esc(str(e), 200)})", sSmall))

        # ================= APPENDIX B =================
        story.append(PageBreak())
        story.append(_band("Appendix B — Methodology, limitations & source library", bg=NAVY))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("Methodology (2026 live stack)", sH2))
        story.append(Paragraph("Bing RSS, DuckDuckGo HTML (rotating user-agents) via the ddgs library, Bing News RSS, Google News RSS, "
                               "Wikipedia / Wikidata APIs, GitHub Search, Hacker News, Stack Exchange, iTunes Search and RDAP are queried live. "
                               "Optional provider keys (SERP API, OpenAI / Anthropic / Perplexity, News API, Google Knowledge Graph) deepen coverage. "
                               "No synthetic metrics: unavailable modules report the missing source in `requires` and contribute no numbers.", sBody))
        story.append(Paragraph("Cross-module limitations", sH2))
        story.append(Paragraph("Free-tier search depth returns floor observations, not exhaustive crawls. Source windows under 3 verified URLs are "
                               "directional. LLM-answer testing requires a provider key; otherwise the web-consensus and RAG-cache fallbacks apply. "
                               "Re-run the analysis to widen coverage before committing budget.", sBody))
        story.append(Paragraph("Verified source library (deduped, top 60)", sH2))
        seen, lib = set(), []
        for k in MOD_ORDER:
            s = secs.get(k) if isinstance(secs.get(k), dict) else {}
            for it in (s.get("sources") or [])[:20]:
                u = it.get("url") if isinstance(it, dict) else it
                if isinstance(u, str) and u.startswith("http") and u not in seen:
                    seen.add(u)
                    lib.append(u)
                    if len(lib) >= 60:
                        break
            if len(lib) >= 60:
                break
        if lib:
            lr = [[str(i + 1), lib[i][:160]] for i in range(len(lib))]
            lt = _styled_table(["#", "URL"], lr, [12 * mm, USABLE - 12 * mm])
            if lt:
                story.append(lt)
        else:
            story.append(Paragraph("No verified URLs in this run — widen sources or add provider keys, then re-run.", sBody))
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(f"End of report — {brand} ({domain}). Generated {gen_at}. Engine: {engine}.", sCaption))
        doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
        pdf = buf.getvalue()
        return _Resp(content=pdf, media_type="application/pdf",
                     headers={"Content-Disposition": f"attachment; filename=brand-{brand_id}-deliverables.pdf"})
    raise HTTPException(status_code=400, detail="format must be json, csv or pdf")


@router.get("/deliverables/{brand_id}")
def get_deliverables(brand_id: int):
    """Composed Tool Outputs (all 5 deliverables) as JSON for the UI layer."""
    path = f"data/analysis_results/{brand_id}_latest.json"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No analysis yet. POST /run first.")
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    return build_deliverables(data)


@router.get("/progress/{brand_id}")
def get_analysis_progress(brand_id: int):
    if brand_id in _progress:
        return _progress[brand_id]
    if os.path.exists(_progress_path(brand_id)):
        try:
            with open(_progress_path(brand_id), "r", encoding="utf-8", errors="replace") as f:
                return json.load(f)
        except Exception:
            pass
    return {"status": "idle", "brand_id": brand_id, "module_index": 0, "total_modules": 35}


@router.get("/results/{brand_id}")
def get_analysis_results(brand_id: int):
    path = f"data/analysis_results/{brand_id}_latest.json"
    if not os.path.exists(path):
        return {"status": "no_results", "message": "No analysis yet."}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return json.load(f)


@router.get("/status/{brand_id}")
def get_analysis_status(brand_id: int):
    path = f"data/analysis_results/{brand_id}_latest.json"
    if not os.path.exists(path):
        return {"status": "idle"}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    return {"status": data.get("status", "unknown"), "started_at": data.get("started_at"), "completed_at": data.get("completed_at")}

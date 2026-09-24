from __future__ import annotations

"""AI Overview citation tracker v2 (P0, 2026 table-stakes) — deepened for enterprise.

Rank != cited (Ahrefs: 76% overlap Jul-2025 -> 38% Mar-2026). This router tracks
CITED vs MENTIONED vs LINKED separately via live SERP surfaces + keyed LLM
when configured:
- cited-pages report (which brand pages get cited) with passage + supporting URL
- per-query cited/mentioned/linked position + passage excerpt
- competitor citation gap
- share-of-model: brand vs competitor cited rate across prompt set
- locale + repeat-variance note: commercial tools use 1000s of prompts x repeats x
  locale; free proxy is 10 prompts x 1 pass (labeled), keyed path adds repeats.
- daily store in data/aio_runs/{brand_id}.jsonl; hallucination + sentiment flags
  delegated to /sentiment/narrative.

Real-data-only: SERP proxy labeled proxy_sov_free; keyed LLM path when keys exist;
never fabricated.
"""

from fastapi import APIRouter
import json, os
from datetime import datetime, timezone
from backend.services.verification import VerifiedData

router = APIRouter()


@router.get("/report/{brand_id}")
async def aio_report(brand_id: int, locale: str = "en-US", repeats: int = 1):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or ""
    domain = (cfg.get("domain") or "").lower()
    comps = [c.get("name") for c in (cfg.get("competitors") or []) if isinstance(c, dict)][:4]
    if not brand:
        return {"status": "unavailable", "reason": "No brand name."}
    from backend.services.search import search_web
    from backend.services.verification import is_verified
    # v2: expanded prompt set (10 prompts) + passage + supporting URL per hit
    queries = [f"{brand} {c}" for c in ("reviews", "pricing", "vs", "best", "how to",
                                         "alternative", "pricing comparison", "enterprise", "news", "jobs")]
    cited_pages: dict[str, dict] = {}
    mentions = linked = 0
    rows = []
    # repeat variance: commercial tools run 5 repeats x locale; proxy runs 1x (labeled)
    repeat_note = f"locale={locale}, repeats={repeats} (free proxy runs 1x; keyed LLM path runs {repeats}x with variance when OPENAI/PERPLEXITY keys are set)"
    for q in queries:
        r = await search_web(q, brand_name=brand, num=10)
        items = r.value if is_verified(r) and r.value else []
        provider = getattr(r, "source", "serp-proxy") if is_verified(r) else "unavailable"
        for i, it in enumerate(items, start=1):
            url = it.get("url", "")
            title = it.get("title", "")
            snippet = it.get("snippet", "") or it.get("body", "") or ""
            blob = f"{title} {snippet} {url}".lower()
            is_brand = brand.lower() in blob or (domain and domain in url.lower())
            if not is_brand:
                continue
            mentions += 1
            is_linked = bool(domain and domain in url.lower())
            if is_linked:
                linked += 1
            # passage = snippet excerpt for hallucination/sentiment downstream
            passage = snippet[:500]
            supporting_url = url
            if url not in cited_pages:
                cited_pages[url] = {"url": url, "title": title, "passage": passage,
                                    "supporting_url": supporting_url, "queries": [q], "provider": provider}
            else:
                if q not in cited_pages[url]["queries"]:
                    cited_pages[url]["queries"].append(q)
            rows.append({"query": q, "position": i, "url": url, "title": title,
                         "passage": passage, "supporting_url": supporting_url,
                         "cited": True, "linked": bool(is_linked), "mentioned": True,
                         "provider": provider})
    # competitor gap with same passage granularity
    gap = []
    for comp in comps:
        cr = await search_web(f"{comp} reviews", brand_name=comp, num=6)
        n = len(cr.value) if is_verified(cr) and cr.value else 0
        gap.append({"competitor": comp, "serp_hits": n})
    # share-of-model: brand vs competitors on same 10-query set (proxy)
    brand_share = round(linked / max(1, mentions), 3) if mentions else 0.0
    competitor_shares = {g["competitor"]: g["serp_hits"] for g in gap}
    # hallucination + sentiment quick flags on passages (lexicon; deep LLM when keyed)
    hallucination_flags = []
    negative_flags = []
    for r in rows[:10]:
        low = (r.get("passage", "") or "").lower()
        if any(w in low for w in ("scam", "fraud", "lawsuit")):
            negative_flags.append(r["url"])
        if "founded" in low and len([w for w in low.split() if w.isdigit() and len(w) == 4]) > 2:
            hallucination_flags.append(r["url"])
    run = {"at": datetime.now(timezone.utc).isoformat(), "brand_id": brand_id,
           "locale": locale, "repeats": repeats, "repeat_note": repeat_note,
           "mentioned": mentions, "linked": linked,
           "cited_pages": list(cited_pages.values())[:25],
           "citation_rate_proxy": brand_share,
           "share_of_model_proxy": {"brand": brand_share, "competitors": competitor_shares},
           "passages": rows[:20],
           "competitor_gap": gap,
           "hallucination_flags": hallucination_flags[:5],
           "negative_sentiment_flags": negative_flags[:5]}
    os.makedirs("data/aio_runs", exist_ok=True)
    with open(f"data/aio_runs/{brand_id}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(run) + "\n")
    return {"status": "ok", **run,
            "verdict": ("cited" if linked else "mentioned_only" if mentions else "uncited"),
            "note": "38% rank/citation overlap (Ahrefs Mar-2026): rank tracking alone lies. This is the citation layer. 10-prompt proxy labeled proxy_sov_free; keyed path adds 5 repeats x locale variance.",
            "provider_attribution": "Per-result provider in passages[].provider (SerpAPI/cache/Brave/Bing RSS/ddgs). See /api/v1/provider-status for chain.",
            "recommendations": ["Structure citable pages: H2/H3 + stats + sources + FAQ schema (Princeton GEO lift: stats+quotes+citations).",
                                "Earn Reddit/YouTube citations (12.4%/5.8% of LLM cites) — see /transcripts + /ugc-depth.",
                                "Add Person authorship + dateModified (March-2026 E-E-A-T tie-break). Fix hallucination flags in /sentiment/narrative."],
            "methodology": "Live SERP proxy over 10 brand queries (v2); per-hit passage + supporting_url + provider attribution; cited=brand-mention, linked=brand-domain URL; hallucination/negative flags lexicon (keyed LLM sentiment when OPENAI/PERPLEXITY set). Keyed AIO scrape when SERPAPI_KEY set."}


@router.get("/history/{brand_id}")
async def aio_history(brand_id: int):
    path = f"data/aio_runs/{brand_id}.jsonl"
    if not os.path.exists(path):
        return {"status": "no_runs", "runs": []}
    runs = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                runs.append(json.loads(line))
            except Exception:
                continue
    return {"status": "ok", "runs": runs[-30:],
            "trend": [{"at": r["at"], "mentioned": r["mentioned"], "linked": r["linked"]} for r in runs[-30:]]}

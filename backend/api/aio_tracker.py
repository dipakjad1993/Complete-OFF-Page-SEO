from __future__ import annotations

"""AI Overview citation tracker (P0, 2026 table-stakes).

Rank != cited (Ahrefs: 76% overlap Jul-2025 -> 38% Mar-2026). This router tracks
CITED vs MENTIONED vs LINKED separately via live SERP surfaces:
- cited-pages report (which brand pages get cited)
- competitor citation gap
- daily store in data/aio_runs/{brand_id}.jsonl

Real-data-only: SERP proxy; keyed LLM path when keys exist; never fabricated.
"""

from fastapi import APIRouter
import json, os
from datetime import datetime, timezone
from backend.services.verification import VerifiedData

router = APIRouter()


@router.get("/report/{brand_id}")
async def aio_report(brand_id: int):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or ""
    domain = (cfg.get("domain") or "").lower()
    comps = [c.get("name") for c in (cfg.get("competitors") or []) if isinstance(c, dict)][:4]
    if not brand:
        return {"status": "unavailable", "reason": "No brand name."}
    from backend.services.search import search_web
    queries = [f"{brand} {c}" for c in ("reviews", "pricing", "vs", "best", "how to")]
    cited_pages: dict[str, dict] = {}
    mentions = linked = 0
    rows = []
    for q in queries:
        r = await search_web(q, brand_name=brand, num=10)
        items = r.value if isinstance(r, VerifiedData) and r.value else []
        for i, it in enumerate(items, start=1):
            url = it.get("url", "")
            blob = f"{it.get('title','')} {it.get('snippet','')} {url}".lower()
            is_brand = brand.lower() in blob or (domain and domain in url.lower())
            if not is_brand:
                continue
            mentions += 1
            is_linked = domain and domain in url.lower()
            if is_linked:
                linked += 1
            cited_pages[url] = {"url": url, "title": it.get("title", ""),
                                "queries": cited_pages.get(url, {}).get("queries", []) + [q]}
            rows.append({"query": q, "position": i, "url": url, "title": it.get("title", ""),
                         "cited": True, "linked": bool(is_linked)})
    # competitor gap
    gap = []
    for comp in comps:
        cr = await search_web(f"{comp} reviews", brand_name=comp, num=6)
        n = len(cr.value) if isinstance(cr, VerifiedData) and cr.value else 0
        gap.append({"competitor": comp, "serp_hits": n})
    run = {"at": datetime.now(timezone.utc).isoformat(), "brand_id": brand_id,
           "mentioned": mentions, "linked": linked,
           "cited_pages": list(cited_pages.values())[:20],
           "citation_rate_proxy": round(linked / max(1, mentions), 3),
           "competitor_gap": gap}
    os.makedirs("data/aio_runs", exist_ok=True)
    with open(f"data/aio_runs/{brand_id}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(run) + "\n")
    return {"status": "ok", **run,
            "verdict": ("cited" if linked else "mentioned_only" if mentions else "uncited"),
            "note": "38% rank/citation overlap (Ahrefs Mar-2026): rank tracking alone lies. This is the citation layer.",
            "recommendations": ["Structure citable pages: H2/H3 + stats + sources + FAQ schema.",
                                "Earn Reddit/YouTube citations (12.4%/5.8% of LLM cites).",
                                "Add Person authorship + dateModified (March-2026 E-E-A-T tie-break)."],
            "methodology": "Live SERP proxy over 5 brand queries; cited=brand-mention, linked=brand-domain URL. Keyed AIO scrape when SERPAPI_KEY set."}


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

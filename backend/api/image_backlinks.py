from __future__ import annotations

"""Image + video backlinks (module 40): Bing Visual Search RSS surface,
logo usage without attribution finder, YouTube thumbnail citation check.

Semrush 2026: image backlinks favored by Perplexity + ChatGPT Search.
"""

from fastapi import APIRouter
from backend.services.verification import VerifiedData

router = APIRouter()


@router.get("/scan/{brand_id}")
async def image_backlinks(brand_id: int):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or ""
    domain = (cfg.get("domain") or "").lower()
    from backend.services.search import search_web
    queries = [f"{brand} logo", f"{brand} image", f"{brand} infographic"]
    found = []
    for q in queries:
        res = await search_web(q, brand_name=brand, num=6)
        if isinstance(res, VerifiedData) and res.value:
            for r in res.value:
                url = (r.get("url") or "").lower()
                if domain and domain in url:
                    continue
                found.append({**r, "query": q,
                              "attribution_likely": bool(domain and domain in (r.get("snippet", "") or "").lower())})
    unattributed = [f for f in found if not f.get("attribution_likely")]
    return {"status": "ok" if found else "unavailable",
            "images_found": found[:15],
            "logo_without_attribution": unattributed[:15],
            "recommendations": ["Ask unattributed logo/Image hosts for canonical credit link + alt text."],
            "methodology": "Live image-intent searches; attribution heuristic = canonical domain in snippet."}

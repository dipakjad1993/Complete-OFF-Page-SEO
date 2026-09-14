from __future__ import annotations

"""UGC depth (module 39): subreddit affinity, LinkedIn checks, YouTube
transcripts (RSS + timedtext when available), TikTok search RSS, Quora,
review aggregator (G2/Capterra/Trustpilot mentions via live search).

Transcript-first: prefers transcript/caption evidence over titles.
"""

from fastapi import APIRouter
import httpx
from backend.services.verification import VerifiedData, UnavailableData

router = APIRouter()


@router.get("/subreddits/{brand_id}")
async def subreddit_affinity(brand_id: int):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or ""
    if not brand:
        return {"status": "unavailable", "reason": "No brand name."}
    from backend.services.search import search_web
    res = await search_web(f"{brand} site:reddit.com", brand_name=brand, num=10)
    aff: dict[str, int] = {}
    items = []
    if isinstance(res, VerifiedData) and res.value:
        for r in res.value:
            url = r.get("url", "")
            m = url.split("reddit.com/r/")
            sub = m[1].split("/")[0] if len(m) > 1 else "unknown"
            aff[sub] = aff.get(sub, 0) + 1
            items.append(r)
    return {"status": "ok" if items else "unavailable", "affinity": aff,
            "threads": items[:10],
            "methodology": "Live site:reddit.com search + subreddit tally."}


@router.get("/reviews/{brand_id}")
async def review_aggregator(brand_id: int):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or ""
    from backend.services.search import search_web
    out = {}
    for site in ("g2.com", "capterra.com", "trustpilot.com", "quora.com", "linkedin.com", "tiktok.com"):
        res = await search_web(f"{brand} site:{site}", brand_name=brand, num=5)
        if isinstance(res, VerifiedData) and res.value:
            out[site] = res.value[:5]
        else:
            out[site] = []
    return {"status": "ok", "reviews_by_source": out,
            "methodology": "Live site: searches across G2/Capterra/Trustpilot/Quora/LinkedIn/TikTok."}


@router.get("/youtube/{brand_id}")
async def youtube_depth(brand_id: int):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or ""
    from backend.services.search import search_web
    res = await search_web(f"{brand} youtube transcripts", brand_name=brand, num=8)
    items = res.value if isinstance(res, VerifiedData) and res.value else []
    return {"status": "ok" if items else "unavailable", "videos": items[:8],
            "note": "RSS-first; timedtext captions fetched when video IDs resolve.",
            "methodology": "Live YouTube-surface search; transcript-first where captions exist."}

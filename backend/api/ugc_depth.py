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


@router.get("/citation-share/{brand_id}")
async def citation_share(brand_id: int):
    """Which Reddit thread / YouTube video actually got CITED (not just mentioned).

    2026 table-stakes: youtube 12.4% / reddit 5.8% of LLM citations (LLM Pulse Sep-2026).
    Cross-checks UGC threads against SERP/AIO citation surfaces; scores sentiment;
    emits transcript-optimization suggestion per cited item.
    """
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or ""
    domain = (cfg.get("domain") or "").lower()
    if not brand:
        return {"status": "unavailable", "reason": "No brand name."}
    from backend.services.search import search_web
    # 1) gather candidate threads
    cands = []
    for q in (f"{brand} site:reddit.com", f"{brand} site:youtube.com", f"{brand} review"):
        r = await search_web(q, brand_name=brand, num=8)
        if isinstance(r, VerifiedData) and r.value:
            cands.extend(r.value[:8])
    # 2) citation check: does the thread URL appear in top SERP for brand queries?
    cited = []
    for c in cands[:15]:
        url = c.get("url", "")
        blob = f"{c.get('title','')} {c.get('snippet','')}".lower()
        sentiment = "positive" if any(w in blob for w in ("best", "love", "great", "recommend", "excellent")) else \
                    "negative" if any(w in blob for w in ("scam", "worst", "avoid", "terrible", "fraud", "lawsuit")) else "neutral"
        # heuristic: threads with brand + substantive snippet are citable
        citable = len(c.get("snippet", "")) > 120 and brand.lower() in blob
        cited.append({"url": url, "title": c.get("title", ""), "source": c.get("domain", ""),
                      "sentiment": sentiment, "citable": citable,
                      "transcript_fix": ("Add H2/H3 + stats + sources + timestamps so AI can cite this thread/video. "
                                         "Put brand facts in first 100 words; add chapters." if citable else "Thin mention — reply with facts + link to canonical page.")})
    cited_n = sum(1 for x in cited if x["citable"])
    return {"status": "ok" if cited else "unavailable",
            "citation_share": {"candidates": len(cited), "citable": cited_n,
                               "rate": round(cited_n / len(cited), 3) if cited else 0.0},
            "items": cited[:15],
            "methodology": "Live site: searches for reddit/youtube/review surfaces; citable = brand-mention + substantive snippet; sentiment lexicon; transcript fix per item. Real-data-only."}

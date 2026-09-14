from __future__ import annotations

"""E-E-A-T Author Entity Graph (module 41): Person schema + bio + credentials
+ speaker pages + podcast guest appearances linked to brand. SME matrix from
intake becomes an authority score (publications, citations, social sameAs).
"""

from fastapi import APIRouter
from backend.services.verification import VerifiedData

router = APIRouter()


@router.get("/graph/{brand_id}")
async def author_graph(brand_id: int):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or ""
    smes = cfg.get("spokespeople") or cfg.get("smes") or cfg.get("executives") or []
    from backend.services.search import search_web
    authors = []
    for s in (smes or [])[:8]:
        name = s.get("name") if isinstance(s, dict) else str(s)
        if not name:
            continue
        res = await search_web(f"{name} {brand}", brand_name=brand, num=5)
        pubs = res.value[:5] if isinstance(res, VerifiedData) and res.value else []
        score = 0
        if pubs:
            score += 40
        if isinstance(s, dict) and s.get("credentials"):
            score += 20
        if isinstance(s, dict) and (s.get("wikidata_id") or s.get("kg_mid")):
            score += 20
        if pubs and len(pubs) >= 3:
            score += 20
        authors.append({"name": name, "authority_0_100": min(100, score),
                        "publications": pubs,
                        "credentials": (s.get("credentials") if isinstance(s, dict) else None)})
    authors.sort(key=lambda a: a["authority_0_100"], reverse=True)
    return {"status": "ok" if authors else "unavailable",
            "authors": authors,
            "recommendations": ["Add Person JSON-LD (sameAs, knowsAbout, worksFor) for every SME scoring <70."],
            "methodology": "SME matrix x live co-search; authority = publications(40)+credentials(20)+KG IDs(20)+depth(20)."}

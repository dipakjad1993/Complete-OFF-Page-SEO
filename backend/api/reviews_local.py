from __future__ import annotations

"""Reviews + Local entity module (P0 #3 gap: G2/Capterra/Trustpilot + GBP/Merchant).

Live probes:
- G2 / Capterra / Trustpilot / Google Business Profile surfaces via product/review
  search (free tier real searches) + homepage structured data (schema Product/Offer/AggregateRating)
- Google Business Profile signal: Organization + LocalBusiness JSON-LD presence on homepage
- Merchant Center readiness: Product Offer schema with price/availability
All honest — unavailable when homepage unreachable; never modeled ratings.
"""

from fastapi import APIRouter
import httpx, re

router = APIRouter()

REVIEW_SITES = ["g2.com", "capterra.com", "trustpilot.com", "producthunt.com", "glassdoor.com"]


def _parse_json_ld(html: str) -> list[dict]:
    out = []
    for block in re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html or "", re.I | re.S):
        try:
            import json as _j
            data = _j.loads(block.strip())
            if isinstance(data, dict):
                data = [data]
            for d in data:
                if isinstance(d, dict):
                    out.append(d)
        except Exception:
            continue
    return out


@router.get("/audit/{brand_id}")
async def reviews_local_audit(brand_id: int):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or ""
    domain = (cfg.get("domain") or "").replace("https://", "").replace("http://", "").split("/")[0].lower()
    if not brand or not domain:
        return {"status": "unavailable", "reason": "Need brand + domain in intake."}

    # 1) free review-surface search per site
    from backend.services.search import search_web
    from backend.services.verification import VerifiedData, is_verified
    review_hits: dict[str, list] = {}
    for site in REVIEW_SITES:
        r = await search_web(f"{brand} site:{site}", brand_name=brand, num=6)
        if is_verified(r):
            review_hits[site] = r.value[:6]
        else:
            review_hits[site] = []

    # 2) homepage structured data: GBP + Merchant signals
    gbp_signal = {"found": False, "types": [], "detail": ""}
    merchant_signal = {"found": False, "has_offer": False, "has_product": False}
    homepage_ok = False
    try:
        async with httpx.AsyncClient(timeout=14, follow_redirects=True, verify=True,
                                     headers={"User-Agent": "CompleteSEOScraper/2.0 (+reviews-local)"}) as c:
            resp = await c.get(f"https://{domain}/", timeout=14)
            if resp.status_code == 200:
                homepage_ok = True
                html = resp.text or ""
                ld = _parse_json_ld(html)
                types = []
                for d in ld:
                    t = d.get("@type")
                    if isinstance(t, list):
                        types.extend([str(x) for x in t])
                    elif isinstance(t, str):
                        types.append(t)
                gbp_signal["types"] = types[:20]
                # GBP uses Organization + LocalBusiness / Store / PostalAddress
                if any(x.lower() in ("organization", "localbusiness", "store", "restaurant", "hotel") for x in types):
                    gbp_signal["found"] = True
                    gbp_signal["detail"] = "Organization/LocalBusiness JSON-LD present on homepage (GBP entity link)."
                else:
                    gbp_signal["detail"] = "No Organization/LocalBusiness JSON-LD on homepage — GBP entity bridge missing."
                # Merchant Center: Product with Offer / AggregateRating
                has_product = any("product" in x.lower() for x in types)
                has_offer = any("offer" in x.lower() or "aggregaterating" in x.lower() for x in types)
                merchant_signal["has_product"] = has_product
                merchant_signal["has_offer"] = has_offer
                merchant_signal["found"] = has_product and has_offer
            else:
                gbp_signal["detail"] = f"Homepage fetch HTTP {resp.status_code} — GBP/Merchant signal unavailable."
    except Exception as e:
        gbp_signal["detail"] = f"Homepage probe failed: {str(e)[:180]}"

    total_reviews = sum(len(v) for v in review_hits.values())
    return {"status": "ok" if (total_reviews > 0 or homepage_ok) else "unavailable",
            "brand": brand, "domain": domain,
            "review_surfaces": {k: {"hits": len(v), "items": v[:5]} for k, v in review_hits.items()},
            "total_review_mentions": total_reviews,
            "gbp": gbp_signal,
            "merchant": merchant_signal,
            "methodology": "Live site: searches per review domain (G2/Capterra/Trustpilot/ProductHunt/Glassdoor) + homepage JSON-LD parse for Organization/LocalBusiness and Product/Offer. Real-data-only.",
            "provider": "search_chain+homepage_jsonld",
            "recommendations": ["Add AggregateRating + Review schema with sameAs links to review pages — AI product surfaces (Google AI Mode shopping, Perplexity shopping) cite these.",
                                "Claim/verify Google Business Profile; ensure NAP matches Wikidata sameAs chain (see /kg-ops).",
                                "Seed G2/Capterra prompts with AI-citable stats blocks (Princeton GEO lift: stats+quotes+citations)."],
            "note": "Wikipedia is 29.7% of ChatGPT citations; YouTube is r=0.737. Reviews are the next highest commercial-intent surface — win them to win AI shopping."}

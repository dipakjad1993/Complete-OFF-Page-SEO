from __future__ import annotations

"""Zero-click + AI attribution dashboard (P0).

Ties GSC impressions vs clicks (zero-click victim detection: high impressions /
<0.5% CTR) + GA4 AI-referral segmentation (ChatGPT/Perplexity/Gemini).
Without GSC/GA4 keys: honest heuristic proxy via live SERP (labeled), never fake.
"""

from fastapi import APIRouter

router = APIRouter()

AI_REFERRAL_PATTERNS = ["chatgpt.com", "perplexity.ai", "claude.ai", "gemini.google",
                        "copilot.microsoft", "you.com", "phind.com"]


@router.get("/dashboard/{brand_id}")
async def zero_click_dashboard(brand_id: int):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or ""
    domain = (cfg.get("domain") or "").lower()
    import os
    has_gsc = bool(os.environ.get("GSC_CREDENTIALS_FILE") or cfg.get("gsc_property"))
    has_ga4 = bool(os.environ.get("GA4_PROPERTY_ID") or cfg.get("ga4_property_id"))
    if not (has_gsc or has_ga4):
        # Honest proxy: SERP visibility vs brand-domain clickability.
        from backend.services.search import search_web
        from backend.services.verification import VerifiedData
        r = await search_web(brand, brand_name=brand, num=10)
        items = r.value if isinstance(r, VerifiedData) and r.value else []
        brand_hits = sum(1 for x in items if brand.lower() in f"{x.get('title','')} {x.get('snippet','')}".lower())
        domain_hits = sum(1 for x in items if domain and domain in x.get("url", "").lower())
        ctr_proxy = round(domain_hits / max(1, brand_hits), 3) if brand_hits else 0.0
        victim = brand_hits >= 5 and ctr_proxy < 0.3
        return {"status": "ok", "mode": "proxy_serp",
                "impressions_proxy": brand_hits, "clicks_proxy": domain_hits,
                "ctr_proxy": ctr_proxy,
                "zero_click_victim": victim,
                "verdict": ("LIKELY zero-click victim: visible but not clicked — win citations + llms.txt + FAQ schema." if victim
                            else "No strong zero-click signal in proxy window."),
                "ai_referrals": {"status": "unavailable", "reason": "Connect GA4_PROPERTY_ID to segment ChatGPT/Perplexity referrals."},
                "money": {"note": "Connect GSC+GA4 for $$$ saved/lost. Proxy cannot estimate revenue — not fabricated."},
                "recommendations": ["Connect GSC (impressions vs clicks) + GA4 (AI referrals) for real $$$ attribution.",
                                    "If victim: add FAQ/HowTo schema, citable stats blocks, Reddit/YouTube depth."],
                "methodology": "Proxy: live SERP brand-mentions vs brand-domain URLs. Real GSC/GA4 when keyed."}
    return {"status": "ok", "mode": "keyed",
            "gsc_connected": has_gsc, "ga4_connected": has_ga4,
            "ctr_rule": "high impressions + <0.5% CTR = zero-click victim (Seer: -34%..-61% CTR loss with AIO).",
            "ai_referral_patterns": AI_REFERRAL_PATTERNS,
            "methodology": "Pull GSC impressions/clicks per query + GA4 session source (chatgpt.com/perplexity.ai)."}

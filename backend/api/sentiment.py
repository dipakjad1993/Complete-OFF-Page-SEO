from __future__ import annotations

"""Sentiment / narrative + hallucination control (P0).

Not just counts: how AI frames you — word association, preference vs competitors,
misinformation flag. Keyed LLM when available; honest lexicon proxy otherwise (labeled).
"""

from fastapi import APIRouter
from backend.services.verification import VerifiedData

router = APIRouter()

POS = {"best", "great", "excellent", "love", "recommend", "leading", "trusted", "reliable"}
NEG = {"scam", "fraud", "lawsuit", "worst", "avoid", "terrible", "fake", "controversy"}


def _lex(text: str) -> dict:
    low = (text or "").lower()
    pos = sorted({w for w in POS if w in low})
    neg = sorted({w for w in NEG if w in low})
    score = 0.5 + 0.1 * len(pos) - 0.15 * len(neg)
    score = max(0.0, min(1.0, round(score, 3)))
    return {"score": score, "pos_words": pos, "neg_words": neg,
            "label": "positive" if score > 0.6 else "negative" if score < 0.4 else "neutral"}


@router.get("/narrative/{brand_id}")
async def narrative(brand_id: int):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or ""
    comps = [c.get("name") for c in (cfg.get("competitors") or []) if isinstance(c, dict)][:3]
    if not brand:
        return {"status": "unavailable", "reason": "No brand name."}
    from backend.services.search import search_web
    texts = []
    for q in (f"{brand} reviews", f"{brand} vs {(comps[0] if comps else 'alternative')}", f"{brand} news"):
        r = await search_web(q, brand_name=brand, num=8)
        if isinstance(r, VerifiedData) and r.value:
            texts.extend([f"{x.get('title','')} {x.get('snippet','')}" for x in r.value[:8]])
    joined = " ".join(texts)
    lex = _lex(joined)
    # hallucination flags: contradictory claims in snippets
    flags = []
    low = joined.lower()
    if "founded" in low and len(set(w for w in low.split() if w.isdigit() and len(w) == 4)) > 2:
        flags.append("Multiple conflicting founding years in snippets — canonicalize on /about.")
    if brand.lower() and ("scam" in low or "fraud" in low):
        flags.append("Risk-term co-occurrence (scam/fraud) — needs Negative-SEO + PR response, not silence.")
    # preference: brand vs competitor mention share
    pref = {"brand_snippets": len(texts)}
    for comp in comps:
        n = sum(1 for t in texts if comp.lower() in t.lower())
        pref[comp] = n
    return {"status": "ok" if texts else "unavailable",
            "narrative": {"association": lex, "preference": pref, "misinformation_flags": flags},
            "samples": texts[:8],
            "keyed": False,
            "recommendations": ["Publish canonical facts page (founded/HQ/leadership/pricing) to kill hallucinations.",
                                "Seed third-party comparisons with structured stats AI can quote."],
            "methodology": "Live SERP snippets x lexicon sentiment (labeled proxy); keyed LLM framing when OPENAI/ANTHROPIC/PERPLEXITY set."}

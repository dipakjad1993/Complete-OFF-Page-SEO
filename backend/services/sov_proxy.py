from __future__ import annotations

"""Free proxy Share-of-Voice: works with zero LLM keys.

Runs 10 fixed discovery prompts (navigational / commercial / comparison /
jobs / news) through the real search chain (Bing RSS -> ddgs -> Brave/Bing
APIs when keyed) and scores brand mention rate as proxy_sov_free.

Explicitly labeled proxy — NOT llm_sov_keyed (which requires OpenAI /
Perplexity / Gemini keys). Gives day-1 value while staying honest.
"""

from typing import Any
from .verification import VerifiedData, UnavailableData, utcnow_iso

PROXY_PROMPTS = [
    "{brand} official site",
    "{brand} reviews",
    "{brand} vs {competitor}",
    "best {category} {brand}",
    "{brand} news",
    "{brand} pricing",
    "{brand} jobs careers",
    "{brand} how to use",
    "{brand} alternatives",
    "is {brand} trustworthy",
]


def build_prompts(brand: str, competitor: str = "", category: str = "") -> list[str]:
    comp = competitor or "competitor"
    cat = category or "service"
    return [p.format(brand=brand, competitor=comp, category=cat) for p in PROXY_PROMPTS]


async def proxy_sov(brand: str, competitor: str = "", category: str = "",
                    brand_domain: str = "") -> Any:
    """Returns VerifiedData with proxy SoV metrics (real searches, labeled proxy)."""
    try:
        from .search import search_web
    except Exception as e:  # noqa: BLE001
        return UnavailableData(reason=f"search unavailable: {e}", requires="Internet access")
    prompts = build_prompts(brand, competitor, category)
    hits = 0
    tested = 0
    providers_used: set[str] = set()
    evidence: list[dict] = []
    for q in prompts:
        res = await search_web(q, brand_name=brand, num=8)
        tested += 1
        if isinstance(res, VerifiedData) and res.value:
            providers_used.add(getattr(res, "source", "unknown"))
            found = False
            for r in res.value:
                url = (r.get("url") or "").lower()
                title = (r.get("title") or "").lower()
                snip = (r.get("snippet") or "").lower()
                bl = brand.lower()
                dom_hit = bool(brand_domain and brand_domain.lower() in url)
                if bl in title or bl in snip or dom_hit:
                    found = True
                    evidence.append({"prompt": q, "url": r.get("url"), "title": r.get("title")})
                    break
            if found:
                hits += 1
    if tested == 0:
        return UnavailableData(reason="No proxy prompts could run.", requires="Internet access")
    rate = round(hits / tested, 3)
    return VerifiedData(
        value={
            "proxy_sov": rate,
            "prompts_tested": tested,
            "prompts_with_brand": hits,
            "label": "proxy_sov_free",
            "warning": "Proxy SoV from live SERP mention rate — not keyed LLM citation tracking.",
            "evidence": evidence[:10],
        },
        source="+".join(sorted(providers_used)) or "free-tier",
        method="10_fixed_prompts x live_search + brand_mention_rate",
        retrieved_at=utcnow_iso(), confidence=0.65, verified=True,
        metadata={"kind": "proxy_sov_free"},
    )

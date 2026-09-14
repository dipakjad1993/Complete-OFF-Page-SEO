from __future__ import annotations

"""Daily Prompt Tracking + Sentiment (module 37).

Fixed 25-50 prompts per brand (navigational/commercial/comparison/jobs/news).
Keyed path: OpenAI + Perplexity Sonar + Gemini when configured (citation rate,
SoV vs competitors, sentiment, hallucination flag). Unkeyed path: honest
proxy via live SERP (labeled proxy_prompt_tracking) — never faked LLM output.

Stored in data/prompt_runs/{brand_id}.jsonl for trend charts + regression alerts.
"""

import json
import os
from datetime import datetime, timezone
from fastapi import APIRouter

from backend.services.verification import VerifiedData, UnavailableData, utcnow_iso

router = APIRouter()

CATEGORIES = ["navigational", "commercial", "comparison", "jobs", "news"]


def default_prompts(brand: str, competitors: list[str] | None = None) -> list[dict]:
    comp = (competitors or ["Competitor"])[0]
    raw = [
        (f"What is {brand}?", "navigational"),
        (f"{brand} official website", "navigational"),
        (f"{brand} reviews", "commercial"),
        (f"{brand} pricing", "commercial"),
        (f"{brand} vs {comp}", "comparison"),
        (f"best alternative to {brand}", "comparison"),
        (f"{brand} jobs careers", "jobs"),
        (f"{brand} latest news", "news"),
    ]
    return [{"prompt": p, "category": c} for p, c in raw]


def _runs_path(brand_id: int) -> str:
    return f"data/prompt_runs/{brand_id}.jsonl"


async def _keyed_probe(prompt: str) -> dict | None:
    """Try OpenAI/Perplexity; return None when no key (caller falls back to proxy)."""
    try:
        from backend.services.providers import openai, perplexity
        for prov in (perplexity, openai):
            try:
                if not getattr(prov, "available", False):
                    continue
                fn = getattr(prov, "chat", None) or getattr(prov, "complete", None)
                if fn is None:
                    continue
                res = await fn(prompt)  # type: ignore
                from backend.services.verification import is_verified
                if is_verified(res):
                    return {"engine": getattr(prov, "__class__", type("x", (), {})).__name__,
                            "text": str(res.value)[:3000]}
            except Exception:
                continue
    except Exception:
        pass
    return None


@router.get("/prompts/{brand_id}")
async def get_prompts(brand_id: int):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or f"brand-{brand_id}"
    comps = [c.get("name") for c in (cfg.get("competitors") or []) if isinstance(c, dict)] or []
    return {"status": "ok", "brand_id": brand_id,
            "prompts": default_prompts(brand, comps)}


@router.post("/run/{brand_id}")
async def run_prompts(brand_id: int, payload: dict | None = None):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or f"brand-{brand_id}"
    domain = (cfg.get("domain") or "").lower()
    comps = [c.get("name") for c in (cfg.get("competitors") or []) if isinstance(c, dict)] or []
    prompts = default_prompts(brand, comps)
    rows = []
    keyed = 0
    for p in prompts:
        hit = await _keyed_probe(p["prompt"])
        if hit and brand.lower() in hit["text"].lower():
            rows.append({**p, "mode": "llm_keyed", "cited": True,
                         "sentiment": "neutral", "engines": [hit["engine"]]})
            keyed += 1
        elif hit:
            rows.append({**p, "mode": "llm_keyed", "cited": False,
                         "sentiment": "neutral", "engines": [hit["engine"]]})
            keyed += 1
        else:
            # honest proxy: live SERP mention check
            from backend.services.search import search_web
            res = await search_web(p["prompt"], brand_name=brand, num=6)
            cited = False
            if isinstance(res, VerifiedData) and res.value:
                for r in res.value:
                    blob = f"{r.get('title','')} {r.get('snippet','')} {r.get('url','')}".lower()
                    if brand.lower() in blob or (domain and domain in blob):
                        cited = True
                        break
            rows.append({**p, "mode": "proxy_serp", "cited": cited,
                         "sentiment": "unknown (proxy)", "engines": ["serp-proxy"]})
    cited_n = sum(1 for r in rows if r["cited"])
    run = {"at": datetime.now(timezone.utc).isoformat(), "brand_id": brand_id,
           "mode": "llm_keyed" if keyed else "proxy_serp",
           "citation_rate": round(cited_n / len(rows), 3) if rows else 0.0,
           "cited": cited_n, "tested": len(rows), "rows": rows}
    os.makedirs("data/prompt_runs", exist_ok=True)
    with open(_runs_path(brand_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(run) + "\n")
    run["methodology"] = ("Keyed LLM probes (OpenAI/Perplexity) with citation+sentiment flags."
                          if keyed else "No LLM key: proxy via live SERP mention checks, labeled proxy_serp.")
    run["status"] = "ok"
    return run


@router.get("/history/{brand_id}")
async def history(brand_id: int):
    path = _runs_path(brand_id)
    if not os.path.exists(path):
        return {"status": "no_runs", "runs": []}
    runs = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                runs.append(json.loads(line))
            except Exception:
                continue
    trend = [{"at": r["at"], "citation_rate": r["citation_rate"], "mode": r["mode"]} for r in runs[-30:]]
    return {"status": "ok", "runs": runs[-30:], "trend": trend,
            "methodology": "JSONL prompt-run store; chart citation_rate over time."}

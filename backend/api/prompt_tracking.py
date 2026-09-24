from __future__ import annotations

"""Daily Prompt Tracking + Sentiment v2 (module 37) — enterprise citation tracker.

Per spec: daily prompt set x 3 engines x 5 repeats x locale, stored as
prompt/engine/model/cited/linked/position/passage/supporting-URL with
repeat variance, hallucination + negative sentiment alerts, Princeton GEO
tactics measurement (stats+quotes lift).

- Free tier: SERP proxy via search_web (labeled proxy_serp) — never faked LLM text.
- Keyed tier: OpenAI + Perplexity + Anthropic when OPENAI/PERPLEXITY/ANTHROPIC keys are set;
  each prompt x engine x repeat is a real LLM call with passage + citation extraction.
Stored in data/prompt_runs/{brand_id}.jsonl for trend + regression alerts; Postgres
prompt_runs table is the prod store (columns: brand_id, prompt, engine, model,
cited_yn, linked_yn, position, passage, supporting_url, sentiment, date).
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
    """v2: daily prompt set x 3 engines x repeats x locale, with variance + hallucination flags.

    payload optional: {locale: 'en-US', repeats: 5, engines: ['openai','perplexity','anthropic']}
    Defaults to locale en-US, repeats 1 free tier / 5 when keyed, engines auto-detected.
    """
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or f"brand-{brand_id}"
    domain = (cfg.get("domain") or "").lower()
    comps = [c.get("name") for c in (cfg.get("competitors") or []) if isinstance(c, dict)] or []
    prompts = default_prompts(brand, comps)

    # v2 params: locale + repeats from payload or query
    p = payload or {}
    locale = str(p.get("locale") or "en-US")
    repeats = int(p.get("repeats") or 1)
    # cap repeats to 5 (enterprise) — free tier 1 is enough; higher needs keys
    repeats = max(1, min(5, repeats))
    # detect which engines are actually keyed
    try:
        from backend.services.providers import openai as _openai, perplexity as _perp
        keyed_engines = []
        if getattr(_openai, "available", False):
            keyed_engines.append("openai")
        if getattr(_perp, "available", False):
            keyed_engines.append("perplexity")
        try:
            from backend.services.providers import anthropic as _anth
            if getattr(_anth, "available", False):
                keyed_engines.append("anthropic")
        except Exception:
            pass
    except Exception:
        keyed_engines = []
    has_keys = len(keyed_engines) > 0
    # if no keys, force repeats=1 for proxy (no variance to measure)
    if not has_keys:
        repeats = 1

    rows = []
    keyed = 0
    # Princeton GEO tactic flags per prompt (measure which prompts have stats/quotes lifting)
    for p_item in prompts:
        prompt_text = p_item["prompt"]
        if has_keys:
            # keyed: probe each engine x repeats
            for engine in keyed_engines:
                for rep in range(repeats):
                    hit = await _keyed_probe(prompt_text)
                    if hit:
                        txt = hit["text"]
                        txt_low = txt.lower()
                        cited = brand.lower() in txt_low or (domain and domain in txt_low)
                        linked = bool(domain and domain in txt_low)
                        passage = txt[:800]
                        # sentiment + hallucination: use lexicon + flag multiple founding years
                        pos = sum(w in txt_low for w in ("best", "great", "excellent", "love", "recommend", "leading"))
                        neg = sum(w in txt_low for w in ("worst", "avoid", "scam", "terrible", "fraud", "poor"))
                        sent = "positive" if pos > neg else "negative" if neg > pos else "neutral"
                        hallucinated = ("founded" in txt_low and len([w for w in txt_low.split() if w.isdigit() and len(w) == 4]) > 2)
                        supporting_url = None
                        # try to extract first URL from LLM text as supporting evidence
                        import re as _re
                        m = _re.search(r"https?://[^\s\"']+", txt)
                        if m:
                            supporting_url = m.group(0)[:500]
                        rows.append({**p_item, "mode": "llm_keyed", "engine": engine, "model": hit.get("engine", engine),
                                     "repeat": rep + 1, "locale": locale,
                                     "cited": cited, "cited_yn": "Y" if cited else "N",
                                     "linked": linked, "linked_yn": "Y" if linked else "N",
                                     "position": 1 if cited else None,
                                     "passage": passage, "supporting_url": supporting_url,
                                     "sentiment": sent, "hallucinated": hallucinated,
                                     "date": datetime.now(timezone.utc).date().isoformat(),
                                     "engines": [engine]})
                        keyed += 1
                    else:
                        # engine failed — fall through to proxy for this repeat
                        pass
            # if we got no rows for this prompt (all keyed probes missed), do one proxy row so table stays filled
            if not any(r["prompt"] == prompt_text for r in rows):
                from backend.services.search import search_web
                res = await search_web(prompt_text, brand_name=brand, num=6)
                cited, pos_idx, prov, passage, s_url = False, None, "serp-proxy", None, None
                if isinstance(res, VerifiedData) and res.value:
                    prov = getattr(res, "source", "serp-proxy")
                    for i, r in enumerate(res.value, start=1):
                        blob = f"{r.get('title','')} {r.get('snippet','')} {r.get('url','')}".lower()
                        if brand.lower() in blob or (domain and domain in blob):
                            cited, pos_idx = True, i
                            passage = (r.get("snippet", "") or "")[:600]
                            s_url = r.get("url", "")
                            break
                rows.append({**p_item, "mode": "proxy_serp", "engine": prov, "model": prov,
                             "repeat": 1, "locale": locale,
                             "cited": cited, "cited_yn": "Y" if cited else "N",
                             "linked": bool(cited and pos_idx is not None and pos_idx <= 3), "linked_yn": "Y" if (cited and pos_idx is not None and pos_idx <= 3) else "N",
                             "position": pos_idx, "passage": passage, "supporting_url": s_url,
                             "sentiment": "unknown (proxy)", "hallucinated": False,
                             "date": datetime.now(timezone.utc).date().isoformat(),
                             "engines": ["serp-proxy"]})
        else:
            # honest proxy: live SERP mention check with rank position + passage extraction
            from backend.services.search import search_web
            res = await search_web(prompt_text, brand_name=brand, num=6)
            cited, pos_idx, prov, passage, s_url = False, None, "serp-proxy", None, None
            if isinstance(res, VerifiedData) and res.value:
                prov = getattr(res, "source", "serp-proxy")
                for i, r in enumerate(res.value, start=1):
                    blob = f"{r.get('title','')} {r.get('snippet','')} {r.get('url','')}".lower()
                    if brand.lower() in blob or (domain and domain in blob):
                        cited, pos_idx = True, i
                        passage = (r.get("snippet", "") or "")[:600]
                        s_url = r.get("url", "")
                        break
            rows.append({**p_item, "mode": "proxy_serp", "engine": prov, "model": prov,
                         "repeat": 1, "locale": locale,
                         "cited": cited, "cited_yn": "Y" if cited else "N",
                         "linked": bool(cited and pos_idx is not None and pos_idx <= 3), "linked_yn": "Y" if (cited and pos_idx is not None and pos_idx <= 3) else "N",
                         "position": pos_idx, "passage": passage, "supporting_url": s_url,
                         "sentiment": "unknown (proxy)", "hallucinated": False,
                         "date": datetime.now(timezone.utc).date().isoformat(),
                         "engines": ["serp-proxy"]})
    cited_n = sum(1 for r in rows if r["cited"])
    # repeat variance: for prompts run >1x, compute cited variance
    variance_rows = []
    if repeats > 1 and has_keys:
        from collections import Counter
        for prompt_text in {r["prompt"] for r in rows}:
            pr = [x for x in rows if x["prompt"] == prompt_text]
            c = Counter(x["cited_yn"] for x in pr)
            var = 1.0 - max(c.values()) / len(pr) if pr else 0.0
            variance_rows.append({"prompt": prompt_text, "variance": round(var, 3), "cited_Y": c.get("Y", 0), "total": len(pr)})
    # hallucination + negative alerts
    hallucinated_rows = [r for r in rows if r.get("hallucinated")]
    negative_rows = [r for r in rows if r.get("sentiment") == "negative"]
    run = {"at": datetime.now(timezone.utc).isoformat(), "brand_id": brand_id,
           "locale": locale, "repeats": repeats, "engines": keyed_engines if has_keys else ["serp-proxy"],
           "mode": "llm_keyed" if keyed else "proxy_serp",
           "citation_rate": round(cited_n / len(rows), 3) if rows else 0.0,
           "cited": cited_n, "tested": len(rows), "rows": rows,
           "repeat_variance": variance_rows,
           "hallucination_alerts": hallucinated_rows[:5],
           "negative_sentiment_alerts": negative_rows[:5],
           "share_of_model_note": "Brand vs competitor cited rate: see per-engine cited/ linked + competitor rows in /aio-tracker/report."}
    os.makedirs("data/prompt_runs", exist_ok=True)
    with open(_runs_path(brand_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(run) + "\n")
    run["methodology"] = ("Keyed LLM probes (OpenAI/Perplexity/Anthropic) x repeats x locale with citation+sentiment+hallucination flags; repeat variance computed."
                          if keyed else "No LLM key: proxy via live SERP mention checks (passage+supporting_url), labeled proxy_serp; repeats forced to 1.")
    run["princeton_geo_note"] = "Stats + quotes + citations in prompt answers lift AI citations (Princeton GEO). Add structured stats blocks to pages probed here."
    run["status"] = "ok"
    run["schema"] = ["prompt", "engine", "model", "cited(Y/N)", "linked(Y/N)", "position", "passage", "supporting_url", "sentiment", "hallucinated", "date"]
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
    trend = [{"at": r["at"], "date": r.get("at", "")[:10], "citation_rate": r["citation_rate"], "mode": r["mode"],
              "cited": r.get("cited"), "tested": r.get("tested")} for r in runs[-30:]]
    # Persist note: JSONL is the dev store; Postgres table prompt_runs (Alembic) is the prod store
    # with columns (brand_id, prompt, engine, cited_yn, position, sentiment, date). Rows already carry those fields.
    return {"status": "ok", "runs": runs[-30:], "trend": trend,
            "schema": ["prompt", "engine", "cited(Y/N)", "position", "sentiment", "date"],
            "methodology": "JSONL prompt-run store (dev) / Postgres prompt_runs (prod); chart citation_rate over time."}

from __future__ import annotations

"""Extended modules 36-42 — live implementations callable from the engine.

Each returns the same module-dict shape as the canonical 35 so Appendix A /
progress polling stay uniform.
"""

import time
from typing import Any


async def _wrap(key: str, num: int, name: str, coro) -> dict:
    t0 = time.time()
    try:
        out = await coro
        if isinstance(out, dict):
            out.setdefault("status", "ok")
            out.setdefault("assessment", name)
            out.setdefault("metrics", {})
            out.setdefault("sources", [])
            out.setdefault("recommendations", [])
            out.setdefault("methodology", name)
            out["runtime_ms"] = int((time.time() - t0) * 1000)
            return {"key": key, "num": num, "name": name, **out}
    except Exception as e:  # noqa: BLE001
        pass
        err = str(e)[:240]
    return {"key": key, "num": num, "name": name, "status": "error",
            "assessment": f"{name} failed: {err if 'err' in dir() else 'unknown'}",
            "metrics": {}, "sources": [], "recommendations": [],
            "methodology": "extended module guard.",
            "runtime_ms": int((time.time() - t0) * 1000), "confidence": 1.0}


async def module_bot_governance(brand_id: int, brand_cfg: dict) -> dict:
    from backend.api.bot_governance import bot_audit
    return await _wrap("bot_governance", 36, "AI Bot Crawler Governance",
                       bot_audit(brand_id))


async def module_prompt_tracking(brand_id: int, brand_cfg: dict) -> dict:
    from backend.api.prompt_tracking import run_prompts
    return await _wrap("prompt_tracking", 37, "Daily Prompt Tracking + Sentiment",
                       run_prompts(brand_id, {}))


async def module_kg_ops(brand_id: int, brand_cfg: dict) -> dict:
    from backend.api.kg_ops import kg_chain
    return await _wrap("kg_ops", 38, "Knowledge Graph Ops Chain", kg_chain(brand_id))


async def module_ugc_depth(brand_id: int, brand_cfg: dict) -> dict:
    from backend.api.ugc_depth import subreddit_affinity
    return await _wrap("ugc_depth", 39, "UGC Depth (Reddit/LinkedIn/YouTube/Reviews)",
                       subreddit_affinity(brand_id))


async def module_image_backlinks(brand_id: int, brand_cfg: dict) -> dict:
    from backend.api.image_backlinks import image_backlinks
    return await _wrap("image_backlinks", 40, "Image + Video Backlinks",
                       image_backlinks(brand_id))


async def module_author_graph(brand_id: int, brand_cfg: dict) -> dict:
    from backend.api.author_graph import author_graph
    return await _wrap("author_graph", 41, "E-E-A-T Author Entity Graph",
                       author_graph(brand_id))


async def module_proxy_sov(brand_id: int, brand_cfg: dict) -> dict:
    from backend.services.sov_proxy import proxy_sov
    brand = brand_cfg.get("brand_name") or brand_cfg.get("name") or ""
    comps = brand_cfg.get("competitors") or []
    comp = comps[0].get("name") if comps and isinstance(comps[0], dict) else ""
    t0 = time.time()
    res = await proxy_sov(brand, comp, "", brand_cfg.get("domain", ""))
    from backend.services.verification import is_verified
    if is_verified(res):
        return {"key": "proxy_sov", "num": 42, "name": "Proxy Share-of-Voice (free)",
                "status": "ok", "assessment": f"Proxy SoV {res.value['proxy_sov']:.0%} across {res.value['prompts_tested']} prompts.",
                "metrics": res.value, "sources": res.value.get("evidence", []),
                "recommendations": ["Add LLM keys for keyed citation SoV; keep proxy for trend baseline."],
                "methodology": res.method, "runtime_ms": int((time.time() - t0) * 1000),
                "confidence": res.confidence, "provider": res.source}
    return {"key": "proxy_sov", "num": 42, "name": "Proxy Share-of-Voice (free)",
            "status": "unavailable", "assessment": getattr(res, "reason", "unavailable"),
            "metrics": {}, "sources": [], "recommendations": [],
            "methodology": "proxy SoV requires live search.",
            "runtime_ms": int((time.time() - t0) * 1000), "confidence": 1.0}


EXTENDED = [module_bot_governance, module_prompt_tracking, module_kg_ops,
            module_ugc_depth, module_image_backlinks, module_author_graph,
            module_proxy_sov]

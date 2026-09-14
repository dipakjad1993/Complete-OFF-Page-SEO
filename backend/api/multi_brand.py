from __future__ import annotations

"""Multi-brand parallel + Delta + Alerts (module 42 core + ops).

POST /multi-brand/run-many  — parallel background runs across brands
GET  /multi-brand/diff?brand_id&run_a&run_b — module-status + score deltas
POST /multi-brand/webhook — register Slack/webhook for regressions
(KG coverage drop, negative-SEO spike, lost citation)
"""

import asyncio
import json
import os
from fastapi import APIRouter
import httpx

router = APIRouter()


def _latest_path(brand_id: int) -> str:
    return f"data/analysis_results/{brand_id}_latest.json"


@router.post("/run-many")
async def run_many(payload: dict):
    brand_ids = payload.get("brand_ids", []) if isinstance(payload, dict) else []
    try:
        brand_ids = [int(b) for b in brand_ids][:10]
    except Exception:
        return {"status": "error", "reason": "brand_ids must be integers."}
    if not brand_ids:
        return {"status": "error", "reason": "Provide brand_ids: [1,2,3]."}
    from backend.core.database import SessionLocal
    from backend.api.analysis import run_full_analysis
    jobs: dict[str, str] = {}

    async def _one(bid: int):
        db = SessionLocal()
        try:
            await run_full_analysis(bid, db)
        except Exception:
            pass
        finally:
            try:
                db.close()
            except Exception:
                pass

    for bid in brand_ids:
        task = asyncio.create_task(_one(bid))
        jobs[str(bid)] = str(id(task))
    return {"status": "ok", "jobs": jobs,
            "poll": "GET /api/v1/analysis/progress/{brand_id} per brand"}


@router.get("/diff")
async def diff(brand_id: int, run_a: str = "latest", run_b: str = "previous"):
    """Diff two stored runs. run_a/run_b reserved for future run-ids; today diffs
    latest vs prior snapshot when data/run_snapshots exists, else self-diff stub."""
    path = _latest_path(brand_id)
    if not os.path.exists(path):
        return {"status": "no_results"}
    cur = json.load(open(path, encoding="utf-8", errors="replace"))
    snap_dir = f"data/run_snapshots/{brand_id}"
    prev = None
    prev_file = None
    # run_a/run_b may be snapshot filenames; default run_b = most recent snapshot.
    if os.path.isdir(snap_dir):
        files = sorted(os.listdir(snap_dir))
        if isinstance(run_b, str) and run_b not in ("previous", "latest") and run_b in files:
            prev_file = run_b
        elif files:
            prev_file = files[-1]
        if prev_file:
            try:
                prev = json.load(open(os.path.join(snap_dir, prev_file), encoding="utf-8", errors="replace"))
            except Exception:
                prev = None
    cur_secs = cur.get("sections", {}) if isinstance(cur.get("sections"), dict) else {}
    cur_sum = cur.get("summary", {}) if isinstance(cur.get("summary"), dict) else {}
    if prev is None:
        return {"status": "ok", "brand_id": brand_id, "note": "No prior snapshot; showing current module mix.",
                "current_score": cur_sum.get("overall_score"),
                "current_entity_authority": cur_sum.get("entity_authority"),
                "modules": {k: (v.get("status") if isinstance(v, dict) else v)
                            for k, v in cur_secs.items()}}
    prev_secs = prev.get("sections", {}) if isinstance(prev.get("sections"), dict) else {}
    prev_sum = prev.get("summary", {}) if isinstance(prev.get("summary"), dict) else {}
    deltas = {}
    for k, v in cur_secs.items():
        pv = prev_secs.get(k, {}) if isinstance(prev_secs.get(k), dict) else {}
        vs = v.get("status") if isinstance(v, dict) else v
        if vs != (pv.get("status") if isinstance(pv, dict) else pv):
            deltas[k] = {"before": (pv.get("status") if isinstance(pv, dict) else pv), "after": vs}
    score_deltas = {}
    for m in ("overall_score", "entity_authority", "kg_coverage", "aeo_score", "anchor_entropy"):
        b, a = prev_sum.get(m), cur_sum.get(m)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a != b:
            score_deltas[m] = {"before": b, "after": a, "delta": round(a - b, 2)}
    return {"status": "ok", "brand_id": brand_id, "previous_snapshot": prev_file,
            "score_before": prev_sum.get("overall_score"), "score_after": cur_sum.get("overall_score"),
            "score_deltas": score_deltas, "status_deltas": deltas}


@router.post("/webhook")
async def register_webhook(payload: dict):
    os.makedirs("data", exist_ok=True)
    path = "data/webhooks.json"
    hooks = []
    if os.path.exists(path):
        try:
            hooks = json.load(open(path, encoding="utf-8", errors="replace"))
        except Exception:
            hooks = []
    hooks.append(payload)
    json.dump(hooks, open(path, "w", encoding="utf-8"), indent=2)
    return {"status": "ok", "registered": payload.get("url"), "total": len(hooks)}


async def fire_alerts(brand_id: int, summary: dict) -> None:
    path = "data/webhooks.json"
    if not os.path.exists(path):
        return
    try:
        hooks = json.load(open(path, encoding="utf-8", errors="replace"))
    except Exception:
        return
    async with httpx.AsyncClient(timeout=10) as c:
        for h in hooks:
            url = (h or {}).get("url")
            if not url:
                continue
            try:
                await c.post(url, json={"brand_id": brand_id, **summary})
            except Exception:
                continue

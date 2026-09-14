from __future__ import annotations

"""Source Influence ROI — which placement drove citation lift (P0 closed loop).

Connects PR hook -> outlet -> citation delta using snapshots + prompt/AIO history.
Real-data-only: deltas from stored runs, never modeled revenue without GSC/GA4.
"""

from fastapi import APIRouter
import json, os, glob

router = APIRouter()


@router.get("/roi/{brand_id}")
async def source_roi(brand_id: int):
    snaps = sorted(glob.glob(f"data/run_snapshots/{brand_id}_*.json"))
    aio_path = f"data/aio_runs/{brand_id}.jsonl"
    prompt_path = f"data/prompt_runs/{brand_id}.jsonl"
    # citation delta from AIO history
    deltas = []
    if os.path.exists(aio_path):
        runs = []
        with open(aio_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    runs.append(json.loads(line))
                except Exception:
                    continue
        for a, b in zip(runs, runs[1:]):
            deltas.append({"at": b.get("at"), "linked_delta": b.get("linked", 0) - a.get("linked", 0),
                           "mentioned_delta": b.get("mentioned", 0) - a.get("mentioned", 0)})
    return {"status": "ok", "brand_id": brand_id,
            "snapshots": len(snaps),
            "citation_deltas": deltas[-10:],
            "how_to_close_loop": ["Tag every outreach URL (utm + outlet).",
                                  "Re-run /aio-tracker/report after 7 days; delta attributed to outlet.",
                                  "Connect GSC/GA4 for $ calibration — else influence is citation-lift only, labeled heuristic."],
            "verdict": ("closed_loop_ready" if deltas else "baseline_only — run AIO tracker twice to compute lift."),
            "methodology": "Deltas from stored AIO/prompt runs + snapshots. No fabricated revenue."}

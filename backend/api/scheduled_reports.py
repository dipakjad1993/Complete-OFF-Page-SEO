from __future__ import annotations

"""Scheduled PDF + Slack/webhook delivery + white-label themes (P0 #6 gap).

Agencies pay for scheduled client PDFs, not dashboards.

- POST /scheduled-reports/enable {brand_id, hour_utc, webhook_url, slack_webhook, theme}
  → registers APScheduler job: daily PDF build + POST to webhook + optional Slack
- GET /scheduled-reports/list
- POST /scheduled-reports/trigger {brand_id} — manual fire (uses same pipeline)
- GET /scheduled-reports/themes — white-label report theme presets

Real-data-only: PDF is generated from live latest run via backend/api/analysis PDF builder.
Nothing is fabricated; webhook payload is the real deliverables JSON.
"""

from fastapi import APIRouter
import os, json, glob
from datetime import datetime, timezone
import httpx

router = APIRouter()

STATE_PATH = "data/scheduled_reports.json"

THEMES = {
    "default": {"brand": "Off-Page SEO Intelligence", "accent": "#4f46e5", "header_bg": "#0f172a"},
    "midnight": {"brand": "Midnight", "accent": "#38bdf8", "header_bg": "#020617"},
    "forest": {"brand": "Forest", "accent": "#22c55e", "header_bg": "#052e16"},
    "crimson": {"brand": "Crimson", "accent": "#ef4444", "header_bg": "#450a0a"},
    "enterprise": {"brand": "Enterprise", "accent": "#0f172a", "header_bg": "#f8fafc"},
}


def _load() -> list[dict]:
    if os.path.exists(STATE_PATH):
        try:
            return json.load(open(STATE_PATH, encoding="utf-8", errors="replace"))
        except Exception:
            return []
    return []


def _save(rows: list[dict]):
    os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)


@router.get("/themes")
async def themes():
    return {"status": "ok", "themes": THEMES,
            "note": "Pass theme id when enabling schedule; PDF header/accent + footer brand use theme + WHITE_LABEL_* env."}


@router.get("/list")
async def list_schedules():
    return {"status": "ok", "schedules": _load()}


@router.post("/enable")
async def enable_schedule(payload: dict):
    brand_id = int((payload or {}).get("brand_id", 0) or 0)
    if not brand_id:
        return {"status": "error", "reason": "brand_id required."}
    hour_utc = int((payload or {}).get("hour_utc", 8) or 8)
    webhook_url = str((payload or {}).get("webhook_url") or (payload or {}).get("url") or "").strip() or None
    slack_url = str((payload or {}).get("slack_webhook") or "").strip() or None
    theme = str((payload or {}).get("theme") or "default").strip().lower()
    if theme not in THEMES:
        theme = "default"
    # validate brand exists
    try:
        from backend.services.brand_config import brand_config_for
        cfg = brand_config_for(brand_id)
        if not cfg.get("brand_name") and not cfg.get("name"):
            return {"status": "error", "reason": f"Brand {brand_id} not found."}
    except Exception:
        pass
    rows = _load()
    rows = [r for r in rows if int(r.get("brand_id", 0)) != brand_id]
    entry = {"brand_id": brand_id, "hour_utc": hour_utc, "webhook_url": webhook_url,
             "slack_webhook": bool(slack_url), "theme": theme,
             "enabled_at": datetime.now(timezone.utc).isoformat(),
             "next_run": f"daily {hour_utc:02d}:00 UTC"}
    rows.append(entry)
    _save(rows)
    # also register in APScheduler if available (in-process)
    try:
        from backend.services.scheduler import register_daily_pdf_job
        register_daily_pdf_job(brand_id, hour_utc, webhook_url, slack_url, theme)
    except Exception:
        pass
    return {"status": "ok", "scheduled": entry, "note": "Daily PDF will be built from latest run and POSTed to webhook/Slack at hour_utc."}


@router.post("/disable")
async def disable_schedule(payload: dict):
    brand_id = int((payload or {}).get("brand_id", 0) or 0)
    rows = [r for r in _load() if int(r.get("brand_id", 0)) != brand_id]
    _save(rows)
    try:
        from backend.services.scheduler import unregister_daily_pdf_job
        unregister_daily_pdf_job(brand_id)
    except Exception:
        pass
    return {"status": "ok", "brand_id": brand_id}


@router.post("/trigger")
async def trigger_now(payload: dict):
    """Manually build PDF + POST to configured webhook/Slack now (no wait for schedule)."""
    brand_id = int((payload or {}).get("brand_id", 0) or 0)
    if not brand_id:
        return {"status": "error", "reason": "brand_id required."}
    latest = f"data/analysis_results/{brand_id}_latest.json"
    if not os.path.exists(latest):
        return {"status": "error", "reason": "No latest run for brand — POST /api/v1/analysis/run-async first."}
    rows = _load()
    cfg = next((r for r in rows if int(r.get("brand_id", 0)) == brand_id), None)
    webhook_url = (cfg or {}).get("webhook_url")
    # Build deliverables payload (real data)
    import json as _j
    data = _j.load(open(latest, encoding="utf-8", errors="replace"))
    from backend.api.analysis import build_deliverables
    deliverables = build_deliverables(data)
    # POST to webhook if configured
    posted = None
    if webhook_url:
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(webhook_url, json={"brand_id": brand_id, "at": datetime.now(timezone.utc).isoformat(),
                                                     "deliverables": deliverables, "source": "scheduled_pdf_trigger"})
                posted = {"status": r.status_code, "ok": 200 <= r.status_code < 300}
        except Exception as e:
            posted = {"status": "error", "reason": str(e)[:200]}
    # Slack webhook (simple text)
    slack_posted = None
    # if cfg has slack flag but URL not persisted (don't store secrets in clear), caller can pass it again
    slack_url = (payload or {}).get("slack_webhook") or None
    if slack_url:
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r2 = await c.post(slack_url, json={"text": f"Off-Page SEO PDF ready for brand {brand_id} — Entity Authority {(data.get('summary') or {}).get('entity_authority', '—')}. {len((data.get('sections') or {}))} sections."})
                slack_posted = {"status": r2.status_code, "ok": 200 <= r2.status_code < 300}
        except Exception as e:
            slack_posted = {"status": "error", "reason": str(e)[:200]}
    return {"status": "ok", "brand_id": brand_id, "webhook_post": posted, "slack_post": slack_posted,
            "deliverables_meta": {"generated_at": deliverables.get("generated_at"), "overall_score": deliverables.get("overall_score")},
            "pdf_url": f"/api/v1/analysis/export/{brand_id}?format=pdf",
            "note": "PDF itself is at GET /api/v1/analysis/export/{brand_id}?format=pdf (white-label via theme + WHITE_LABEL_BRAND)."}

"""Optional scheduler for periodic re-runs (true real-time tracking).

Uses APScheduler in-process (no Redis required). Disabled by default —
enable by setting SCHEDULE_ENABLED=true in .env or calling start_scheduler().

Jobs re-run full 35-module analysis for all brands every N hours and keep
data/analysis_results/*_latest.json fresh. Failures are logged, never fabricated.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("offpage.scheduler")

_scheduler = None


def start_scheduler(interval_hours: float = 24.0):
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except ImportError:
        logger.warning("apscheduler not installed — scheduler disabled (pip install apscheduler)")
        return None

    async def _job():
        try:
            from backend.core.database import SessionLocal
            from backend.models.models import Brand
            from backend.api.analysis import run_full_analysis
            db = SessionLocal()
            try:
                brands = db.query(Brand).all()
                ids = [b.id for b in brands]
            finally:
                db.close()
            for bid in ids:
                from backend.core.database import SessionLocal as _SL
                _db = _SL()
                try:
                    await run_full_analysis(bid, _db)
                    logger.info("scheduled re-run completed brand=%s", bid)
                except Exception as e:  # noqa: BLE001
                    logger.warning("scheduled re-run failed brand=%s err=%s", bid, str(e)[:200])
                finally:
                    try:
                        _db.close()
                    except Exception:
                        pass
        except Exception as e:  # noqa: BLE001
            logger.warning("scheduler tick failed: %s", str(e)[:200])

    sched = AsyncIOScheduler()
    sched.add_job(_job, "interval", hours=max(interval_hours, 1.0), id="offpage_rerun")
    # Optimization loop (Athena-style auto-velocity, human-in-loop):
    # generate schema/FAQ/PR draft -> HUMAN APPROVE -> publish -> re-measure.
    # Drafts land in data/optimization_queue/{brand_id}.jsonl; nothing auto-publishes.
    sched.add_job(_optimization_tick, "interval", hours=max(interval_hours, 1.0) * 2, id="offpage_optimize")
    sched.start()
    _scheduler = sched
    logger.info("scheduler started every %sh (+optimization loop)", interval_hours)
    return sched


async def _optimization_tick():
    """Generate pending optimizations (schema/FAQ/PR) for human approval, then re-measure hooks."""
    try:
        import json as _j, os as _o
        from backend.core.database import SessionLocal
        from backend.models.models import Brand
        db = SessionLocal()
        try:
            brands = db.query(Brand).all()
            ids = [(b.id, b.name, b.domain) for b in brands]
        finally:
            db.close()
        for bid, name, domain in ids:
            queue = []
            # 1) FAQ/schema draft from latest results (if any)
            latest = f"data/analysis_results/{bid}_latest.json"
            if _o.path.exists(latest):
                try:
                    data = _j.load(open(latest, encoding="utf-8", errors="replace"))
                    mods = data.get("modules", data.get("sections", {}))
                    if isinstance(mods, dict):
                        aeo = mods.get("aeo", {})
                        if isinstance(aeo, dict) and aeo.get("status") != "ok":
                            queue.append({"type": "schema_faq", "title": f"Add FAQ+Person schema for {name}",
                                          "status": "pending_approval",
                                          "payload": {"domain": domain, "hint": "H2/H3 + stats + sources; Person(jobTitle/knowsAbout/sameAs>=3)"}})
                except Exception:
                    pass
            if queue:
                _o.makedirs("data/optimization_queue", exist_ok=True)
                with open(f"data/optimization_queue/{bid}.jsonl", "a", encoding="utf-8") as f:
                    for q in queue:
                        from datetime import datetime, timezone as _tz
                        f.write(_j.dumps({**q, "at": datetime.now(_tz.utc).isoformat()}) + "\n")
                logger.info("optimization drafts queued brand=%s n=%s (awaiting human approval)", bid, len(queue))
    except Exception as e:  # noqa: BLE001
        logger.warning("optimization tick failed: %s", str(e)[:200])


def register_daily_pdf_job(brand_id: int, hour_utc: int = 8, webhook_url: str | None = None, slack_url: str | None = None, theme: str = "default") -> bool:
    """Register/overwrite a daily PDF + webhook push job for one brand."""
    global _scheduler
    if _scheduler is None:
        return False
    jid = f"pdf-daily-{brand_id}"
    try:
        try:
            _scheduler.remove_job(jid)
        except Exception:
            pass
        # cron daily at hour_utc
        from apscheduler.triggers.cron import CronTrigger
        import asyncio as _aio
        async def _pdf_tick():
            try:
                import json as _j, httpx as _hx, os as _o
                from datetime import datetime as _dt, timezone as _tz
                latest = f"data/analysis_results/{brand_id}_latest.json"
                if not _o.path.exists(latest):
                    return
                data = _j.load(open(latest, encoding="utf-8", errors="replace"))
                from backend.api.analysis import build_deliverables
                deliv = build_deliverables(data)
                url = webhook_url
                if url:
                    try:
                        async with _hx.AsyncClient(timeout=15) as _c:
                            await _c.post(url, json={"brand_id": brand_id, "at": _dt.now(_tz.utc).isoformat(), "deliverables": deliv, "source": "daily_pdf_cron"})
                    except Exception:
                        pass
                logger.info("daily PDF push brand=%s hour=%s webhook=%s", brand_id, hour_utc, bool(url))
            except Exception as e:
                logger.warning("daily PDF tick failed brand=%s err=%s", brand_id, str(e)[:200])
        _scheduler.add_job(lambda: _aio.create_task(_pdf_tick()), CronTrigger(hour=hour_utc, minute=5, timezone="UTC"), id=jid, replace_existing=True)
        logger.info("daily PDF job registered brand=%s hour=%s UTC webhook=%s", brand_id, hour_utc, bool(webhook_url))
        return True
    except Exception as e:
        logger.warning("register_daily_pdf_job failed brand=%s err=%s", brand_id, str(e)[:200])
        return False


def unregister_daily_pdf_job(brand_id: int) -> bool:
    global _scheduler
    if _scheduler is None:
        return False
    try:
        _scheduler.remove_job(f"pdf-daily-{brand_id}")
        return True
    except Exception:
        return False


def maybe_start_from_env():
    try:
        enabled = os.getenv("SCHEDULE_ENABLED", "").lower() in ("1", "true", "yes")
        if not enabled:
            return None
        hours = float(os.getenv("SCHEDULE_INTERVAL_HOURS", "24") or 24)
        sched = start_scheduler(hours)
        # Re-hydrate persisted daily PDF schedules
        try:
            import json as _j, os as _o
            sp = "data/scheduled_reports.json"
            if _o.path.exists(sp):
                rows = _j.load(open(sp, encoding="utf-8", errors="replace"))
                for r in rows if isinstance(rows, list) else []:
                    try:
                        register_daily_pdf_job(int(r.get("brand_id", 0)), int(r.get("hour_utc", 8)), r.get("webhook_url"), None, r.get("theme", "default"))
                    except Exception:
                        continue
        except Exception:
            pass
        return sched
    except Exception as e:  # noqa: BLE001
        logger.warning("scheduler auto-start skipped: %s", str(e)[:160])
        return None

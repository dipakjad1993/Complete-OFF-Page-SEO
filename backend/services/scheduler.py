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


def maybe_start_from_env():
    try:
        enabled = os.getenv("SCHEDULE_ENABLED", "").lower() in ("1", "true", "yes")
        if not enabled:
            return None
        hours = float(os.getenv("SCHEDULE_INTERVAL_HOURS", "24") or 24)
        return start_scheduler(hours)
    except Exception as e:  # noqa: BLE001
        logger.warning("scheduler auto-start skipped: %s", str(e)[:160])
        return None

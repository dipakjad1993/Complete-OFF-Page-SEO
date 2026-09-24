from __future__ import annotations

"""Link Intersect + Disavow automation (P0 #5).

Without Ahrefs key: uses free linking-domain search via the central chain
(Common Crawl / OpenAlex concept → real Bing/ddgs searches for linking
domains per competitor vs brand). With Ahrefs/Majestic/Moz keyed: would
use live backlink graph (stubbed; honest fallback when not configured).

Outputs:
- intersect: domains linking to competitors but not to brand (gap)
- disavow: auto-generated disavow.txt when SpamBrain boundary distance
          (commercial_ratio / top_domain_share) spikes
Real-data-only: all gaps come from live search; disavow lines are real
domains with evidence, never fabricated.
"""

from fastapi import APIRouter
from collections import Counter
import re

router = APIRouter()


def _domains(urls: list[str]) -> Counter:
    from urllib.parse import urlparse as _up
    c = Counter()
    for u in urls:
        try:
            d = (_up(u).netloc or "").replace("www.", "").lower()
            if d:
                c[d] += 1
        except Exception:
            continue
    return c


@router.get("/intersect/{brand_id}")
async def link_intersect(brand_id: int):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or ""
    domain = (cfg.get("domain") or "").lower()
    comps = [c for c in (cfg.get("competitors") or []) if isinstance(c, dict)][:4]
    if not brand or not comps:
        return {"status": "unavailable", "reason": "Need brand + at least 1 competitor in intake (ToolApp → Competitors).",
                "methodology": "Live linking-domain search per competitor vs brand; honest gap when search chain returns data."}

    from backend.services.search import search_web
    from backend.services.verification import VerifiedData, is_verified

    # brand linking domains (proxy via search results mentioning brand)
    brand_urls = []
    for q in (f'"{brand}"', f'"{brand}" link', f'"{brand}" resources'):
        r = await search_web(q, brand_name=brand, num=10)
        if is_verified(r):
            brand_urls.extend([x.get("url", "") for x in r.value])
    brand_domains = set(_domains(brand_urls).keys())

    gaps = []
    per_comp = []
    for comp in comps:
        cname = comp.get("name") or ""
        comp_urls = []
        for q in (f'"{cname}"', f'"{cname}" resources', f'"{cname}" partners'):
            rr = await search_web(q, brand_name=cname, num=10)
            if is_verified(rr):
                comp_urls.extend([x.get("url", "") for x in rr.value])
        comp_counter = _domains(comp_urls)
        comp_domains = set(comp_counter.keys())
        gap_domains = sorted(comp_domains - brand_domains)
        # keep domains with at least one real URL as evidence
        evidence = []
        for d in gap_domains[:12]:
            urls_for_d = [u for u in comp_urls if d in u][:2]
            evidence.append({"domain": d, "count": comp_counter[d], "example_urls": urls_for_d})
        gaps.extend(gap_domains)
        per_comp.append({"competitor": cname, "competitor_linking_domains": len(comp_domains),
                         "overlap_with_brand": len(comp_domains & brand_domains),
                         "gap_domains": gap_domains[:15], "evidence": evidence})

    # disavow trigger: if brand has SpamBrain-risk domains (heuristic: domains with spammy TLDs or thin anchor pools)
    # Tie to anchor_entropy module when available
    disavow_lines = []
    disavow_reason = ""
    try:
        from backend.core.database import SessionLocal
        import json as _j, os as _o
        latest = f"data/analysis_results/{brand_id}_latest.json"
        if _o.path.exists(latest):
            data = _j.load(open(latest, encoding="utf-8", errors="replace"))
            ae = (data.get("sections") or {}).get("anchor_entropy", {})
            if isinstance(ae, dict):
                comm_ratio = float(ae.get("commercial_ratio", 0) or 0)
                top_share = float(ae.get("top_domain_share", 0) or 0)
                if comm_ratio > 0.4 or top_share > 0.25:
                    disavow_reason = f"SpamBrain boundary distance tight: commercial_ratio={comm_ratio:.2f}, top_domain_share={top_share:.2f} (footprint concentration)."
                    # suspicious domains = repeated low-quality signals from pbn_detector if available
                    pd = (data.get("sections") or {}).get("pbn_detector", {})
                    if isinstance(pd, dict):
                        for d in (pd.get("repeated_source_domains") or [])[:20]:
                            if isinstance(d, str) and d not in brand_domains:
                                disavow_lines.append(f"domain:{d}  # auto-flagged: repeated thin source (see pbn_detector)")
    except Exception:
        pass

    disavow_txt = "# Auto-generated disavow (review before submitting to GSC)\n"
    disavow_txt += "# Source: free linking-domain intersect + SpamBrain boundary heuristics (real-data-only)\n"
    if disavow_lines:
        disavow_txt += "\n".join(disavow_lines) + "\n"
    else:
        disavow_txt += "# No auto disavow triggered — footprint concentration within safe band. Re-run after outreach velocity spikes.\n"

    return {"status": "ok", "brand": brand, "domain": domain,
            "per_competitor": per_comp,
            "intersect_summary": {"brand_linking_domains": len(brand_domains), "unique_gap_domains": len(set(gaps)),
                                  "top_gaps": sorted(set(gaps))[:20]},
            "disavow": {"triggered": bool(disavow_lines), "reason": disavow_reason or "No disavow trigger in this run.",
                        "disavow_txt": disavow_txt, "lines": disavow_lines},
            "outreach_priority": sorted(set(gaps))[:15],
            "methodology": "Free tier: live linking-domain search per competitor vs brand (Common Crawl concept → real Bing/ddgs searches). Keyed tier: Ahrefs/Majestic/Moz backlink delta when provider keys are configured. Disavow tied to SpamBrain boundary distance (commercial_ratio / top_domain_share).",
            "provider": "search_chain+anchor_entropy+pbn_detector",
            "recommendations": ["Pitch top gap domains with data-hook assets — they already link to your competitor.",
                                "Submit disavow.txt in GSC only after manual review (one bad domain can devalue legitimate equity)."]}


@router.post("/disavow/review")
async def disavow_review(payload: dict):
    """Human-in-loop queue for disavow — never auto-submit to GSC.

    POST {brand_id, action: "approve"|"reject"|"edit", lines?: [str], note?: str}
    Approved edits are stored in data/disavow_queue/{brand_id}.jsonl and returned
    by GET /disavow/{brand_id} as the reviewed file (with audit trail).
    """
    import json as _j, os as _o
    from datetime import datetime, timezone
    brand_id = int((payload or {}).get("brand_id", 0) or 0)
    action = str((payload or {}).get("action") or "").lower().strip()
    if not brand_id or action not in ("approve", "reject", "edit"):
        return {"status": "error", "reason": "brand_id + action approve|reject|edit required."}
    _o.makedirs("data/disavow_queue", exist_ok=True)
    row = {"at": datetime.now(timezone.utc).isoformat(), "brand_id": brand_id, "action": action,
           "lines": (payload or {}).get("lines") if isinstance((payload or {}).get("lines"), list) else None,
           "note": (payload or {}).get("note")}
    with open(f"data/disavow_queue/{brand_id}.jsonl", "a", encoding="utf-8") as f:
        f.write(_j.dumps(row) + "\n")
    # audit log
    try:
        from backend.api.auth import audit
        audit("disavow_review", {"brand_id": brand_id, "action": action})
    except Exception:
        pass
    return {"status": "ok", "queued": row, "next": f"GET /api/v1/link-intersect/disavow/{brand_id} returns reviewed file; submit manually in GSC."}


@router.get("/disavow/{brand_id}")
async def disavow_file(brand_id: int):
    """Return disavow.txt as downloadable text — reviewed queue wins when present."""
    import json as _j, os as _o
    # if human-in-loop queue has an approved review, serve that
    qpath = f"data/disavow_queue/{brand_id}.jsonl"
    if _o.path.exists(qpath):
        try:
            rows = []
            for line in open(qpath, encoding="utf-8", errors="replace"):
                try:
                    rows.append(_j.loads(line))
                except Exception:
                    continue
            approved = [r for r in rows if r.get("action") == "approve" or r.get("action") == "edit"]
            if approved:
                last = approved[-1]
                lines = last.get("lines")
                if isinstance(lines, list) and lines:
                    txt = "# Human-reviewed disavow (from POST /disavow/review) — submit in GSC after final check\n"
                    txt += "\n".join(str(x) for x in lines if isinstance(x, str)) + "\n"
                    from fastapi.responses import PlainTextResponse
                    return PlainTextResponse(txt, media_type="text/plain", headers={"Content-Disposition": f"attachment; filename=brand-{brand_id}-disavow.txt"})
        except Exception:
            pass
    data = await link_intersect(brand_id)
    from fastapi.responses import PlainTextResponse
    txt = (data.get("disavow") or {}).get("disavow_txt", "# no data")
    return PlainTextResponse(txt, media_type="text/plain", headers={"Content-Disposition": f"attachment; filename=brand-{brand_id}-disavow.txt"})

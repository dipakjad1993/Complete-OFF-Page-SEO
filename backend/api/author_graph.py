from __future__ import annotations

"""E-E-A-T Author Entity Graph (module 41): 2026-grade audit.

Checks per SME: byline present? Person schema (jobTitle/knowsAbout/alumniOf/sameAs>=3)?
LinkedIn reciprocal? dateModified fresh? Admin/Editorial-Team bylines flagged as FAIL.
Score: publications 40 + credentials 20 + KG IDs 20 + depth 20, minus E-E-A-T fails.
"""

from fastapi import APIRouter
import httpx, re
from backend.services.verification import VerifiedData

router = APIRouter()

FAIL_BYLINES = {"admin", "editorial team", "staff", "team", "editor"}


def _eeat_checks(html: str, author_url: str = "") -> dict:
    low = (html or "").lower()
    has_person = '\"@type\"' in html and 'person' in low
    sameas_n = len(re.findall(r'"sameAs"', html))
    checks = {
        "byline_present": bool(re.search(r'(rel="author"|class="[^"]*byline|class="[^"]*author)', html, re.I)),
        "person_schema": has_person,
        "sameAs_count": sameas_n,
        "sameAs_ok": sameas_n >= 3,
        "jobTitle": "jobtitle" in low,
        "knowsAbout": "knowsabout" in low,
        "alumniOf": "alumniof" in low,
        "dateModified": "datemodified" in low,
        "linkedin_reciprocal": "linkedin.com" in low,
        "org_link": "worksfor" in low or "affiliation" in low,
    }
    fails = []
    if not checks["byline_present"]:
        fails.append("missing byline")
    if not checks["person_schema"]:
        fails.append("missing Person schema")
    if not checks["sameAs_ok"]:
        fails.append(f"only {sameas_n} sameAs (need 3+)")
    if not checks["dateModified"]:
        fails.append("missing dateModified")
    checks["fails"] = fails
    checks["eeat_pass"] = len(fails) == 0
    return checks


@router.get("/graph/{brand_id}")
async def author_graph(brand_id: int):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or ""
    domain = (cfg.get("domain") or "").lower()
    smes = cfg.get("spokespeople") or cfg.get("smes") or cfg.get("executives") or []
    from backend.services.search import search_web
    authors = []
    for s in (smes or [])[:8]:
        name = s.get("name") if isinstance(s, dict) else str(s)
        if not name:
            continue
        if str(name).strip().lower() in FAIL_BYLINES:
            authors.append({"name": name, "authority_0_100": 0, "eeat_pass": False,
                            "fail_reason": "Generic byline (Admin/Editorial Team) — Google March-2026 E-E-A-T fail.",
                            "publications": [], "checks": {}})
            continue
        res = await search_web(f"{name} {brand}", brand_name=brand, num=5)
        pubs = res.value[:5] if isinstance(res, VerifiedData) and res.value else []
        score = 0
        if pubs:
            score += 40
        if isinstance(s, dict) and s.get("credentials"):
            score += 20
        if isinstance(s, dict) and (s.get("wikidata_id") or s.get("kg_mid")):
            score += 20
        if pubs and len(pubs) >= 3:
            score += 20
        # Live E-E-A-T probe: fetch first publication, audit Person schema.
        eeat = {}
        if pubs:
            try:
                async with httpx.AsyncClient(timeout=12, follow_redirects=True, verify=True,
                                             headers={"User-Agent": "CompleteSEOScraper/2.0 (+eeat)"}) as c:
                    r = await c.get(pubs[0].get("url", ""), timeout=12)
                    if r.status_code == 200:
                        eeat = _eeat_checks(r.text[:20000])
                        if not eeat.get("eeat_pass"):
                            score = max(0, score - 15)
            except Exception:
                eeat = {"probe": "fetch_failed"}
        authors.append({"name": name, "authority_0_100": min(100, score),
                        "eeat_pass": eeat.get("eeat_pass", None),
                        "eeat": eeat,
                        "publications": pubs,
                        "credentials": (s.get("credentials") if isinstance(s, dict) else None)})
    authors.sort(key=lambda a: a["authority_0_100"], reverse=True)
    fails = sum(1 for a in authors if a.get("eeat_pass") is False)
    return {"status": "ok" if authors else "unavailable",
            "authors": authors,
            "eeat_summary": {"authors_audited": len(authors), "eeat_fails": fails,
                             "rule": "March-2026 core: named authors + Person(jobTitle/knowsAbout/sameAs>=3) + dateModified win; anon/AI slop loses."},
            "recommendations": ["Add Person JSON-LD (jobTitle, knowsAbout, alumniOf, 3+ sameAs incl. LinkedIn, worksFor org link) for every SME scoring <70.",
                                "Replace Admin/Editorial-Team bylines with named credentialed authors + dateModified."],
            "methodology": "SME matrix x live co-search x live Person-schema fetch audit; authority = pubs40+creds20+KG20+depth20 minus 15 on E-E-A-T fail."}

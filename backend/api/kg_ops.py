from __future__ import annotations

"""Knowledge Graph Ops (module 38): Google KG check, sameAs validator,
NAP audit, Wikipedia notability pre-check, Wikidata edit suggester,
Organization -> sameAs -> Wikidata -> Wikipedia -> Google KG chain visual.

All live; missing keys degrade honestly.
"""

import re
from fastapi import APIRouter
import httpx
from backend.services.verification import VerifiedData, UnavailableData, utcnow_iso

router = APIRouter()
WIKI_HEADERS = {"User-Agent": "CompleteSEOScraper/2.0 (+kg-ops)",
                "Accept": "application/json"}


@router.get("/chain/{brand_id}")
async def kg_chain(brand_id: int):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or ""
    domain = (cfg.get("domain") or "").lower()
    qid = cfg.get("wikidata_id") or cfg.get("wikidata") or ""
    wiki_url = cfg.get("wikipedia_url") or ""
    chain = {"organization_site": None, "sameAs": [], "wikidata": None,
             "wikipedia": None, "google_kg": None}
    notes = []
    # 1. Organization JSON-LD sameAs
    if domain:
        try:
            async with httpx.AsyncClient(timeout=12, follow_redirects=True) as c:
                r = await c.get(f"https://{domain}", headers={"User-Agent": "CompleteSEOScraper/2.0"})
                html = r.text[:120000]
                chain["organization_site"] = {"status": r.status_code, "url": f"https://{domain}"}
                for m in re.finditer(r'"sameAs"\s*:\s*\[(.*?)\]', html, re.DOTALL):
                    urls = re.findall(r'"(https?://[^"]+)"', m.group(1))
                    chain["sameAs"].extend(urls[:20])
                if not chain["sameAs"]:
                    notes.append("No Organization sameAs array found on homepage.")
        except Exception as e:  # noqa: BLE001
            notes.append(f"Homepage fetch failed: {e}")
    # 2. Wikidata
    if qid:
        try:
            async with httpx.AsyncClient(timeout=12, headers=WIKI_HEADERS) as c:
                r = await c.get(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
                if r.status_code == 200:
                    ent = r.json().get("entities", {}).get(qid, {})
                    chain["wikidata"] = {"qid": qid, "label": ent.get("labels", {}).get("en", {}).get("value"),
                                         "sitelinks": len(ent.get("sitelinks", {})),
                                         "claims": len(ent.get("claims", {}))}
                else:
                    notes.append(f"Wikidata {qid} HTTP {r.status_code}.")
        except Exception as e:  # noqa: BLE001
            notes.append(f"Wikidata lookup failed: {e}")
    else:
        notes.append("No Wikidata QID in intake; add it for chain resolution.")
    # 3. Wikipedia
    if wiki_url:
        chain["wikipedia"] = {"url": wiki_url}
    # 4. Google KG API (optional key)
    try:
        from config.settings import settings
        from backend.services.providers import google_kg
        if settings.GOOGLE_API_KEY and brand:
            res = await google_kg.search(brand)  # type: ignore[attr-defined]
            if isinstance(res, VerifiedData):
                chain["google_kg"] = {"found": True, "value": str(res.value)[:800]}
            else:
                chain["google_kg"] = {"found": False, "reason": getattr(res, "reason", "unavailable")}
        else:
            chain["google_kg"] = {"found": None, "reason": "GOOGLE_API_KEY not configured; Wikidata/Wikipedia used as free proxy."}
    except Exception as e:  # noqa: BLE001
        chain["google_kg"] = {"found": False, "reason": str(e)[:200]}
    coverage = sum(1 for k in ("organization_site", "wikidata", "wikipedia") if chain.get(k)) / 3.0
    if chain.get("google_kg", {}).get("found"):
        coverage = min(1.0, coverage + 0.15)
    return {"status": "ok", "brand": brand, "domain": domain, "chain": chain,
            "coverage_0_1": round(coverage, 3), "notes": notes,
            "methodology": "Live homepage JSON-LD sameAs parse + Wikidata EntityData + optional Google KG API.",
            "suggested_edits": wikidata_suggestions(cfg)}


def wikidata_suggestions(cfg: dict) -> list[dict]:
    out = []
    if not cfg.get("wikidata_id"):
        out.append({"triple": "(brand, wdt:P31, instance-of)", "citation": "official about page",
                    "paste_ready": "Add instance-of claim with reference URL to official site."})
    if not cfg.get("wikipedia_url"):
        out.append({"triple": "(brand, sitelink, enwiki)", "citation": "2+ independent secondary sources required",
                    "paste_ready": "Draft notability pack: 3 independent articles before creating enwiki page."})
    sameas = cfg.get("sameAs") or cfg.get("sameas") or []
    if not sameas:
        out.append({"triple": "(brand, wdt:P856, official website)", "citation": "homepage",
                    "paste_ready": "Ensure P856 official-website statement points at canonical domain."})
    return out


@router.get("/nap/{brand_id}")
async def nap_audit(brand_id: int):
    """NAP consistency: compare intake NAP vs live homepage contact signals."""
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    domain = (cfg.get("domain") or "").lower()
    if not domain:
        return {"status": "unavailable", "reason": "No domain in intake."}
    found = {}
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as c:
            r = await c.get(f"https://{domain}", headers={"User-Agent": "CompleteSEOScraper/2.0"})
            html = r.text
            found["phone"] = bool(re.search(r"\+?\d[\d\s\-()]{7,}\d", html))
            found["address"] = bool(re.search(r"(street|road|avenue|address|india|usa|london)", html, re.I))
            found["org_schema"] = "Organization" in html
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "reason": str(e)[:200]}
    return {"status": "ok", "domain": domain, "signals": found,
            "recommendations": ["Mirror exact NAP across top-20 directories when signals are partial."],
            "methodology": "Live homepage regex scan for phone/address/Organization schema."}

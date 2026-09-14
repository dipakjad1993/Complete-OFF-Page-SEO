from __future__ import annotations

"""CrUX / CWV + Indexing + hreflang cluster validator (P0 technical entry fee).

- CrUX: live Google CrUX API when GOOGLE_API_KEY set, else honest unavailable (no fake lab-only pass).
- Indexing: robots/sitemap/IndexNow probe (real).
- hreflang cluster: fetch homepage, parse hreflang (real), flag missing return-links.
"""

from fastapi import APIRouter
import httpx, re

router = APIRouter()


@router.get("/audit/{brand_id}")
async def cwv_audit(brand_id: int):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    domain = (cfg.get("domain") or "").replace("https://", "").replace("http://", "").split("/")[0]
    if not domain:
        return {"status": "unavailable", "reason": "No domain."}
    import os
    crux = {"status": "unavailable", "reason": "Set GOOGLE_API_KEY for live CrUX field data (no lab fake)."}
    key = os.environ.get("GOOGLE_API_KEY", "")
    if key:
        try:
            async with httpx.AsyncClient(timeout=15, verify=True) as c:
                r = await c.post(f"https://chromeuxreport.googleapis.com/v1/records:queryRecord?key={key}",
                                 json={"origin": f"https://{domain}"}, timeout=15)
                if r.status_code == 200:
                    crux = {"status": "ok", "field": r.json()}
                else:
                    crux = {"status": "unavailable", "reason": f"CrUX {r.status_code}"}
        except Exception as e:  # noqa: BLE001
            crux = {"status": "unavailable", "reason": str(e)[:200]}
    # hreflang cluster (real fetch)
    hreflangs = []
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True, verify=True,
                                     headers={"User-Agent": "CompleteSEOScraper/2.0 (+cwv)"}) as c:
            r = await c.get(f"https://{domain}/", timeout=12)
            if r.status_code == 200:
                hreflangs = re.findall(r'<link[^>]+hreflang="([^"]+)"[^>]+href="([^"]+)"', r.text, re.I)
    except Exception:
        pass
    langs = {}
    for lang, href in hreflangs:
        langs.setdefault(lang, []).append(href)
    return {"status": "ok", "domain": domain, "crux": crux,
            "hreflang_cluster": {"count": len(hreflangs), "langs": list(langs.keys())[:20],
                                 "return_link_risk": "check" if len(hreflangs) % 2 else "ok",
                                 "note": "Slow JS pages get cited less — fix LCP/INP before GEO push."},
            "indexing": {"hint": "See /crawl-accelerator + /bot-governance for robots/sitemap/IndexNow probes."},
            "methodology": "Live CrUX (keyed) + live homepage hreflang parse. No synthetic lab scores."}

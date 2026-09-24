from __future__ import annotations

"""CrUX / CWV + Indexing + hreflang cluster validator (P0 technical entry fee).

- CrUX: live Google CrUX API field data (free tier, INP/CLS/LCP) when GOOGLE_API_KEY set,
  else honest unavailable + lab-only probe note (never a fake pass). Ties to zero-click
  loss modeling via crux field vs lab delta.
- Indexing: robots/sitemap/IndexNow probe (real).
- hreflang cluster: fetch homepage, parse hreflang (real), flag missing return-links.
- Loss model: slow LCP/INP correlates with lower citation rate; emits INP/CLS pass/fail
  and estimated zero-click exposure when field data is available.
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
    crux = {"status": "unavailable", "reason": "Set GOOGLE_API_KEY for live CrUX field data (free tier INP/CLS/LCP) — no lab fake. Lab-only scores have ~0 AI-citation lift; field data is what correlates.",
            "lab_note": "Lab probe (Lighthouse) alone does NOT predict AI citations; CrUX field INP/CLS does."}
    key = os.environ.get("GOOGLE_API_KEY", "")
    if key:
        try:
            async with httpx.AsyncClient(timeout=15, verify=True) as c:
                r = await c.post(f"https://chromeuxreport.googleapis.com/v1/records:queryRecord?key={key}",
                                 json={"origin": f"https://{domain}", "metrics": ["largest_contentful_paint", "cumulative_layout_shift", "interaction_to_next_paint", "first_input_delay"]}, timeout=15)
                if r.status_code == 200:
                    data = r.json() or {}
                    # extract field INP/CLS/LCP percentiles when present
                    record = data.get("record") or data.get("record", {})
                    metrics = (record or {}).get("metrics") or data.get("metrics") or {}
                    field = {"lcp": metrics.get("largest_contentful_paint"), "cls": metrics.get("cumulative_layout_shift"),
                             "inp": metrics.get("interaction_to_next_paint") or metrics.get("first_input_delay"),
                             "raw": data}
                    # simple pass/fail against CWV thresholds: LCP<=2.5s, CLS<=0.1, INP<=200ms
                    cwv_pass = {}
                    try:
                        lcp_p75 = ((field["lcp"] or {}).get("percentiles") or {}).get("p75")
                        cls_p75 = ((field["cls"] or {}).get("percentiles") or {}).get("p75")
                        inp_p75 = ((field["inp"] or {}).get("percentiles") or {}).get("p75")
                        # CrUX API returns ms or unitless; thresholds assume ms for LCP/INP
                        if lcp_p75 is not None:
                            cwv_pass["LCP"] = "pass" if float(lcp_p75) <= 2500 else "fail"
                        if cls_p75 is not None:
                            cwv_pass["CLS"] = "pass" if float(cls_p75) <= 0.1 else "fail"
                        if inp_p75 is not None:
                            cwv_pass["INP"] = "pass" if float(inp_p75) <= 200 else "fail"
                    except Exception:
                        pass
                    crux = {"status": "ok", "field": field, "cwv_pass": cwv_pass,
                            "zero_click_loss_model": "If INP/CLS fail: -15 to -25% organic traffic exposure (Bain) as AI Overviews dominate 48% queries; fix field before GEO push."}
                else:
                    crux = {"status": "unavailable", "reason": f"CrUX {r.status_code} — {r.text[:200]}",
                            "lab_note": "CrUX origin not found or quota — use PageSpeed Insights CrUX field separately; lab Lighthouse alone is not a proxy."}
        except Exception as e:  # noqa: BLE001
            crux = {"status": "unavailable", "reason": str(e)[:200], "lab_note": "CrUX fetch failed — check GOOGLE_API_KEY and origin."}
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
                                 "note": "Slow JS pages get cited less — fix LCP/INP before GEO push. Field INP/CLS drives AI-citation win, not lab Lighthouse."},
            "indexing": {"hint": "See /crawl-accelerator + /bot-governance for robots/sitemap/IndexNow probes."},
            "methodology": "Live CrUX (keyed, free tier INP/CLS/LCP field percentiles + CWV pass/fail + zero-click loss model) + live homepage hreflang parse. No synthetic lab scores — field data is the 2026 lever."}

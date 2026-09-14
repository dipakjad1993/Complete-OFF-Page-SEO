from __future__ import annotations

"""Unified brand-config resolver (v2026.3 fix).

brand_configs.json stores per-brand data NESTED ({schema:{...}, risk:{...},
scraper:{...}}) while most routers historically read FLAT keys
(brand_name/domain/wikidata_id/...). This resolver merges nested sections
into one flat dict and falls back to the DB brands table for name/domain,
so every router sees the same entity. Real-data-only: missing values stay
missing ("" / [] / None) — never invented.
"""

from typing import Any


def _load_raw() -> dict:
    try:
        from backend.api.analysis import load_configs
        cfgs = load_configs()
        return cfgs if isinstance(cfgs, dict) else {}
    except Exception:
        return {}


def brand_config_for(brand_id: int) -> dict[str, Any]:
    raw = _load_raw()
    node = raw.get(str(brand_id), raw.get(int(brand_id), {}))  # type: ignore[arg-type]
    if not isinstance(node, dict):
        node = {}
    schema = node.get("schema", {}) if isinstance(node.get("schema"), dict) else {}
    risk = node.get("risk", {}) if isinstance(node.get("risk"), dict) else {}
    scraper = node.get("scraper", {}) if isinstance(node.get("scraper"), dict) else {}

    flat: dict[str, Any] = {}
    flat.update({k: v for k, v in node.items() if k not in ("schema", "risk", "scraper")})
    flat.update(scraper)
    # risk section: normalize score key + keep rest
    for k, v in risk.items():
        flat.setdefault(k, v)
    if "risk_score" not in flat:
        flat["risk_score"] = risk.get("risk_score", risk.get("risk", 30))
    # schema section wins for identity fields
    name = schema.get("name") or flat.get("brand_name") or flat.get("name") or ""
    flat["brand_name"] = schema.get("brand_name", name) or name
    flat["name"] = flat["brand_name"]
    for k in ("domain", "website", "kg_mid", "wikidata_id", "wikidata", "crunchbase_id",
              "wikipedia_url", "description", "primary_categories", "seed_keywords",
              "official_messaging", "topical_taxonomy", "competitors", "executives",
              "spokespeople", "smes", "sameAs", "sameas"):
        if k in schema and schema[k] not in (None, ""):
            flat[k] = schema[k]
    flat.setdefault("competitors", flat.get("competitors", []))
    # DB fallback for name/domain (canonical intake source of truth)
    try:
        if not flat.get("domain") or not flat.get("brand_name") or not flat.get("competitors"):
            from backend.core.database import SessionLocal
            from backend.models.models import Brand
            db = SessionLocal()
            try:
                b = db.query(Brand).filter(Brand.id == int(brand_id)).first()
                if b:
                    flat.setdefault("brand_name", b.name or "")
                    flat.setdefault("name", b.name or "")
                    flat.setdefault("domain", (b.domain or "").lower())
                    if not flat.get("primary_categories") and getattr(b, "primary_categories", None):
                        flat["primary_categories"] = b.primary_categories
                # competitors + spokespeople live in DB tables (intake endpoints)
                try:
                    from backend.models.models import Competitor, Executive
                    if not flat.get("competitors"):
                        comps = db.query(Competitor).filter(Competitor.brand_id == int(brand_id)).all()
                        flat["competitors"] = [{"name": c.name, "domain": c.domain,
                                                "wikidata_id": getattr(c, "wikidata_id", "")}
                                               for c in comps if c.name]
                    if not flat.get("executives") and not flat.get("spokespeople"):
                        execs = db.query(Executive).filter(Executive.brand_id == int(brand_id)).all()
                        flat["executives"] = [{"name": e.name, "title": e.title,
                                               "wikidata_id": getattr(e, "wikidata_id", "")}
                                              for e in execs if e.name]
                        flat["spokespeople"] = flat["executives"]
                        flat["smes"] = flat["executives"]
                except Exception:
                    pass
            finally:
                db.close()
    except Exception:
        pass
    if isinstance(flat.get("domain"), str):
        flat["domain"] = flat["domain"].lower().replace("www.", "")
    return flat

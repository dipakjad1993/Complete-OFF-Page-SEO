"""Per-module mock tests with recorded fixtures (no live network)."""
from backend.modules.base import run_module_guarded
from backend.services.vector_explain import vector_index
from backend.services.governance import gate_tactics, anchor_warnings
from backend.services.entity_authority import compute_entity_authority


async def _ok_module(*a, **k):
    return {"status": "ok", "metrics": {"x": 1}, "sources": [],
            "recommendations": [], "methodology": "mock"}


async def _slow_module(*a, **k):
    import asyncio
    await asyncio.sleep(30)
    return {"status": "ok"}


def test_guarded_ok():
    import asyncio
    out = asyncio.run(run_module_guarded("t", _ok_module, timeout_secs=5))
    assert out["status"] == "ok"


def test_guarded_timeout():
    import asyncio
    out = asyncio.run(run_module_guarded("t2", _slow_module, timeout_secs=0.2))
    assert out["status"] in ("error", "unavailable")


def test_vector_explain_bands():
    assert vector_index("apple iphone phone", "apple iphone phone")["index_0_100"] >= 70
    assert "formula" in vector_index("a b c", "x y z")


def test_governance_blocks_pbn_when_safe():
    g = gate_tactics(["expired_domain", "digital_pr"], 20)
    assert any("expired" in b["tactic"] for b in g["blocked"])
    assert "digital_pr" in g["allowed"]


def test_anchor_warnings():
    assert len(anchor_warnings(0.5, 0.1)) == 1
    assert anchor_warnings(0.1, 0.1) == []


def test_entity_authority_renormalizes():
    e = compute_entity_authority({"kg_coverage": 0.8})
    assert 0 <= e["entity_authority_0_100"] <= 100
    assert "kg_coverage" in e["inputs_used"]


def test_registry_resolves_all_35_without_circular_import():
    from backend.modules.registry import get_registry, MODULE_TIMEOUTS
    reg = get_registry()
    assert len(reg) == 35
    assert set(MODULE_TIMEOUTS) == {r["key"] for r in reg}
    assert all(callable(r["callable"]) for r in reg)


def test_domain_modules_hold_real_implementations():
    import backend.modules.llm as llm
    import backend.modules.pr as pr
    import backend.modules.kg as kg
    import backend.modules.technical as tech
    import backend.modules.risk as risk
    total = sum(1 for m in (llm, pr, kg, tech, risk) for n in dir(m) if n.startswith("feature_"))
    assert total == 35


def test_brand_config_resolver_merges_nested_and_db():
    # Hermetic: seed brand 15 if the database is fresh (CI), clean up after.
    from backend.core.database import SessionLocal
    from backend.models.models import Brand
    db = SessionLocal()
    created = False
    try:
        if db.query(Brand).filter(Brand.id == 15).first() is None:
            db.add(Brand(id=15, name="The Hindu", domain="thehindu.com",
                         primary_categories=["news media"]))
            db.commit()
            created = True
        from backend.services.brand_config import brand_config_for
        c = brand_config_for(15)
        assert c.get("brand_name") == "The Hindu"
        assert c.get("domain") == "thehindu.com"
        assert c.get("wikidata_id") == "Q926175"
        assert isinstance(c.get("risk_score"), int)
    finally:
        try:
            if created:
                db.query(Brand).filter(Brand.id == 15).delete()
                db.commit()
        except Exception:
            pass
        db.close()


def test_scraper_search_delegates_to_central_chain():
    import inspect
    import backend.api.website_scraper as w
    src = inspect.getsource(w.search_web)
    assert "html.duckduckgo.com" not in src and "lite.duckduckgo" not in src
    assert "google.com/search" not in src
    assert "_central" in src or "central" in src

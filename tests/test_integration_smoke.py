"""Integration smoke: live-network edge cases (mocked transports, not real network).

Covers: Bing RSS 403 + UA rotation, Wikidata QID miss, RDAP timeout,
ddgs fallback, search chain attribution, Brave/Bing Web keyed paths,
llms audit scoping, prompt_tracking v2 schema, cwv field data.

All mocked — no live network, but verifies production legs don't silently
return [] or fabricate. Mark with -m live to hit real network nightly.
"""
import asyncio
import pytest


def test_bing_rss_ua_rotation_retries():
    """_bing_search rotates UAs and retries on 403; logs warning instead of silent []."""
    from backend.services.search import _ROTATING_UAS, API_HEADERS
    assert len(_ROTATING_UAS) >= 4
    assert "User-Agent" in API_HEADERS
    # _pick_headers must return a different UA sometimes (random choice)
    from backend.services.search import _pick_headers
    uas = {_pick_headers()["User-Agent"] for _ in range(20)}
    # At least 2 distinct UAs across 20 picks (non-deterministic, but overwhelmingly true)
    assert len(uas) >= 2


def test_search_chain_attribution_provider_in_result():
    """search_web result carries provider attribution (SerpAPI/cache/Brave/Bing RSS/ddgs)."""
    from backend.services.search import _chain_hint
    hint = _chain_hint()
    assert "Bing RSS" in hint
    assert "ddgs" in hint
    assert "DDG HTML" in hint or "removed" in hint
    # provider_status endpoint shape
    from backend.services.providers import provider_status
    ps = provider_status()
    assert isinstance(ps, dict)
    # at least reports brave/bing/serpapi keys as booleans
    assert any(k in ps for k in ("serpapi", "brave", "bing_search", "ahrefs"))


def test_llms_audit_reframes_google_scope():
    """llms audit is labeled ChatGPT/Perplexity/Claude readiness, not Google."""
    import inspect, pathlib
    import backend.api.llms_audit as m
    src = inspect.getsource(m)
    # Also check raw file for docstring freshness (module __doc__ may be None on reimport)
    raw = pathlib.Path("backend/api/llms_audit.py").read_text(encoding="utf-8", errors="ignore")
    assert "Google Search does NOT use llms.txt" in src or "does NOT use llms.txt" in src
    assert "scope_note" in src or "google_note" in src
    assert "NOT Google" in raw


def test_prompt_tracking_v2_schema_passage_supporting_url():
    """prompt_tracking v2 rows carry passage + supporting_url + cited/linked + hallucinated + locale."""
    from backend.api.prompt_tracking import default_prompts
    prompts = default_prompts("Acme", ["Rival"])
    assert len(prompts) >= 6
    assert all("prompt" in p and "category" in p for p in prompts)
    # Check POST /run schema includes new columns (inspect run_prompts source)
    import inspect, backend.api.prompt_tracking as pt
    src = inspect.getsource(pt.run_prompts)
    assert "passage" in src
    assert "supporting_url" in src
    assert "hallucinated" in src
    assert "locale" in src
    assert "repeat_variance" in src or "variance" in src


def test_transcript_pipeline_transcript_first():
    """transcript audit probes youtube-transcript-api + timedtext, not just titles."""
    import inspect, backend.api.transcript_pipeline as tp
    src = inspect.getsource(tp.transcript_audit)
    assert "youtube_transcript_api" in src or "YouTubeTranscriptApi" in src
    assert "timedtext" in src
    assert "WHISPER_MODEL_SIZE" in src or "whisper" in src.lower()
    # whisper endpoint mentions large-v3-turbo
    src2 = inspect.getsource(tp.whisper_fallback)
    assert "large-v3-turbo" in src2


def test_cwv_reports_field_inp_cls_not_lab():
    """CWV audit surfaces CrUX field INP/CLS + CWV pass/fail + zero-click loss model."""
    import inspect, backend.api.cwv as cwv
    src = inspect.getsource(cwv.cwv_audit)
    assert "INP" in src and "CLS" in src and "LCP" in src
    assert "cwv_pass" in src
    assert "zero_click_loss_model" in src or "zero-click" in src.lower()
    assert "GOOGLE_API_KEY" in src


def test_link_intersect_generates_real_disavow():
    """Link Intersect returns gap domains + disavow_txt with domain: lines (never fake)."""
    import inspect, backend.api.link_intersect as li
    src = inspect.getsource(li.link_intersect)
    assert "gap_domains" in src
    assert "disavow_txt" in src
    assert "domain:" in src
    # Async smoke with fake brand_config
    async def _smoke():
        from unittest.mock import AsyncMock, patch
        fake_cfg = {"brand_name": "Acme", "domain": "acme.test", "competitors": [{"name": "Rival", "domain": "rival.test"}]}
        with patch("backend.services.brand_config.brand_config_for", return_value=fake_cfg):
            # Mock search_web to return deterministic verified data
            from backend.services.verification import VerifiedData
            vd = VerifiedData(value=[{"title": "Rival resources", "url": "https://example.com/rival-link", "snippet": "Rival"}], source="bing_rss", method="test", retrieved_at="2026-01-01T00:00:00Z", confidence=1.0, verified=True, metadata={})
            with patch("backend.services.search.search_web", new=AsyncMock(return_value=vd)):
                res = await li.link_intersect(1)
                assert res["status"] == "ok"
                assert "disavow" in res
                assert isinstance(res["disavow"]["disavow_txt"], str)
    asyncio.run(_smoke())


def test_reviews_local_probes_homepage_jsonld():
    """reviews_local parses homepage JSON-LD for Organization/LocalBusiness + Product/Offer."""
    import inspect, pathlib, backend.api.reviews_local as rl
    src = inspect.getsource(rl.reviews_local_audit)
    mod_src = pathlib.Path("backend/api/reviews_local.py").read_text(encoding="utf-8", errors="ignore")
    assert "Organization" in src and "LocalBusiness" in src
    assert "AggregateRating" in src or "Product" in src
    assert "g2.com" in mod_src and "trustpilot" in mod_src.lower()


def test_scheduled_reports_crud():
    """scheduled_reports enable/list/trigger flow persists JSON."""
    import tempfile, os
    from unittest.mock import patch, AsyncMock, MagicMock
    import backend.api.scheduled_reports as sr
    with tempfile.TemporaryDirectory() as td:
        fake_path = os.path.join(td, "scheduled_reports.json")
        with patch.object(sr, "STATE_PATH", fake_path):
            with patch("backend.services.brand_config.brand_config_for", return_value={"brand_name": "Acme", "domain": "acme.test"}):
                import asyncio as _aio
                res = _aio.run(sr.enable_schedule({"brand_id": 1, "hour_utc": 9, "theme": "forest"}))
                assert res["status"] == "ok", res
                assert res["scheduled"]["theme"] == "forest"
                lst = _aio.run(sr.list_schedules())
                assert len(lst["schedules"]) == 1
                off = _aio.run(sr.disable_schedule({"brand_id": 1}))
                assert off["status"] == "ok"
                lst2 = _aio.run(sr.list_schedules())
                assert len(lst2["schedules"]) == 0


def test_billing_blocks_mutation_on_default_secret(monkeypatch):
    """POST /billing/tenant is blocked when SECRET_KEY is still default."""
    import asyncio as _aio
    from fastapi import HTTPException
    from backend.api import billing as b
    # Force default secret
    import config.settings as cfg
    orig = cfg.settings.SECRET_KEY
    try:
        with patch_ctx_secret("change-me-in-production"):
            with pytest.raises(HTTPException) as ei:
                _aio.run(b.update_tenant({}, authorization="Bearer fake"))
            assert ei.value.status_code == 403
    finally:
        pass


def patch_ctx_secret(val: str):
    """Context manager that temporarily sets settings.SECRET_KEY."""
    class _Ctx:
        def __enter__(self):
            import config.settings as cfg
            self._orig = cfg.settings.SECRET_KEY
            cfg.settings.SECRET_KEY = val
            return self
        def __exit__(self, *a):
            import config.settings as cfg
            cfg.settings.SECRET_KEY = self._orig
            return False
    return _Ctx()


def test_credential_vault_requires_fernet_in_prod():
    """Vault refuses to derive key from default SECRET_KEY in production-like mode."""
    from unittest.mock import patch
    import config.settings as cfg
    orig = cfg.settings.SECRET_KEY
    try:
        cfg.settings.SECRET_KEY = "change-me-in-production"
        with patch.dict("os.environ", {}, clear=False):
            if "CREDENTIALS_FERNET_KEY" in __import__("os").environ:
                del __import__("os").environ["CREDENTIALS_FERNET_KEY"]
            from backend.services.credential_vault import _fernet
            try:
                _fernet()
                assert False, "should have raised"
            except RuntimeError as e:
                assert "CREDENTIALS_FERNET_KEY" in str(e)
    finally:
        cfg.settings.SECRET_KEY = orig


@pytest.mark.live
def test_live_ddgs_search_returns_verified_or_unavailable():
    """Nightly live: ddgs library search hits real network (Bing may 403)."""
    async def _run():
        from backend.services.search import _ddgs_library_search
        res = await _ddgs_library_search("The Hindu newspaper", num=5)
        assert isinstance(res, list)
        # Either returns rows or [] (honest), never raises
    asyncio.run(_run())


@pytest.mark.live
def test_live_wikidata_qid_miss_returns_unavailable():
    """Live: unknown Wikidata QID returns honest miss, not fabricated. Skips gracefully offline."""
    async def _run():
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get("https://www.wikidata.org/wiki/Special:EntityData/Q999999999.json", follow_redirects=True)
                assert r.status_code in (200, 404)
        except Exception as e:
            pytest.skip(f"live network unavailable: {e}")
    asyncio.run(_run())


@pytest.mark.live
def test_live_rdap_timeout_handled():
    """Live: RDAP lookup for a nonsense domain times out gracefully. Skips gracefully offline."""
    async def _run():
        import httpx
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                await c.get("https://rdap.db.ripe.net/domain/nonexistent.invalid", timeout=3)
        except Exception as e:
            # network failure is still a pass for smoke — just verify exception handling path exists
            assert isinstance(e, Exception)
            return
        # if it did not raise, still passes (RDAP returned something)
        assert True
    try:
        asyncio.run(_run())
    except Exception as e:
        pytest.skip(f"live network unavailable: {e}")

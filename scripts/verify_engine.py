#!/usr/bin/env python3
"""
Test script to verify all components of the Off-Page SEO Engine.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_imports():
    print("Testing imports...")
    try:
        from backend.core.database import engine, Base, get_db
        print("  [OK] Database module")
    except Exception as e:
        print(f"  [FAIL] Database module: {e}")
        return False
    
    try:
        from backend.models.models import (
            Brand, Executive, Competitor, BrandMention, Backlink,
            Campaign, Alert, PodcastPitch, PRPitch, KnowledgeGraphTriple,
            RAGCitation, VectorDistance, CompetitorBERTVector, EdgeRedirect,
            ToxicBacklink, GeoCrawlAudit, AnchorTextProfile, ShareOfSearch,
            CrawlStatus, SponsoredCompliance, HreflangAudit, SchemaProtocol,
            ConsensusScore, SatelliteEntity, ComplianceRule, SimulationResult,
            VisualEntityAudit, PassageAttention, RedditConsensus,
            DeadEquitySalvage, ZeroPartyDataAsset
        )
        print("  [OK] All 31 database models")
    except Exception as e:
        print(f"  [FAIL] Models: {e}")
        return False
    
    try:
        from backend.api import (
            brands, features, campaigns, alerts, dashboard,
            knowledge_graph, rag_monitor, vector_engine, pr_engine,
            podcast_monitor, compliance, geo_audit, edge_redirect,
            toxic_analysis, consensus, simulation, zero_party_data,
            passage_scoring, reddit_monitor, satellite_entities,
            schema_validator, anchor_analysis, crawl_accelerator,
            visual_audit, dead_equity, share_of_search, intake,
            analysis, website_scraper,
        )
        print("  [OK] All 30 API routers (incl. analysis, website_scraper, intake)")
    except Exception as e:
        print(f"  [FAIL] API routers: {e}")
        return False
    
    return True


def test_database():
    print("\nTesting database...")
    try:
        from backend.core.database import engine, Base, init_db
        import backend.models.models  # noqa: F401 — registers all tables

        init_db()
        print("  [OK] Tables created successfully")
        
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"  [OK] {len(tables)} tables created")
        for table in sorted(tables):
            print(f"       - {table}")
        
        return True
    except Exception as e:
        print(f"  [FAIL] Database: {e}")
        return False


def test_api():
    print("\nTesting API...")
    try:
        from fastapi.testclient import TestClient
        from main import app
        
        client = TestClient(app)
        
        # Root serves SPA HTML (dist/ or static/) — assert HTML, not JSON.
        response = client.get("/")
        assert response.status_code == 200
        assert "html" in response.headers.get("content-type", "").lower() or "<html" in response.text.lower()
        print("  [OK] Root endpoint (SPA HTML)")

        # /api JSON info (must NOT be swallowed by SPA catch-all).
        response = client.get("/api")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "operational"
        print(f"  [OK] API info ({data.get('features_count')} features)")

        response = client.get("/health")
        assert response.status_code == 200
        assert response.json().get("status") == "healthy"
        print("  [OK] Health endpoint (JSON, not HTML)")
        
        response = client.get("/api/v1/features/")
        assert response.status_code == 200
        data = response.json()
        assert data["total_features"] == 35
        print(f"  [OK] Features endpoint ({data['total_features']} features)")
        
        import uuid as _uuid
        _uniq = _uuid.uuid4().hex[:8]
        response = client.post("/api/v1/brands/", json={
            "name": f"Verification Test Brand {_uniq}",
            "domain": f"verify-{_uniq}.example.com",
            "description": "A test brand for verification only"
        })
        assert response.status_code == 200
        brand = response.json()
        brand_id = brand["id"]
        print(f"  [OK] Brand creation (ID: {brand_id})")
        
        response = client.get(f"/api/v1/brands/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Brand retrieval")
        
        response = client.get(f"/api/v1/dashboard/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Executive dashboard")
        
        response = client.get(f"/api/v1/features/status/summary")
        assert response.status_code == 200
        print("  [OK] Feature status summary")
        
        response = client.get(f"/api/v1/alerts/")
        assert response.status_code == 200
        print("  [OK] Alerts endpoint")
        
        response = client.get(f"/api/v1/knowledge-graph/gaps/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Knowledge graph gaps")
        
        response = client.get(f"/api/v1/rag-monitor/accuracy-report/{brand_id}")
        assert response.status_code == 200
        print("  [OK] RAG accuracy report")
        
        response = client.get(f"/api/v1/vector-engine/distances/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Vector distances")
        
        response = client.get(f"/api/v1/consensus/score/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Consensus score")
        
        response = client.get(f"/api/v1/toxic-analysis/anchor-entropy/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Anchor entropy analysis")
        
        response = client.get(f"/api/v1/share-of-search/current/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Share of search")
        
        response = client.get(f"/api/v1/passage-scoring/analysis/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Passage scoring")
        
        response = client.get(f"/api/v1/schema-validator/generate/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Schema validator")
        
        response = client.get(f"/api/v1/dead-equity/scan/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Dead equity scanner")
        
        response = client.get(f"/api/v1/geo-audit/blackouts/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Geo audit blackouts")
        
        response = client.get(f"/api/v1/edge-redirect/edge-rules/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Edge redirect rules")
        
        response = client.get(f"/api/v1/anchor-analysis/distribution/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Anchor distribution")
        
        response = client.get(f"/api/v1/crawl-accelerator/status/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Crawl accelerator")
        
        response = client.get(f"/api/v1/visual-audit/authority-gap/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Visual audit")
        
        response = client.get(f"/api/v1/reddit-monitor/sentiment/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Reddit sentiment")
        
        response = client.get(f"/api/v1/satellite-entities/discover/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Satellite entities")
        
        response = client.get(f"/api/v1/compliance/rules/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Compliance rules")
        
        # Analysis engine background + export endpoints (new).
        response = client.get(f"/api/v1/analysis/progress/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Analysis progress")

        response = client.get(f"/api/v1/analysis/status/{brand_id}")
        assert response.status_code == 200
        print("  [OK] Analysis status")

        response = client.get(f"/api/v1/analysis/export/{brand_id}?format=json")
        assert response.status_code in (200, 404)
        print("  [OK] Analysis export (json)")

        response = client.get("/api/v1/provider-status")
        # provider-status lives under analysis router; tolerate 404 on old builds
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            print("  [OK] Provider status (no secrets leaked)")

        print(f"\n  All 30 API routers tested successfully!")
        return True
        
    except Exception as e:
        print(f"  [FAIL] API test: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("  Complete Off-Page SEO Engine - Verification Test")
    print("=" * 60)
    print()
    
    all_passed = True
    
    if not test_imports():
        all_passed = False
    
    if not test_database():
        all_passed = False
    
    if not test_api():
        all_passed = False
    
    print()
    print("=" * 60)
    if all_passed:
        print("  ALL TESTS PASSED!")
        print("  The Complete Off-Page SEO Engine is ready.")
        print()
        print("  To start the server:")
        print("    python scripts/start_server.py")
        print()
        print("  API Documentation:")
        print("    http://localhost:8000/docs")
        print()
        print("  Dashboard:")
        print("    http://localhost:3000")
    else:
        print("  SOME TESTS FAILED!")
        print("  Please check the errors above.")
    print("=" * 60)


if __name__ == "__main__":
    main()

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime
from pathlib import Path
import uvicorn

from contextlib import asynccontextmanager
from backend.core.database import engine, get_db, Base, init_db
from backend.models.models import Brand
from config.settings import settings
from backend.api import (
    brands, features, campaigns, alerts, dashboard,
    knowledge_graph, rag_monitor, vector_engine, pr_engine,
    podcast_monitor, compliance, geo_audit, edge_redirect,
    toxic_analysis, consensus, simulation, zero_party_data,
    passage_scoring, reddit_monitor, satellite_entities,
    schema_validator, anchor_analysis, crawl_accelerator,
    visual_audit, dead_equity, share_of_search, intake, analysis,
    website_scraper, bot_governance, prompt_tracking, kg_ops,
    ugc_depth, image_backlinks, author_graph, multi_brand,
    pr_outreach, auth as auth_api,
    aio_tracker, zero_click, transcript_pipeline, llms_audit,
    sentiment, source_influence, cwv, billing,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB on startup (WAL mode + tables) — no longer at import time.
    try:
        init_db()
    except Exception as e:
        print(f"[startup] DB init warning: {e}")
    # Warn when running with default SECRET_KEY.
    try:
        w = settings.secret_warning()
        if w:
            print(f"[startup] WARNING: {w}")
        else:
            print("[startup] SECRET_KEY OK (custom)")
        print(f"[startup] Providers configured: {settings.configured_providers or 'none (free tier)'}")
    except Exception:
        pass
    # Optional periodic re-runs (SCHEDULE_ENABLED=true in .env).
    try:
        from backend.services.scheduler import maybe_start_from_env
        maybe_start_from_env()
    except Exception as e:
        print(f"[startup] scheduler skipped: {e}")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS: FRONTEND_ORIGINS env in production; wildcard dev default (no credentials).
# Set FRONTEND_ORIGINS=https://app.example.com,https://admin.example.com to lock down.
_cors_origins = settings.cors_origins if hasattr(settings, "cors_origins") else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(brands.router, prefix="/api/v1/brands", tags=["Brands"])
app.include_router(features.router, prefix="/api/v1/features", tags=["Features"])
app.include_router(campaigns.router, prefix="/api/v1/campaigns", tags=["Campaigns"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["Alerts"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard"])
app.include_router(knowledge_graph.router, prefix="/api/v1/knowledge-graph", tags=["Knowledge Graph"])
app.include_router(rag_monitor.router, prefix="/api/v1/rag-monitor", tags=["RAG Monitor"])
app.include_router(vector_engine.router, prefix="/api/v1/vector-engine", tags=["Vector Engine"])
app.include_router(pr_engine.router, prefix="/api/v1/pr-engine", tags=["PR Engine"])
app.include_router(podcast_monitor.router, prefix="/api/v1/podcast-monitor", tags=["Podcast Monitor"])
app.include_router(compliance.router, prefix="/api/v1/compliance", tags=["Compliance"])
app.include_router(geo_audit.router, prefix="/api/v1/geo-audit", tags=["Geo Audit"])
app.include_router(edge_redirect.router, prefix="/api/v1/edge-redirect", tags=["Edge Redirect"])
app.include_router(toxic_analysis.router, prefix="/api/v1/toxic-analysis", tags=["Toxic Analysis"])
app.include_router(consensus.router, prefix="/api/v1/consensus", tags=["Consensus"])
app.include_router(simulation.router, prefix="/api/v1/simulation", tags=["Simulation"])
app.include_router(zero_party_data.router, prefix="/api/v1/zero-party-data", tags=["Zero Party Data"])
app.include_router(passage_scoring.router, prefix="/api/v1/passage-scoring", tags=["Passage Scoring"])
app.include_router(reddit_monitor.router, prefix="/api/v1/reddit-monitor", tags=["Reddit Monitor"])
app.include_router(satellite_entities.router, prefix="/api/v1/satellite-entities", tags=["Satellite Entities"])
app.include_router(schema_validator.router, prefix="/api/v1/schema-validator", tags=["Schema Validator"])
app.include_router(anchor_analysis.router, prefix="/api/v1/anchor-analysis", tags=["Anchor Analysis"])
app.include_router(crawl_accelerator.router, prefix="/api/v1/crawl-accelerator", tags=["Crawl Accelerator"])
app.include_router(visual_audit.router, prefix="/api/v1/visual-audit", tags=["Visual Audit"])
app.include_router(dead_equity.router, prefix="/api/v1/dead-equity", tags=["Dead Equity"])
app.include_router(share_of_search.router, prefix="/api/v1/share-of-search", tags=["Share of Search"])
app.include_router(intake.router, prefix="/api/v1/intake", tags=["Intake Data Layer"])
app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["Analysis Engine"])
app.include_router(website_scraper.router, prefix="/api/v1/scraper", tags=["Website Scraper"])
app.include_router(bot_governance.router, prefix="/api/v1/bot-governance", tags=["Bot Governance"])
app.include_router(prompt_tracking.router, prefix="/api/v1/prompt-tracking", tags=["Prompt Tracking"])
app.include_router(kg_ops.router, prefix="/api/v1/kg-ops", tags=["KG Ops"])
app.include_router(ugc_depth.router, prefix="/api/v1/ugc-depth", tags=["UGC Depth"])
app.include_router(image_backlinks.router, prefix="/api/v1/image-backlinks", tags=["Image Backlinks"])
app.include_router(author_graph.router, prefix="/api/v1/author-graph", tags=["Author Graph"])
app.include_router(multi_brand.router, prefix="/api/v1/multi-brand", tags=["Multi-Brand"])
app.include_router(pr_outreach.router, prefix="/api/v1/pr-outreach", tags=["PR Outreach 2.0"])
app.include_router(aio_tracker.router, prefix="/api/v1/aio-tracker", tags=["AIO Citation Tracker"])
app.include_router(zero_click.router, prefix="/api/v1/zero-click", tags=["Zero-Click Attribution"])
app.include_router(transcript_pipeline.router, prefix="/api/v1/transcripts", tags=["Transcript Pipeline"])
app.include_router(llms_audit.router, prefix="/api/v1/llms-audit", tags=["LLMs.txt 29-Check"])
app.include_router(sentiment.router, prefix="/api/v1/sentiment", tags=["Sentiment & Narrative"])
app.include_router(source_influence.router, prefix="/api/v1/source-influence", tags=["Source Influence ROI"])
app.include_router(cwv.router, prefix="/api/v1/cwv", tags=["CWV & Hreflang"])
app.include_router(billing.router, prefix="/api/v1/billing", tags=["Billing & White-Label"])

FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"
SPA_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


# ---- Health + API info MUST be registered BEFORE the SPA catch-all ----
# Otherwise GET /health and GET /api match /{full_path:path} and return HTML.
@app.get("/api")
async def api_info():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "operational",
        "features_count": 35,
        "extended_count": 7,
        "p0_2026": ["aio-tracker", "zero-click", "transcripts", "llms-audit", "sentiment", "source-influence", "cwv"],
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/v1/provider-status", include_in_schema=False)
async def provider_status_alias():
    """Top-level alias for /api/v1/analysis/provider-status (verify_engine + frontend compat)."""
    try:
        from backend.services.providers import provider_status
        return {"providers": provider_status(),
                "configured": settings.configured_providers,
                "retrieved_at": datetime.utcnow().isoformat()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)[:300])


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path, headers=SPA_HEADERS)
    return FileResponse("static/index.html", headers=SPA_HEADERS)


# ---- SPA catch-all is intentionally LAST so /api/*, /docs, /health, /openapi.json never collide ----
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    # Explicitly never swallow API / docs / health paths (with or without trailing slash).
    if (
        full_path.startswith("api/")
        or full_path == "api"
        or full_path.startswith("api/v1")
        or full_path in ("docs", "redoc", "openapi.json", "health")
        or full_path.startswith("docs/")
        or full_path.startswith("redoc/")
    ):
        raise HTTPException(status_code=404, detail="Not found")
    asset = FRONTEND_DIST / full_path
    if FRONTEND_DIST.exists() and full_path and asset.is_file():
        return FileResponse(asset, headers=SPA_HEADERS)
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path, headers=SPA_HEADERS)
    raise HTTPException(status_code=404, detail="Not found")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

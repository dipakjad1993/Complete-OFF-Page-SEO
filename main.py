from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime
from pathlib import Path
import uvicorn

from backend.core.database import engine, get_db, Base
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
    website_scraper
)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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

FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"
SPA_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path, headers=SPA_HEADERS)
    return FileResponse("static/index.html", headers=SPA_HEADERS)


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    if full_path.startswith("api/") or full_path in ("docs", "redoc", "openapi.json"):
        raise HTTPException(status_code=404, detail="Not found")
    asset = FRONTEND_DIST / full_path
    if FRONTEND_DIST.exists() and full_path and asset.is_file():
        return FileResponse(asset, headers=SPA_HEADERS)
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path, headers=SPA_HEADERS)
    raise HTTPException(status_code=404, detail="Not found")


@app.get("/api")
async def api_info():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "operational",
        "features_count": 35,
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

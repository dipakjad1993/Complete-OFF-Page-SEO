from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from backend.core.database import get_db
from backend.models.models import Brand

router = APIRouter()


class FeatureStatus(BaseModel):
    feature_id: int
    feature_name: str
    status: str
    description: str


FEATURES = [
    {"id": 1, "name": "LLM Co-Mention & Perception Auditing", "status": "active", "description": "Scrapes AI search engine context windows to measure brand inclusion"},
    {"id": 2, "name": "Predictive Digital PR & Trend Hook Engine", "status": "active", "description": "Data-driven story hooks matched to trending topics"},
    {"id": 3, "name": "Automated Unlinked Citation Converter", "status": "active", "description": "Detects unlinked brand mentions and converts to links"},
    {"id": 4, "name": "Algorithmic Link Poisoning & Anomaly Radar", "status": "active", "description": "ML anomaly detection on backlink velocity and anchor text"},
    {"id": 5, "name": "Entity-Driven Podcast & Video Citation Finder", "status": "active", "description": "Scrapes transcript databases for brand mentions"},
    {"id": 6, "name": "Embedding Distance Engine", "status": "active", "description": "Maps vector gaps between brand and industry nodes"},
    {"id": 7, "name": "RAG Source Patching Engine", "status": "active", "description": "Detects and corrects AI hallucinations about your brand"},
    {"id": 8, "name": "Web Consensus Scorer", "status": "active", "description": "Calculates net-sentiment across the web"},
    {"id": 9, "name": "Autonomous Buying Agent Optimizer", "status": "active", "description": "Optimizes for AI purchasing agent evaluation"},
    {"id": 10, "name": "PBN & Fake-PR Detector", "status": "active", "description": "Forensic analysis of target domains for PBN footprints"},
    {"id": 11, "name": "Share-of-Search Revenue Modeler", "status": "active", "description": "Monte Carlo simulations forecasting business impact"},
    {"id": 12, "name": "Edge Auto-Router", "status": "active", "description": "Serverless edge rules for dead link equity recovery"},
    {"id": 13, "name": "Active Anti-Scrape & Canonical Shield", "status": "active", "description": "Dynamic headers to neutralize negative SEO attacks"},
    {"id": 14, "name": "Developer Ecosystem & Schema Seeder", "status": "active", "description": "Auto-generates PRs for API/SDK attribution"},
    {"id": 15, "name": "Whisper-Vector Transcription Monitor", "status": "active", "description": "Processes audio/video for verbal brand mentions"},
    {"id": 16, "name": "Knowledge Graph Triple Arbitrage", "status": "active", "description": "Real-time Wikidata triple monitoring and editing"},
    {"id": 17, "name": "Anonymized Telemetry Data-PR Engine", "status": "active", "description": "First-party data mining for press assets"},
    {"id": 18, "name": "Multi-Agent Off-Page Simulation Sandbox", "status": "active", "description": "Pre-campaign algorithmic impact testing"},
    {"id": 19, "name": "Satellite Entity M&A Radar", "status": "active", "description": "Discovers acquisition targets with topical authority"},
    {"id": 20, "name": "Reverse RAG-Cache Poisoning Defense", "status": "active", "description": "Vector cache eviction and memory purging"},
    {"id": 21, "name": "Visual Entity Co-Occurrence Audit", "status": "active", "description": "Computer vision analysis of brand in visual media"},
    {"id": 22, "name": "Agentic Protocol Negotiation Proxy", "status": "active", "description": "Machine-to-machine entity handshake protocol"},
    {"id": 23, "name": "Temporal Graph Decay & Citation Renewal", "status": "active", "description": "Monitors citation depth decay and triggers renewal"},
    {"id": 24, "name": "C2PA & DNSSEC Key-Signed Schema", "status": "active", "description": "Cryptographic entity-origin proof signing"},
    {"id": 25, "name": "Corporate Compliance & Redaction Guard", "status": "active", "description": "Pre-outreach legal compliance checking"},
    {"id": 26, "name": "Multi-Region Geo-Crawl Node Profiler", "status": "active", "description": "Global citation localization auditing"},
    {"id": 27, "name": "Zero-Party API Data-Syndication", "status": "active", "description": "Exclusive data widgets for journalists"},
    {"id": 28, "name": "Passage-Level BERT Evaluator", "status": "active", "description": "Scores passage attention weight around backlinks"},
    {"id": 29, "name": "Reddit & Forum Consensus Mapper", "status": "active", "description": "Tracks community sentiment and co-occurrence"},
    {"id": 30, "name": "Competitor BERT-Vector Extraction", "status": "active", "description": "Reverse-engineers semantic keywords from competitors"},
    {"id": 31, "name": "Non-HTML Protocol Auditor", "status": "active", "description": "Validates machine-readable off-page citations"},
    {"id": 32, "name": "Neural Anchor-Text Entropy Predictor", "status": "active", "description": "Monitors over-optimization boundaries"},
    {"id": 33, "name": "AI Crawler Re-Indexation Pinger", "status": "active", "description": "Accelerates re-crawl after media placements"},
    {"id": 34, "name": "FTC & Sponsored-Link Compliance Shield", "status": "active", "description": "Detects missing rel=sponsored and FTC disclosures"},
    {"id": 35, "name": "Cross-Border Hreflang Equity Balancer", "status": "active", "description": "Prevents regional link equity cannibalization"},
]


@router.get("/")
def list_features():
    return {"total_features": len(FEATURES), "features": FEATURES}


# NOTE: /status/summary MUST be declared BEFORE /{feature_id} otherwise
# "status" is parsed as feature_id and returns 422. Explicit ordering fix.
@router.get("/status/summary")
def feature_status_summary():
    active = sum(1 for f in FEATURES if f["status"] == "active")
    return {
        "total": len(FEATURES),
        "active": active,
        "inactive": len(FEATURES) - active
    }


@router.get("/{feature_id}")
def get_feature(feature_id: int):
    feature = next((f for f in FEATURES if f["id"] == feature_id), None)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")
    return feature

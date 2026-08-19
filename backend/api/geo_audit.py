from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Brand, GeoCrawlAudit

router = APIRouter()


class GeoAuditCreate(BaseModel):
    brand_id: int
    region: str
    source_url: Optional[str] = None
    brand_cited: bool = False
    citation_context: Optional[str] = None
    domain_authority: Optional[float] = None


@router.post("/audit")
def create_geo_audit(audit_data: GeoAuditCreate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == audit_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    audit = GeoCrawlAudit(**audit_data.model_dump())
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit


@router.get("/regions/{brand_id}")
def get_regional_coverage(brand_id: int, db: Session = Depends(get_db)):
    audits = db.query(GeoCrawlAudit).filter(
        GeoCrawlAudit.brand_id == brand_id
    ).all()
    
    regions = {}
    for audit in audits:
        if audit.region not in regions:
            regions[audit.region] = {
                "total_audits": 0,
                "brand_cited": 0,
                "avg_da": 0,
                "citations": []
            }
        regions[audit.region]["total_audits"] += 1
        if audit.brand_cited:
            regions[audit.region]["brand_cited"] += 1
        if audit.domain_authority:
            regions[audit.region]["avg_da"] += audit.domain_authority
        regions[audit.region]["citations"].append({
            "url": audit.source_url,
            "cited": audit.brand_cited,
            "context": audit.citation_context
        })
    
    for region in regions:
        if regions[region]["total_audits"] > 0:
            regions[region]["avg_da"] /= regions[region]["total_audits"]
            regions[region]["citation_rate"] = (
                regions[region]["brand_cited"] / regions[region]["total_audits"] * 100
            )
    
    return {"brand_id": brand_id, "regional_coverage": regions}


@router.get("/blackouts/{brand_id}")
def identify_citation_blackouts(brand_id: int, db: Session = Depends(get_db)):
    major_regions = ["US", "UK", "EU", "APAC", "LATAM", "MEA", "CA", "AU"]
    
    audits = db.query(GeoCrawlAudit).filter(
        GeoCrawlAudit.brand_id == brand_id
    ).all()
    
    audited_regions = set(a.region for a in audits)
    blackouts = []
    
    for region in major_regions:
        if region not in audited_regions:
            blackouts.append({
                "region": region,
                "status": "no_data",
                "recommendation": f"Initiate geo-crawl audit for {region} market"
            })
        else:
            region_audits = [a for a in audits if a.region == region]
            cited_count = sum(1 for a in region_audits if a.brand_cited)
            citation_rate = cited_count / len(region_audits) * 100 if region_audits else 0
            
            if citation_rate < 20:
                blackouts.append({
                    "region": region,
                    "status": "low_citation",
                    "citation_rate": citation_rate,
                    "recommendation": f"Launch {region}-targeted media outreach campaign"
                })
    
    return {
        "brand_id": brand_id,
        "blackouts": blackouts,
        "total_blackouts": len(blackouts),
        "regions_audited": len(audited_regions)
    }


@router.get("/recommendations/{brand_id}")
def get_geo_recommendations(brand_id: int, db: Session = Depends(get_db)):
    audits = db.query(GeoCrawlAudit).filter(
        GeoCrawlAudit.brand_id == brand_id
    ).all()
    
    recommendations = []
    
    region_stats = {}
    for audit in audits:
        if audit.region not in region_stats:
            region_stats[audit.region] = {"total": 0, "cited": 0}
        region_stats[audit.region]["total"] += 1
        if audit.brand_cited:
            region_stats[audit.region]["cited"] += 1
    
    for region, stats in region_stats.items():
        rate = stats["cited"] / stats["total"] * 100 if stats["total"] > 0 else 0
        if rate < 30:
            recommendations.append({
                "region": region,
                "current_rate": rate,
                "priority": "high" if rate < 10 else "medium",
                "actions": [
                    f"Identify top {region} media outlets in your industry",
                    f"Partner with {region}-based PR agency for local placements",
                    f"Create region-specific content for {region} publications",
                    f"Target {region} industry events and conferences"
                ]
            })
    
    return {"brand_id": brand_id, "recommendations": recommendations}

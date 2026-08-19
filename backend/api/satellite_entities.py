from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Brand, SatelliteEntity

router = APIRouter()


class SatelliteEntityCreate(BaseModel):
    brand_id: int
    entity_domain: str
    entity_name: str
    topical_authority: Optional[float] = None
    estimated_value: Optional[float] = None
    acquisition_type: Optional[str] = None
    domain_age: Optional[int] = None
    backlink_count: Optional[int] = None
    relevance_score: Optional[float] = None


@router.post("/scan")
def scan_satellite_entity(entity_data: SatelliteEntityCreate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == entity_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    entity = SatelliteEntity(**entity_data.model_dump())
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


@router.get("/discover/{brand_id}")
def discover_satellites(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    existing = db.query(SatelliteEntity).filter(
        SatelliteEntity.brand_id == brand_id
    ).all()
    
    return {
        "brand": brand.name,
        "discovered_satellites": [
            {
                "domain": s.entity_domain,
                "name": s.entity_name,
                "topical_authority": s.topical_authority,
                "estimated_value": s.estimated_value,
                "relevance_score": s.relevance_score,
                "recommendation": "High-value acquisition target" if (s.topical_authority or 0) > 0.7 else "Moderate value"
            } for s in existing
        ],
        "total_satellites": len(existing)
    }


@router.get("/recommendations/{brand_id}")
def get_acquisition_recommendations(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    satellites = db.query(SatelliteEntity).filter(
        SatelliteEntity.brand_id == brand_id
    ).all()
    
    recommendations = []
    for s in satellites:
        score = (s.topical_authority or 0) * 0.4 + (s.relevance_score or 0) * 0.4 + (1 - (s.estimated_value or 10000) / 100000) * 0.2
        
        if score > 0.6:
            recommendations.append({
                "entity": s.entity_name,
                "domain": s.entity_domain,
                "acquisition_type": s.acquisition_type,
                "score": round(score, 2),
                "estimated_value": s.estimated_value,
                "topical_authority": s.topical_authority,
                "backlink_count": s.backlink_count,
                "priority": "high" if score > 0.8 else "medium"
            })
    
    return {
        "brand": brand.name,
        "recommendations": sorted(recommendations, key=lambda x: x["score"], reverse=True),
        "total_recommendations": len(recommendations)
    }

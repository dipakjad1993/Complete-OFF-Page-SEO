from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

from backend.core.database import get_db
from backend.models.models import (
    Brand, Executive, Competitor, BrandMention, Backlink, Campaign,
    Alert, KnowledgeGraphTriple, RAGCitation, VectorDistance,
    ToxicBacklink, AnchorTextProfile, ConsensusScore, ShareOfSearch,
    CrawlStatus, CompetitorBERTVector, EdgeRedirect
)

router = APIRouter()


class BrandCreate(BaseModel):
    name: str
    domain: str
    kg_mid: Optional[str] = None
    wikidata_id: Optional[str] = None
    crunchbase_id: Optional[str] = None
    wikipedia_url: Optional[str] = None
    description: Optional[str] = None
    topical_taxonomy: Optional[dict] = None
    primary_categories: Optional[list] = None
    seed_keywords: Optional[list] = None


class BrandResponse(BaseModel):
    id: int
    name: str
    domain: str
    kg_mid: Optional[str]
    wikidata_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("/", response_model=BrandResponse)
def create_brand(brand_data: BrandCreate, db: Session = Depends(get_db)):
    existing = db.query(Brand).filter(Brand.domain == brand_data.domain).first()
    if existing:
        raise HTTPException(status_code=400, detail="Brand with this domain already exists")
    
    brand = Brand(**brand_data.model_dump())
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


@router.get("/", response_model=List[BrandResponse])
def list_brands(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    brands = db.query(Brand).offset(skip).limit(limit).all()
    return brands


@router.get("/{brand_id}")
def get_brand(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    mention_count = db.query(func.count(BrandMention.id)).filter(BrandMention.brand_id == brand_id).scalar()
    backlink_count = db.query(func.count(Backlink.id)).filter(Backlink.brand_id == brand_id).scalar()
    alert_count = db.query(func.count(Alert.id)).filter(
        Alert.brand_id == brand_id, Alert.is_resolved == False
    ).scalar()
    
    return {
        "brand": brand,
        "stats": {
            "total_mentions": mention_count,
            "total_backlinks": backlink_count,
            "active_alerts": alert_count,
        }
    }


@router.put("/{brand_id}")
def update_brand(brand_id: int, brand_data: BrandCreate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    for key, value in brand_data.model_dump(exclude_unset=True).items():
        setattr(brand, key, value)
    
    db.commit()
    db.refresh(brand)
    return brand


@router.delete("/{brand_id}")
def delete_brand(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    db.delete(brand)
    db.commit()
    return {"message": "Brand deleted successfully"}


@router.get("/{brand_id}/executives")
def list_executives(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    return brand.executives


@router.get("/{brand_id}/competitors")
def list_competitors(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    return brand.competitors


@router.get("/{brand_id}/overview")
def brand_overview(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    mentions = db.query(func.count(BrandMention.id)).filter(BrandMention.brand_id == brand_id).scalar()
    unlinked = db.query(func.count(BrandMention.id)).filter(
        BrandMention.brand_id == brand_id, BrandMention.has_link == False
    ).scalar()
    backlinks = db.query(func.count(Backlink.id)).filter(Backlink.brand_id == brand_id).scalar()
    toxic = db.query(func.count(ToxicBacklink.id)).filter(ToxicBacklink.brand_id == brand_id).scalar()
    
    latest_consensus = db.query(ConsensusScore).filter(
        ConsensusScore.brand_id == brand_id
    ).order_by(ConsensusScore.measured_at.desc()).first()
    
    latest_sos = db.query(ShareOfSearch).filter(
        ShareOfSearch.brand_id == brand_id
    ).order_by(ShareOfSearch.measured_at.desc()).first()
    
    active_alerts = db.query(func.count(Alert.id)).filter(
        Alert.brand_id == brand_id, Alert.is_resolved == False
    ).scalar()
    
    return {
        "brand": brand,
        "stats": {
            "total_mentions": mentions,
            "unlinked_mentions": unlinked,
            "total_backlinks": backlinks,
            "toxic_backlinks": toxic,
            "active_alerts": active_alerts,
        },
        "consensus": latest_consensus,
        "share_of_search": latest_sos,
    }

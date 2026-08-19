from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Campaign, Brand

router = APIRouter()


class CampaignCreate(BaseModel):
    brand_id: int
    name: str
    campaign_type: Optional[str] = None
    target_keywords: Optional[list] = None
    target_journalists: Optional[list] = None
    target_publications: Optional[list] = None
    messaging: Optional[str] = None
    budget: Optional[float] = None


@router.post("/")
def create_campaign(campaign_data: CampaignCreate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == campaign_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    campaign = Campaign(**campaign_data.model_dump())
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("/")
def list_campaigns(brand_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Campaign)
    if brand_id:
        query = query.filter(Campaign.brand_id == brand_id)
    return query.order_by(Campaign.created_at.desc()).all()


@router.get("/{campaign_id}")
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.put("/{campaign_id}/status")
def update_campaign_status(campaign_id: int, status: str, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = status
    db.commit()
    return {"message": f"Campaign status updated to {status}"}


@router.get("/{campaign_id}/results")
def get_campaign_results(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"campaign": campaign.name, "results": campaign.results or {}}

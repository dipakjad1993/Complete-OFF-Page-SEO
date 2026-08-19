from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Brand, CrawlStatus

router = APIRouter()


class CrawlPingRequest(BaseModel):
    brand_id: int
    url: str


@router.post("/ping")
def ping_crawl_index(crawl_data: CrawlPingRequest, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == crawl_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    status = db.query(CrawlStatus).filter(
        CrawlStatus.brand_id == crawl_data.brand_id,
        CrawlStatus.url == crawl_data.url
    ).first()
    
    if not status:
        status = CrawlStatus(
            brand_id=crawl_data.brand_id,
            url=crawl_data.url
        )
        db.add(status)
    
    status.ping_sent = True
    status.ping_sent_at = datetime.utcnow()
    db.commit()
    
    return {
        "url": crawl_data.url,
        "ping_status": "sent",
        "timestamp": datetime.utcnow().isoformat(),
        "message": "Index ping request queued for processing"
    }


@router.get("/status/{brand_id}")
def get_crawl_status(brand_id: int, db: Session = Depends(get_db)):
    statuses = db.query(CrawlStatus).filter(
        CrawlStatus.brand_id == brand_id
    ).all()
    
    return {
        "brand_id": brand_id,
        "total_urls": len(statuses),
        "indexed": sum(1 for s in statuses if s.indexation_status == "indexed"),
        "pending": sum(1 for s in statuses if s.indexation_status == "pending"),
        "errors": sum(1 for s in statuses if s.indexation_status == "error"),
        "urls": [
            {
                "url": s.url,
                "status": s.indexation_status,
                "last_crawl": s.googlebot_last_crawl.isoformat() if s.googlebot_last_crawl else None,
                "ping_sent": s.ping_sent
            } for s in statuses
        ]
    }


@router.post("/accelerate/{brand_id}")
def accelerate_indexation(brand_id: int, url: str, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    acceleration_methods = [
        {"method": "Indexing API", "status": "pending", "description": "Submit via Google Indexing API"},
        {"method": "WebSub", "status": "pending", "description": "Publish update via WebSub hub"},
        {"method": "Sitemap Ping", "status": "pending", "description": "Ping search engines with updated sitemap"},
        {"method": "Social Syndication", "status": "pending", "description": "Share URL across social platforms for faster discovery"}
    ]
    
    return {
        "url": url,
        "brand": brand.name,
        "acceleration_methods": acceleration_methods,
        "estimated_indexation_time": "2-6 hours with acceleration",
        "normal_indexation_time": "1-3 weeks without acceleration"
    }

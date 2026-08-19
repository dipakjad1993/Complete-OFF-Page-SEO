from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Brand, DeadEquitySalvage, Backlink

router = APIRouter()


class DeadEquityCreate(BaseModel):
    brand_id: int
    source_url: str
    target_url: str
    http_status: int = 404
    backlink_count: Optional[int] = None
    domain_authority: Optional[float] = None
    equity_value: Optional[float] = None


@router.post("/detect")
def detect_dead_equity(equity_data: DeadEquityCreate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == equity_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    dead = DeadEquitySalvage(**equity_data.model_dump())
    db.add(dead)
    db.commit()
    db.refresh(dead)
    return dead


@router.get("/scan/{brand_id}")
def scan_dead_equity(brand_id: int, db: Session = Depends(get_db)):
    dead_links = db.query(DeadEquitySalvage).filter(
        DeadEquitySalvage.brand_id == brand_id
    ).all()
    
    total_equity = sum(d.equity_value or 0 for d in dead_links)
    undeployed = [d for d in dead_links if not d.redirect_deployed]
    
    return {
        "brand_id": brand_id,
        "total_dead_links": len(dead_links),
        "undeployed_redirects": len(undeployed),
        "total_equity_at_risk": total_equity,
        "links": [
            {
                "source": d.source_url,
                "target": d.target_url,
                "status": d.http_status,
                "backlinks": d.backlink_count,
                "da": d.domain_authority,
                "equity": d.equity_value,
                "redirected": d.redirect_deployed
            } for d in dead_links
        ]
    }


@router.post("/deploy-redirect/{dead_id}")
def deploy_dead_equity_redirect(dead_id: int, db: Session = Depends(get_db)):
    dead = db.query(DeadEquitySalvage).filter(DeadEquitySalvage.id == dead_id).first()
    if not dead:
        raise HTTPException(status_code=404, detail="Dead equity record not found")
    
    dead.redirect_deployed = True
    db.commit()
    
    return {
        "source": dead.source_url,
        "target": dead.target_url,
        "status": "redirect_deployed",
        "equity_recovered": dead.equity_value,
        "edge_rule": f"301 redirect from {dead.source_url} to {dead.target_url}"
    }


@router.get("/recovery-potential/{brand_id}")
def recovery_potential(brand_id: int, db: Session = Depends(get_db)):
    dead_links = db.query(DeadEquitySalvage).filter(
        DeadEquitySalvage.brand_id == brand_id,
        DeadEquitySalvage.redirect_deployed == False
    ).all()
    
    prioritized = sorted(dead_links, key=lambda x: (x.equity_value or 0) * (x.domain_authority or 0), reverse=True)
    
    return {
        "brand_id": brand_id,
        "total_recoverable": len(prioritized),
        "total_equity": sum(d.equity_value or 0 for d in prioritized),
        "top_recovery_targets": [
            {
                "source": d.source_url,
                "target": d.target_url,
                "equity_value": d.equity_value,
                "domain_authority": d.domain_authority,
                "priority_score": (d.equity_value or 0) * (d.domain_authority or 0)
            } for d in prioritized[:10]
        ]
    }

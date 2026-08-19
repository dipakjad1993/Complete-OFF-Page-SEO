from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Brand, VisualEntityAudit

router = APIRouter()


class VisualAuditCreate(BaseModel):
    brand_id: int
    image_url: str
    source_url: Optional[str] = None
    brand_detected: bool = False
    brand_position: Optional[str] = None
    competitor_detected: bool = False
    competitor_positions: Optional[dict] = None
    visual_authority_score: Optional[float] = None


@router.post("/analyze")
def analyze_visual(audit_data: VisualAuditCreate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == audit_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    audit = VisualEntityAudit(**audit_data.model_dump())
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit


@router.get("/audits/{brand_id}")
def list_visual_audits(brand_id: int, db: Session = Depends(get_db)):
    return db.query(VisualEntityAudit).filter(
        VisualEntityAudit.brand_id == brand_id
    ).order_by(VisualEntityAudit.analyzed_at.desc()).all()


@router.get("/authority-gap/{brand_id}")
def visual_authority_gap(brand_id: int, db: Session = Depends(get_db)):
    audits = db.query(VisualEntityAudit).filter(
        VisualEntityAudit.brand_id == brand_id
    ).all()
    
    if not audits:
        return {"message": "No visual audits conducted yet"}
    
    brand_detected_count = sum(1 for a in audits if a.brand_detected)
    avg_position = 0
    positions = [a.brand_position for a in audits if a.brand_position]
    
    position_scores = {"primary": 1.0, "secondary": 0.5, "tertiary": 0.25, "absent": 0}
    if positions:
        avg_position = sum(position_scores.get(p, 0) for p in positions) / len(positions)
    
    competitor_coverage = {}
    for a in audits:
        if a.competitor_positions:
            for comp, pos in a.competitor_positions.items():
                if comp not in competitor_coverage:
                    competitor_coverage[comp] = {"primary": 0, "secondary": 0, "tertiary": 0}
                if pos in competitor_coverage[comp]:
                    competitor_coverage[comp][pos] += 1
    
    return {
        "brand_id": brand_id,
        "total_images_analyzed": len(audits),
        "brand_detected_in": brand_detected_count,
        "detection_rate": brand_detected_count / len(audits) * 100 if audits else 0,
        "avg_visual_position_score": round(avg_position, 4),
        "competitor_visual_coverage": competitor_coverage,
        "recommendation": "Create and distribute high-quality visual assets to improve visual authority" if avg_position < 0.5 else "Visual authority is strong"
    }


@router.get("/generate-assets/{brand_id}")
def generate_visual_assets(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    assets = [
        {
            "type": "architecture_diagram",
            "description": f"System architecture diagram showing {brand.name} as central node",
            "format": "SVG",
            "embeddable": True
        },
        {
            "type": "comparison_chart",
            "description": f"Market comparison chart positioning {brand.name} vs competitors",
            "format": "SVG",
            "embeddable": True
        },
        {
            "type": "infographic",
            "description": f"Industry infographic with {brand.name} branding",
            "format": "SVG",
            "embeddable": True
        }
    ]
    
    return {"brand": brand.name, "recommended_visual_assets": assets}

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import math

from backend.core.database import get_db
from backend.models.models import Brand, AnchorTextProfile, Backlink

router = APIRouter()


@router.get("/analyze/{brand_id}")
def analyze_anchor_text(brand_id: int, db: Session = Depends(get_db)):
    backlinks = db.query(Backlink).filter(Backlink.brand_id == brand_id).all()
    
    anchor_counts = {}
    for bl in backlinks:
        anchor = bl.anchor_text or "(no anchor)"
        anchor_counts[anchor] = anchor_counts.get(anchor, 0) + 1
    
    total = len(backlinks)
    if total == 0:
        return {"message": "No backlinks found"}
    
    entropy = 0
    for count in anchor_counts.values():
        prob = count / total
        if prob > 0:
            entropy -= prob * math.log2(prob)
    
    max_entropy = math.log2(len(anchor_counts)) if anchor_counts else 0
    normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0
    
    profile = []
    for anchor, count in sorted(anchor_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = count / total * 100
        profile.append({
            "anchor_text": anchor,
            "count": count,
            "percentage": round(percentage, 2),
            "risk_level": "high" if percentage > 30 else "medium" if percentage > 15 else "low"
        })
    
    return {
        "brand_id": brand_id,
        "total_backlinks": total,
        "unique_anchors": len(anchor_counts),
        "entropy_score": round(entropy, 4),
        "normalized_entropy": round(normalized_entropy, 4),
        "over_optimization_risk": "high" if normalized_entropy < 0.3 else "medium" if normalized_entropy < 0.5 else "low",
        "top_anchors": profile[:20],
        "recommendations": [
            "Diversify anchor text to include more natural variations" if normalized_entropy < 0.5 else "Anchor distribution looks healthy",
            "Reduce exact-match commercial anchors" if any(p["percentage"] > 25 and p["anchor_text"] != "(no anchor)" for p in profile) else "No overused anchors detected"
        ]
    }


@router.get("/distribution/{brand_id}")
def get_anchor_distribution(brand_id: int, db: Session = Depends(get_db)):
    backlinks = db.query(Backlink).filter(Backlink.brand_id == brand_id).all()
    
    categories = {
        "branded": 0,
        "exact_match": 0,
        "partial_match": 0,
        "generic": 0,
        "naked_url": 0,
        "image": 0,
        "other": 0
    }
    
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    brand_name = brand.name.lower() if brand else ""
    
    for bl in backlinks:
        anchor = (bl.anchor_text or "").lower()
        if not anchor:
            categories["other"] += 1
        elif brand_name and brand_name in anchor:
            categories["branded"] += 1
        elif anchor.startswith("http"):
            categories["naked_url"] += 1
        elif anchor in ["click here", "learn more", "read more", "here", "website"]:
            categories["generic"] += 1
        elif any(kw in anchor for kw in ["buy", "price", "cheap", "best", "top"]):
            categories["exact_match"] += 1
        elif brand_name and any(word in anchor for word in brand_name.split()):
            categories["partial_match"] += 1
        else:
            categories["other"] += 1
    
    total = len(backlinks) if backlinks else 1
    distribution = {k: {"count": v, "percentage": round(v / total * 100, 2)} for k, v in categories.items()}
    
    return {"brand_id": brand_id, "distribution": distribution}


@router.get("/over-optimized/{brand_id}")
def find_over_optimized_anchors(brand_id: int, db: Session = Depends(get_db)):
    backlinks = db.query(Backlink).filter(Backlink.brand_id == brand_id).all()
    
    anchor_counts = {}
    for bl in backlinks:
        anchor = bl.anchor_text or "(no anchor)"
        anchor_counts[anchor] = anchor_counts.get(anchor, 0) + 1
    
    total = len(backlinks)
    over_optimized = []
    
    for anchor, count in anchor_counts.items():
        percentage = count / total * 100 if total > 0 else 0
        if percentage > 20 and anchor != "(no anchor)":
            over_optimized.append({
                "anchor_text": anchor,
                "count": count,
                "percentage": round(percentage, 2),
                "risk": "critical" if percentage > 35 else "high",
                "recommendation": f"Reduce '{anchor}' from {percentage:.1f}% to under 15%"
            })
    
    return {
        "brand_id": brand_id,
        "over_optimized_count": len(over_optimized),
        "anchors": over_optimized
    }

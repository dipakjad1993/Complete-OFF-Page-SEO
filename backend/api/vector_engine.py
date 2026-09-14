from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

# NOTE (v2026.3): numpy/sklearn intentionally NOT imported here — they live in
# requirements-ml.txt (optional 2GB stack). This router only reads stored
# VectorDistance rows; live similarity math uses backend/services/vector_explain.py
# (sentence-transformers when installed, pure-Python TF-IDF fallback otherwise).

from backend.core.database import get_db
from backend.models.models import Brand, VectorDistance, Competitor

router = APIRouter()


class VectorMeasurement(BaseModel):
    brand_id: int
    target_entities: List[str]


@router.post("/measure")
def measure_vector_distances(data: VectorMeasurement, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    results = []
    for entity in data.target_entities:
        existing = db.query(VectorDistance).filter(
            VectorDistance.brand_id == data.brand_id,
            VectorDistance.target_entity == entity
        ).order_by(VectorDistance.measurement_date.desc()).first()
        
        if existing:
            results.append({
                "target_entity": entity,
                "cosine_similarity": existing.cosine_similarity,
                "distance_score": existing.distance_score,
                "co_occurrence_terms": existing.co_occurrence_terms,
                "last_measured": existing.measurement_date.isoformat()
            })
        else:
            results.append({
                "target_entity": entity,
                "cosine_similarity": None,
                "distance_score": None,
                "status": "needs_measurement"
            })
    
    return {
        "brand": brand.name,
        "measurements": results,
        "total_entities": len(results)
    }


@router.get("/distances/{brand_id}")
def get_vector_distances(brand_id: int, db: Session = Depends(get_db)):
    distances = db.query(VectorDistance).filter(
        VectorDistance.brand_id == brand_id
    ).order_by(VectorDistance.measurement_date.desc()).all()
    
    return {
        "brand_id": brand_id,
        "distances": [
            {
                "target_entity": d.target_entity,
                "cosine_similarity": d.cosine_similarity,
                "distance_score": d.distance_score,
                "co_occurrence_terms": d.co_occurrence_terms,
                "measured_at": d.measurement_date.isoformat()
            } for d in distances
        ]
    }


@router.get("/gap-analysis/{brand_id}")
def vector_gap_analysis(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    competitors = db.query(Competitor).filter(Competitor.brand_id == brand_id).all()
    
    latest_distances = db.query(VectorDistance).filter(
        VectorDistance.brand_id == brand_id
    ).order_by(VectorDistance.measurement_date.desc()).limit(20).all()
    
    recommendations = []
    for dist in latest_distances:
        if dist.cosine_similarity and dist.cosine_similarity < 0.5:
            recommendations.append({
                "target_entity": dist.target_entity,
                "current_similarity": dist.cosine_similarity,
                "gap_size": 1.0 - dist.cosine_similarity,
                "recommendation": f"Increase co-occurrence with '{dist.target_entity}' through targeted content and PR",
                "priority": "high" if dist.cosine_similarity < 0.3 else "medium"
            })
    
    return {
        "brand": brand.name,
        "competitor_count": len(competitors),
        "vector_distances_analyzed": len(latest_distances),
        "recommendations": recommendations,
        "total_recommendations": len(recommendations)
    }


@router.post("/track/{brand_id}")
def track_vector_movement(
    brand_id: int,
    target_entity: str,
    db: Session = Depends(get_db)
):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    history = db.query(VectorDistance).filter(
        VectorDistance.brand_id == brand_id,
        VectorDistance.target_entity == target_entity
    ).order_by(VectorDistance.measurement_date.asc()).all()
    
    if len(history) < 2:
        return {
            "target_entity": target_entity,
            "data_points": len(history),
            "trend": "insufficient_data"
        }
    
    similarities = [h.cosine_similarity for h in history if h.cosine_similarity is not None]
    
    if len(similarities) >= 2:
        trend = "improving" if similarities[-1] > similarities[0] else "declining"
        change = similarities[-1] - similarities[0]
    else:
        trend = "unknown"
        change = 0
    
    return {
        "target_entity": target_entity,
        "data_points": len(history),
        "first_measurement": history[0].measurement_date.isoformat() if history else None,
        "latest_measurement": history[-1].measurement_date.isoformat() if history else None,
        "first_similarity": similarities[0] if similarities else None,
        "latest_similarity": similarities[-1] if similarities else None,
        "total_change": change,
        "trend": trend,
        "history": [
            {"date": h.measurement_date.isoformat(), "similarity": h.cosine_similarity}
            for h in history
        ]
    }

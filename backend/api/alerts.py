from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Alert, Brand

router = APIRouter()


class AlertResponse(BaseModel):
    id: int
    brand_id: int
    alert_type: str
    severity: str
    title: str
    description: Optional[str]
    data: Optional[dict]
    is_resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/")
def list_alerts(
    brand_id: Optional[int] = None,
    severity: Optional[str] = None,
    is_resolved: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Alert)
    if brand_id:
        query = query.filter(Alert.brand_id == brand_id)
    if severity:
        query = query.filter(Alert.severity == severity)
    if is_resolved is not None:
        query = query.filter(Alert.is_resolved == is_resolved)
    return query.order_by(Alert.created_at.desc()).all()


@router.get("/critical")
def critical_alerts(db: Session = Depends(get_db)):
    return db.query(Alert).filter(
        Alert.severity == "critical",
        Alert.is_resolved == False
    ).order_by(Alert.created_at.desc()).all()


@router.put("/{alert_id}/resolve")
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_resolved = True
    db.commit()
    return {"message": "Alert resolved"}


@router.get("/stats")
def alert_stats(db: Session = Depends(get_db)):
    total = db.query(func.count(Alert.id)).scalar()
    critical = db.query(func.count(Alert.id)).filter(Alert.severity == "critical", Alert.is_resolved == False).scalar()
    high = db.query(func.count(Alert.id)).filter(Alert.severity == "high", Alert.is_resolved == False).scalar()
    medium = db.query(func.count(Alert.id)).filter(Alert.severity == "medium", Alert.is_resolved == False).scalar()
    low = db.query(func.count(Alert.id)).filter(Alert.severity == "low", Alert.is_resolved == False).scalar()
    resolved = db.query(func.count(Alert.id)).filter(Alert.is_resolved == True).scalar()
    return {"total": total, "critical": critical, "high": high, "medium": medium, "low": low, "resolved": resolved}

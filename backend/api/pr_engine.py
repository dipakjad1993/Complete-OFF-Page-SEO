from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Brand, PRPitch, ComplianceRule

router = APIRouter()


class PRPitchCreate(BaseModel):
    brand_id: int
    journalist_name: Optional[str] = None
    journalist_email: Optional[str] = None
    publication: Optional[str] = None
    topic: Optional[str] = None
    pitch_subject: Optional[str] = None
    pitch_body: Optional[str] = None
    data_assets: Optional[list] = None


@router.post("/pitches")
def create_pr_pitch(pitch_data: PRPitchCreate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == pitch_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    compliance_rules = db.query(ComplianceRule).filter(
        ComplianceRule.brand_id == pitch_data.brand_id,
        ComplianceRule.is_active == True
    ).all()

    compliance_flags = []
    pitch_text = f"{pitch_data.pitch_subject or ''} {pitch_data.pitch_body or ''}".lower()

    for rule in compliance_rules:
        if rule.rule_type == "restricted_keywords":
            keywords = rule.rule_content.get("keywords", []) if isinstance(rule.rule_content, dict) else []
            for kw in keywords:
                if kw.lower() in pitch_text:
                    compliance_flags.append(f"Restricted keyword detected: {kw}")

        if rule.rule_type == "sec_restrictions":
            forward_looking = ["will", "going to", "plan to", "expect to", "projected"]
            for phrase in forward_looking:
                if phrase in pitch_text:
                    compliance_flags.append(f"Potential forward-looking statement: '{phrase}'")

    pitch = PRPitch(**pitch_data.model_dump())
    pitch.compliance_checked = True
    pitch.compliance_flags = compliance_flags if compliance_flags else None
    pitch.status = "compliance_reviewed" if not compliance_flags else "needs_review"

    db.add(pitch)
    db.commit()
    db.refresh(pitch)

    return {
        "pitch": pitch,
        "compliance_status": "passed" if not compliance_flags else "flags_detected",
        "compliance_flags": compliance_flags,
    }


@router.get("/pitches")
def list_pr_pitches(
    brand_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(PRPitch)
    if brand_id:
        query = query.filter(PRPitch.brand_id == brand_id)
    if status:
        query = query.filter(PRPitch.status == status)
    return query.order_by(PRPitch.created_at.desc()).all()


@router.get("/pitches/{pitch_id}")
def get_pr_pitch(pitch_id: int, db: Session = Depends(get_db)):
    pitch = db.query(PRPitch).filter(PRPitch.id == pitch_id).first()
    if not pitch:
        raise HTTPException(status_code=404, detail="Pitch not found")
    return pitch


@router.post("/generate-pitch")
def generate_predictive_pitch(
    brand_id: int,
    topic: str,
    journalist_name: str,
    publication: str,
    db: Session = Depends(get_db)
):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    generated_pitch = {
        "brand": brand.name,
        "topic": topic,
        "journalist": journalist_name,
        "publication": publication,
        "pitch_subject": f"Re: {topic} - perspective from {brand.name}",
        "pitch_body": f"""Hi {journalist_name},

I saw your recent coverage of {topic} in {publication} and wanted to reach out.

At {brand.name}, we work in {', '.join(brand.primary_categories or ['this industry'])} and could offer perspective for a future piece on {topic}.

[REPLACE BEFORE SENDING - add a concrete, verified data point or a specific, factual example from the brand that is directly relevant to this journalist's beat. Do not include unverified claims or made-up statistics.]

I'd be happy to arrange a brief conversation with our subject matter expert.

Best regards""",
        "draft_note": "This is a TEMPLATE draft. Every factual claim must be verified before sending; no "
                      "statistics or data points are auto-generated.",
    }

    return generated_pitch


@router.get("/data-hooks/{brand_id}")
def generate_data_hooks(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    existing = db.query(PRPitch).filter(
        PRPitch.brand_id == brand_id
    ).all()
    real_assets = []
    for p in existing:
        if p.data_assets:
            real_assets.extend(p.data_assets if isinstance(p.data_assets, list) else [p.data_assets])

    if not real_assets:
        return {
            "brand": brand.name,
            "status": "unavailable",
            "requires": "Real data assets (uploaded via the PR pitch form) or a telemetry source (GSC/GA4)",
            "detail": "No real data assets exist for this brand, so no PR data hooks are fabricated. "
                      "Add genuine data (survey results, anonymized metrics, benchmark report) first.",
            "data_hooks": [],
        }

    return {
        "brand": brand.name,
        "status": "ready",
        "data_hooks": [
            {
                "hook_type": "first_party_data",
                "title": f"{brand.name} - real data asset",
                "description": str(a)[:200],
                "data_points": "Attached asset contents (no synthesized metrics)",
                "target_journalists": ["tech_reporters", "industry_analysts"],
            } for a in real_assets[:10]
        ],
        "note": "Hooks are built strictly from data assets you actually provided.",
    }

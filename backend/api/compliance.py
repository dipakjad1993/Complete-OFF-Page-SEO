from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Brand, ComplianceRule, SponsoredCompliance

router = APIRouter()


class ComplianceRuleCreate(BaseModel):
    brand_id: int
    rule_type: str
    rule_name: str
    rule_content: dict


@router.post("/rules")
def create_compliance_rule(rule_data: ComplianceRuleCreate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == rule_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    rule = ComplianceRule(**rule_data.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/rules/{brand_id}")
def get_compliance_rules(brand_id: int, db: Session = Depends(get_db)):
    return db.query(ComplianceRule).filter(
        ComplianceRule.brand_id == brand_id,
        ComplianceRule.is_active == True
    ).all()


@router.post("/check-pitch")
def check_pitch_compliance(
    brand_id: int,
    pitch_text: str,
    db: Session = Depends(get_db)
):
    rules = db.query(ComplianceRule).filter(
        ComplianceRule.brand_id == brand_id,
        ComplianceRule.is_active == True
    ).all()
    
    violations = []
    warnings = []
    
    for rule in rules:
        if rule.rule_type == "restricted_keywords":
            keywords = rule.rule_content.get("keywords", [])
            for kw in keywords:
                if kw.lower() in pitch_text.lower():
                    violations.append({
                        "rule": rule.rule_name,
                        "type": "restricted_keyword",
                        "keyword": kw,
                        "severity": "high"
                    })
        
        elif rule.rule_type == "sec_restrictions":
            forward_looking = rule.rule_content.get("phrases", [
                "will launch", "going to release", "plan to introduce",
                "expect to see", "projected growth", "anticipated revenue"
            ])
            for phrase in forward_looking:
                if phrase.lower() in pitch_text.lower():
                    violations.append({
                        "rule": rule.rule_name,
                        "type": "forward_looking_statement",
                        "phrase": phrase,
                        "severity": "critical"
                    })
        
        elif rule.rule_type == "ftc_disclosure":
            if "sponsored" not in pitch_text.lower() and "ad" not in pitch_text.lower():
                warnings.append({
                    "rule": rule.rule_name,
                    "type": "missing_disclosure",
                    "message": "Consider adding FTC disclosure for sponsored content",
                    "severity": "medium"
                })
        
        elif rule.rule_type == "brand_guidelines":
            disallowed = rule.rule_content.get("disallowed_terms", [])
            for term in disallowed:
                if term.lower() in pitch_text.lower():
                    violations.append({
                        "rule": rule.rule_name,
                        "type": "brand_violation",
                        "term": term,
                        "severity": "high"
                    })
    
    return {
        "compliant": len(violations) == 0,
        "violations": violations,
        "warnings": warnings,
        "total_issues": len(violations) + len(warnings),
        "recommendation": "Pitch is compliant" if not violations else "Review and fix violations before sending"
    }


@router.get("/sponsored-scan/{brand_id}")
def scan_sponsored_compliance(brand_id: int, db: Session = Depends(get_db)):
    scans = db.query(SponsoredCompliance).filter(
        SponsoredCompliance.brand_id == brand_id
    ).all()
    
    non_compliant = [s for s in scans if not s.has_rel_sponsored or not s.has_ftc_disclosure]
    
    return {
        "brand_id": brand_id,
        "total_scans": len(scans),
        "compliant_count": len(scans) - len(non_compliant),
        "non_compliant_count": len(non_compliant),
        "non_compliant_details": [
            {
                "url": s.source_url,
                "domain": s.source_domain,
                "missing_rel_sponsored": not s.has_rel_sponsored,
                "missing_ftc_disclosure": not s.has_ftc_disclosure,
                "risk_level": s.compliance_risk
            } for s in non_compliant
        ]
    }


@router.post("/auto-redact")
def auto_redact_risky_content(
    brand_id: int,
    content: str,
    db: Session = Depends(get_db)
):
    rules = db.query(ComplianceRule).filter(
        ComplianceRule.brand_id == brand_id,
        ComplianceRule.is_active == True
    ).all()
    
    redacted_content = content
    redactions = []
    
    for rule in rules:
        if rule.rule_type == "auto_redact":
            patterns = rule.rule_content.get("patterns", [])
            for pattern in patterns:
                if pattern.lower() in redacted_content.lower():
                    redacted_content = redacted_content.replace(
                        pattern, "[REDACTED]"
                    )
                    redactions.append({
                        "original": pattern,
                        "replacement": "[REDACTED]",
                        "rule": rule.rule_name
                    })
    
    return {
        "original_content": content,
        "redacted_content": redacted_content,
        "redactions_applied": len(redactions),
        "redactions": redactions
    }

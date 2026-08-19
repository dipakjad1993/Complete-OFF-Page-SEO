from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import json
import os

from backend.core.database import get_db
from backend.models.models import Brand, Executive, Competitor, ComplianceRule

router = APIRouter()


class APICredentials(BaseModel):
    brand_id: int
    provider: str
    credentials: dict
    is_active: bool = True


class ExecutiveCreate(BaseModel):
    brand_id: int
    name: str
    title: Optional[str] = None
    bio: Optional[str] = None
    credentials: Optional[list] = None
    quotes: Optional[list] = None
    social_profiles: Optional[dict] = None
    expertise_areas: Optional[list] = None


class CompetitorCreate(BaseModel):
    brand_id: int
    name: str
    domain: Optional[str] = None
    wikidata_id: Optional[str] = None


class BrandSchemaInput(BaseModel):
    brand_id: int
    name: Optional[str] = None
    kg_mid: Optional[str] = None
    wikidata_id: Optional[str] = None
    crunchbase_id: Optional[str] = None
    wikipedia_url: Optional[str] = None
    logo_url: Optional[str] = None
    description: Optional[str] = None
    topical_taxonomy: Optional[dict] = None
    primary_categories: Optional[list] = None
    seed_keywords: Optional[list] = None
    official_messaging: Optional[str] = None


class ScraperConfig(BaseModel):
    brand_id: int
    sources: list
    frequency: str = "daily"
    enabled: bool = True


class RiskConfig(BaseModel):
    brand_id: int
    risk_level: str = "enterprise_safe"
    allowed_tactics: Optional[list] = None
    blocked_domains: Optional[list] = None
    blocked_topics: Optional[list] = None
    ftc_compliance: bool = True
    sec_compliance: bool = True
    max_outreach_per_day: int = 20


CREDENTIALS_FILE = "data/api_credentials.json"


def load_credentials():
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_credentials(data):
    os.makedirs("data", exist_ok=True)
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(data, f, indent=2)


CONFIG_FILE = "data/brand_configs.json"


def load_configs():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


def save_configs(data):
    os.makedirs("data", exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


@router.post("/credentials")
def save_api_credentials(cred_data: APICredentials, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == cred_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    creds = load_credentials()
    brand_key = str(cred_data.brand_id)
    if brand_key not in creds:
        creds[brand_key] = {}
    
    safe_creds = {k: v for k, v in cred_data.credentials.items() if k != "secret"}
    creds[brand_key][cred_data.provider] = {
        "credentials": cred_data.credentials,
        "is_active": cred_data.is_active,
        "updated_at": datetime.utcnow().isoformat()
    }
    save_credentials(creds)
    
    return {"message": f"Credentials saved for {cred_data.provider}", "provider": cred_data.provider}


@router.get("/credentials/{brand_id}")
def get_api_credentials(brand_id: int):
    creds = load_credentials()
    brand_creds = creds.get(str(brand_id), {})
    
    safe_output = {}
    for provider, data in brand_creds.items():
        safe_output[provider] = {
            "is_active": data.get("is_active", False),
            "updated_at": data.get("updated_at"),
            "has_key": bool(data.get("credentials", {}).get("api_key")),
            "configured_fields": list(data.get("credentials", {}).keys())
        }
    
    return {"brand_id": brand_id, "providers": safe_output}


@router.delete("/credentials/{brand_id}/{provider}")
def delete_api_credentials(brand_id: int, provider: str):
    creds = load_credentials()
    brand_key = str(brand_id)
    if brand_key in creds and provider in creds[brand_key]:
        del creds[brand_key][provider]
        save_credentials(creds)
    return {"message": f"Credentials deleted for {provider}"}


@router.post("/executives")
def create_executive(exec_data: ExecutiveCreate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == exec_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    exec_obj = Executive(**exec_data.model_dump())
    db.add(exec_obj)
    db.commit()
    db.refresh(exec_obj)
    return exec_obj


@router.get("/executives/{brand_id}")
def list_executives(brand_id: int, db: Session = Depends(get_db)):
    execs = db.query(Executive).filter(Executive.brand_id == brand_id).all()
    return [
        {
            "id": e.id, "name": e.name, "title": e.title, "bio": e.bio,
            "credentials": e.credentials, "social_profiles": e.social_profiles,
            "expertise_areas": e.expertise_areas
        } for e in execs
    ]


@router.delete("/executives/{exec_id}")
def delete_executive(exec_id: int, db: Session = Depends(get_db)):
    exec_obj = db.query(Executive).filter(Executive.id == exec_id).first()
    if not exec_obj:
        raise HTTPException(status_code=404, detail="Executive not found")
    db.delete(exec_obj)
    db.commit()
    return {"message": "Executive deleted"}


@router.post("/competitors")
def create_competitor(comp_data: CompetitorCreate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == comp_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    comp = Competitor(**comp_data.model_dump())
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


@router.get("/competitors/{brand_id}")
def list_competitors(brand_id: int, db: Session = Depends(get_db)):
    comps = db.query(Competitor).filter(Competitor.brand_id == brand_id).all()
    return [
        {"id": c.id, "name": c.name, "domain": c.domain, "wikidata_id": c.wikidata_id}
        for c in comps
    ]


@router.delete("/competitors/{comp_id}")
def delete_competitor(comp_id: int, db: Session = Depends(get_db)):
    comp = db.query(Competitor).filter(Competitor.id == comp_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competitor not found")
    db.delete(comp)
    db.commit()
    return {"message": "Competitor deleted"}


@router.post("/brand-schema")
def save_brand_schema(schema_data: BrandSchemaInput, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == schema_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    for key, value in schema_data.model_dump(exclude_unset=True).items():
        if key != "brand_id":
            setattr(brand, key, value)
    
    db.commit()
    db.refresh(brand)
    
    configs = load_configs()
    configs[str(schema_data.brand_id)] = configs.get(str(schema_data.brand_id), {})
    configs[str(schema_data.brand_id)]["schema"] = schema_data.model_dump()
    save_configs(configs)
    
    return {"message": "Brand schema saved", "brand": brand.name}


@router.get("/brand-schema/{brand_id}")
def get_brand_schema(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    return {
        "brand_id": brand.id,
        "name": brand.name,
        "domain": brand.domain,
        "kg_mid": brand.kg_mid,
        "wikidata_id": brand.wikidata_id,
        "crunchbase_id": brand.crunchbase_id,
        "wikipedia_url": brand.wikipedia_url,
        "logo_url": brand.logo_url,
        "description": brand.description,
        "topical_taxonomy": brand.topical_taxonomy,
        "primary_categories": brand.primary_categories,
        "seed_keywords": brand.seed_keywords,
    }


@router.post("/scraper-config")
def save_scraper_config(config: ScraperConfig, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == config.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    configs = load_configs()
    brand_key = str(config.brand_id)
    configs[brand_key] = configs.get(brand_key, {})
    configs[brand_key]["scraper"] = {
        "sources": config.sources,
        "frequency": config.frequency,
        "enabled": config.enabled,
        "updated_at": datetime.utcnow().isoformat()
    }
    save_configs(configs)
    
    return {"message": "Scraper configuration saved", "sources": config.sources}


@router.get("/scraper-config/{brand_id}")
def get_scraper_config(brand_id: int):
    configs = load_configs()
    scraper = configs.get(str(brand_id), {}).get("scraper", {})
    return {
        "brand_id": brand_id,
        "sources": scraper.get("sources", []),
        "frequency": scraper.get("frequency", "daily"),
        "enabled": scraper.get("enabled", False)
    }


@router.post("/risk-config")
def save_risk_config(config: RiskConfig, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == config.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    configs = load_configs()
    brand_key = str(config.brand_id)
    configs[brand_key] = configs.get(brand_key, {})
    configs[brand_key]["risk"] = {
        "risk_level": config.risk_level,
        "allowed_tactics": config.allowed_tactics,
        "blocked_domains": config.blocked_domains,
        "blocked_topics": config.blocked_topics,
        "ftc_compliance": config.ftc_compliance,
        "sec_compliance": config.sec_compliance,
        "max_outreach_per_day": config.max_outreach_per_day,
        "updated_at": datetime.utcnow().isoformat()
    }
    save_configs(configs)
    
    return {"message": "Risk configuration saved", "risk_level": config.risk_level}


@router.get("/risk-config/{brand_id}")
def get_risk_config(brand_id: int):
    configs = load_configs()
    risk = configs.get(str(brand_id), {}).get("risk", {})
    return {
        "brand_id": brand_id,
        "risk_level": risk.get("risk_level", "enterprise_safe"),
        "allowed_tactics": risk.get("allowed_tactics", []),
        "blocked_domains": risk.get("blocked_domains", []),
        "blocked_topics": risk.get("blocked_topics", []),
        "ftc_compliance": risk.get("ftc_compliance", True),
        "sec_compliance": risk.get("sec_compliance", True),
        "max_outreach_per_day": risk.get("max_outreach_per_day", 20)
    }


@router.get("/all-configs/{brand_id}")
def get_all_configs(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    configs = load_configs()
    brand_configs = configs.get(str(brand_id), {})
    creds = load_credentials().get(str(brand_id), {})
    execs = db.query(Executive).filter(Executive.brand_id == brand_id).all()
    comps = db.query(Competitor).filter(Competitor.brand_id == brand_id).all()
    rules = db.query(ComplianceRule).filter(ComplianceRule.brand_id == brand_id).all()
    
    return {
        "brand": {"id": brand.id, "name": brand.name, "domain": brand.domain},
        "schema": brand_configs.get("schema", {}),
        "api_credentials": {k: {"is_active": v.get("is_active")} for k, v in creds.items()},
        "executives": [{"id": e.id, "name": e.name, "title": e.title} for e in execs],
        "competitors": [{"id": c.id, "name": c.name} for c in comps],
        "scraper": brand_configs.get("scraper", {}),
        "risk": brand_configs.get("risk", {}),
        "compliance_rules": [{"id": r.id, "name": r.rule_name, "type": r.rule_type} for r in rules],
    }

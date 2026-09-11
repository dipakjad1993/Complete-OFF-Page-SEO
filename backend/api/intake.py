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
    # 2026 spokesperson-matrix depth: KG identity + SME flag + department.
    kg_mid: Optional[str] = None
    wikidata_id: Optional[str] = None
    wikipedia_url: Optional[str] = None
    is_sme: Optional[bool] = False
    department: Optional[str] = None


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
    # 2026 technical-API depth: GSC + GA4 property bindings (enables real
    # branded-query volume + pipeline attribution when the user connects them).
    gsc_property_id: Optional[str] = None
    ga4_property_id: Optional[str] = None
    bot_crawl_api: Optional[str] = None
    link_graph_providers: Optional[list] = None


class ScraperConfig(BaseModel):
    brand_id: int
    sources: list
    frequency: str = "daily"
    enabled: bool = True
    # 2026 listening-stream depth: transcript-first streams + crawl depth.
    listening_streams: Optional[list] = None
    include_transcripts: Optional[bool] = True
    crawl_depth: Optional[int] = 2


class RiskConfig(BaseModel):
    brand_id: int
    risk_level: str = "enterprise_safe"
    # 2026 governance depth: 0 (Fortune-50 safe) – 100 (venture aggressive) slider.
    risk_score: Optional[int] = 10
    allowed_tactics: Optional[list] = None
    blocked_domains: Optional[list] = None
    blocked_topics: Optional[list] = None
    ftc_compliance: bool = True
    sec_compliance: bool = True
    max_outreach_per_day: int = 20


CREDENTIALS_FILE = "data/api_credentials.json"


def load_credentials():
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    return {}


def save_credentials(data):
    os.makedirs("data", exist_ok=True)
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)


CONFIG_FILE = "data/brand_configs.json"


def load_configs():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    return {}


def save_configs(data):
    os.makedirs("data", exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)


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

    payload = exec_data.model_dump()
    # is_sme / department are intake-layer metadata with no DB column (yet);
    # fold them into bio so nothing is lost and the ORM never sees unknown kwargs.
    is_sme = payload.pop("is_sme", False)
    department = payload.pop("department", None)
    tags = ([f"[SME:{department}]"] if is_sme and department else
            ["[SME]"] if is_sme else
            [f"[dept: {department}]"] if department else [])
    if tags:
        payload["bio"] = (" ".join(tags) + " " + (payload.get("bio") or "")).strip()
    exec_obj = Executive(**{k: v for k, v in payload.items() if hasattr(Executive, k)})
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
            "credentials": e.credentials, "quotes": e.quotes,
            "social_profiles": e.social_profiles,
            "expertise_areas": e.expertise_areas,
            "kg_mid": e.kg_mid, "wikidata_id": e.wikidata_id,
            "wikipedia_url": e.wikipedia_url,
        } for e in execs
    ]


class ExecutiveBulkItem(BaseModel):
    name: str
    title: Optional[str] = None
    bio: Optional[str] = None
    credentials: Optional[list] = None
    quotes: Optional[list] = None
    social_profiles: Optional[dict] = None
    expertise_areas: Optional[list] = None
    linkedin: Optional[str] = None
    twitter: Optional[str] = None
    profile_url: Optional[str] = None
    source: Optional[str] = None


class ExecutiveBulkInput(BaseModel):
    brand_id: int
    executives: List[ExecutiveBulkItem]


@router.post("/executives/bulk")
def bulk_upsert_executives(payload: ExecutiveBulkInput, db: Session = Depends(get_db)):
    """Save auto-discovered spokesperson candidates in one call.

    Matches on case-insensitive name per brand (update) else inserts.
    Only stores real scraped values — never invents missing fields.
    """
    brand = db.query(Brand).filter(Brand.id == payload.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    existing = db.query(Executive).filter(Executive.brand_id == payload.brand_id).all()
    by_name = {str(e.name or '').strip().lower(): e for e in existing}
    saved, updated = 0, 0
    for item in payload.executives[:24]:
        nm = str(item.name or '').strip()
        if not nm:
            continue
        social = dict(item.social_profiles or {})
        if item.linkedin and "linkedin" not in social:
            social["linkedin"] = item.linkedin
        if item.twitter and "twitter" not in social:
            social["twitter"] = item.twitter
        if item.profile_url and "profile" not in social:
            social["profile"] = item.profile_url
        if item.source and "source" not in social:
            social["source"] = item.source
        hit = by_name.get(nm.lower())
        if hit:
            if item.title:
                hit.title = item.title
            if item.bio:
                hit.bio = item.bio
            if item.credentials is not None:
                hit.credentials = item.credentials
            if item.quotes is not None:
                hit.quotes = item.quotes
            if item.expertise_areas is not None:
                hit.expertise_areas = item.expertise_areas
            if social:
                merged = dict(hit.social_profiles or {})
                merged.update({k: v for k, v in social.items() if v})
                hit.social_profiles = merged
            updated += 1
        else:
            db.add(Executive(
                brand_id=payload.brand_id, name=nm, title=item.title,
                bio=item.bio, credentials=item.credentials, quotes=item.quotes,
                social_profiles=social or None, expertise_areas=item.expertise_areas,
            ))
            saved += 1
    db.commit()
    return {"saved": saved, "updated": updated,
            "total": saved + updated, "brand_id": payload.brand_id}


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
        if key != "brand_id" and hasattr(Brand, key):
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
        "listening_streams": config.listening_streams or [],
        "include_transcripts": config.include_transcripts if config.include_transcripts is not None else True,
        "crawl_depth": config.crawl_depth if config.crawl_depth is not None else 2,
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
        "enabled": scraper.get("enabled", False),
        "listening_streams": scraper.get("listening_streams", []),
        "include_transcripts": scraper.get("include_transcripts", True),
        "crawl_depth": scraper.get("crawl_depth", 2)
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
        "risk_score": config.risk_score if config.risk_score is not None else 10,
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
        "risk_score": risk.get("risk_score", 10),
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
        "executives": [{"id": e.id, "name": e.name, "title": e.title,
                          "bio": e.bio, "quotes": e.quotes,
                          "credentials": e.credentials,
                          "expertise_areas": e.expertise_areas,
                          "social_profiles": e.social_profiles} for e in execs],
        "competitors": [{"id": c.id, "name": c.name} for c in comps],
        "scraper": brand_configs.get("scraper", {}),
        "risk": brand_configs.get("risk", {}),
        "compliance_rules": [{"id": r.id, "name": r.rule_name, "type": r.rule_type} for r in rules],
    }

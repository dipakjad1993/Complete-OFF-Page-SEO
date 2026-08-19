from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import httpx
import json

from backend.core.database import get_db
from backend.models.models import Brand, KnowledgeGraphTriple
from config.settings import settings

router = APIRouter()


class TripleCreate(BaseModel):
    brand_id: int
    subject: str
    predicate: str
    object_value: str
    source: Optional[str] = None
    source_url: Optional[str] = None
    confidence: Optional[float] = None
    wikidata_property: Optional[str] = None


@router.post("/triples")
def create_kg_triple(triple_data: TripleCreate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == triple_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    triple = KnowledgeGraphTriple(**triple_data.model_dump())
    db.add(triple)
    db.commit()
    db.refresh(triple)
    return triple


@router.get("/triples/{brand_id}")
def get_brand_triples(brand_id: int, db: Session = Depends(get_db)):
    return db.query(KnowledgeGraphTriple).filter(
        KnowledgeGraphTriple.brand_id == brand_id
    ).all()


@router.get("/wikidata/{brand_id}")
async def check_wikidata(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    if not brand.wikidata_id:
        return {"status": "no_wikidata_id", "message": "Brand has no Wikidata ID configured"}
    
    async with httpx.AsyncClient() as client:
        url = f"https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbgetentities",
            "ids": brand.wikidata_id,
            "format": "json",
            "props": "claims|descriptions|labels|sitelinks"
        }
        response = await client.get(url, params=params)
        data = response.json()
    
    entity = data.get("entities", {}).get(brand.wikidata_id, {})
    claims = entity.get("claims", {})
    
    triples = []
    for prop_id, prop_claims in claims.items():
        for claim in prop_claims:
            mainsnak = claim.get("mainsnak", {})
            datavalue = mainsnak.get("datavalue", {})
            value = datavalue.get("value", {})
            
            if isinstance(value, dict):
                if "id" in value:
                    triples.append({"predicate": prop_id, "object": value["id"], "type": "entity"})
                elif "text" in value:
                    triples.append({"predicate": prop_id, "object": value["text"], "type": "string"})
            elif isinstance(value, str):
                triples.append({"predicate": prop_id, "object": value, "type": "string"})
    
    return {
        "wikidata_id": brand.wikidata_id,
        "entity_data": {
            "labels": entity.get("labels", {}),
            "descriptions": entity.get("descriptions", {}),
            "sitelinks": len(entity.get("sitelinks", {})),
            "claim_count": len(claims)
        },
        "extracted_triples": triples,
        "total_triples": len(triples)
    }


@router.get("/gaps/{brand_id}")
def identify_triple_gaps(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    required_predicates = [
        "P31", "P17", "P159", "P112", "P127", "P361",
        "P108", "P452", "P449", "P1813", "P2013",
        "P3403", "P3393"
    ]
    
    existing_triples = db.query(KnowledgeGraphTriple).filter(
        KnowledgeGraphTriple.brand_id == brand_id
    ).all()
    existing_predicates = set(t.predicate for t in existing_triples)
    
    gaps = []
    predicate_names = {
        "P31": "instance of",
        "P17": "country",
        "P159": "headquarters location",
        "P112": "founded by",
        "P127": "owned by",
        "P361": "part of",
        "P108": "employer",
        "P452": "industry",
        "P449": "original broadcaster",
        "P1813": "short name",
        "P2013": "Facebook ID",
        "P3403": "current owner",
        "P3393": "video search result"
    }
    
    for pred in required_predicates:
        if pred not in existing_predicates:
            gaps.append({
                "predicate": pred,
                "predicate_name": predicate_names.get(pred, pred),
                "status": "missing",
                "recommendation": f"Add {predicate_names.get(pred, pred)} triple to strengthen knowledge graph"
            })
    
    return {
        "brand": brand.name,
        "wikidata_id": brand.wikidata_id,
        "existing_triples": len(existing_triples),
        "identified_gaps": gaps,
        "total_gaps": len(gaps)
    }


@router.post("/sync-from-wikidata/{brand_id}")
async def sync_from_wikidata(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    if not brand.wikidata_id:
        raise HTTPException(status_code=400, detail="No Wikidata ID configured for this brand")
    
    async with httpx.AsyncClient() as client:
        url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbgetentities",
            "ids": brand.wikidata_id,
            "format": "json",
            "props": "claims"
        }
        response = await client.get(url, params=params)
        data = response.json()
    
    entity = data.get("entities", {}).get(brand.wikidata_id, {})
    claims = entity.get("claims", {})
    
    synced = 0
    for prop_id, prop_claims in claims.items():
        for claim in prop_claims:
            mainsnak = claim.get("mainsnak", {})
            datavalue = mainsnak.get("datavalue", {})
            value = datavalue.get("value", {})
            
            obj_val = ""
            if isinstance(value, dict):
                obj_val = value.get("id", value.get("text", str(value)))
            else:
                obj_val = str(value)
            
            existing = db.query(KnowledgeGraphTriple).filter(
                KnowledgeGraphTriple.brand_id == brand_id,
                KnowledgeGraphTriple.predicate == prop_id,
                KnowledgeGraphTriple.object_value == obj_val
            ).first()
            
            if not existing:
                triple = KnowledgeGraphTriple(
                    brand_id=brand_id,
                    subject=brand.name,
                    predicate=prop_id,
                    object_value=obj_val,
                    source="wikidata_sync",
                    wikidata_property=prop_id,
                    is_verified=True,
                    confidence=0.95
                )
                db.add(triple)
                synced += 1
    
    db.commit()
    return {"message": f"Synced {synced} new triples from Wikidata", "brand": brand.name}

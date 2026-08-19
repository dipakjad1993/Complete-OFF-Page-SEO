from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import json

from backend.core.database import get_db
from backend.models.models import Brand, SchemaProtocol

router = APIRouter()


class SchemaValidate(BaseModel):
    brand_id: int
    source_url: str
    schema_type: str
    schema_content: dict
    has_open_api: bool = False
    has_c2pa_signature: bool = False


@router.post("/validate")
def validate_schema(schema_data: SchemaValidate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == schema_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    validation_results = {
        "is_valid": True,
        "errors": [],
        "warnings": []
    }
    
    required_fields = {
        "Organization": ["name", "url"],
        "Product": ["name", "description"],
        "Article": ["headline", "author"],
        "WebPage": ["name", "url"]
    }
    
    schema_type = schema_data.schema_type.split("/")[-1]
    required = required_fields.get(schema_type, [])
    
    for field in required:
        if field not in schema_data.schema_content:
            validation_results["errors"].append(f"Missing required field: {field}")
            validation_results["is_valid"] = False
    
    if "@context" not in schema_data.schema_content:
        validation_results["warnings"].append("Missing @context (recommended: https://schema.org)")
    
    if "sameAs" not in schema_data.schema_content:
        validation_results["warnings"].append("Missing sameAs - add social media profile links")
    
    schema_record = SchemaProtocol(**schema_data.model_dump())
    schema_record.is_machine_readable = validation_results["is_valid"]
    db.add(schema_record)
    db.commit()
    db.refresh(schema_record)
    
    return {
        "schema_id": schema_record.id,
        "validation": validation_results,
        "schema_type": schema_type,
        "is_machine_readable": schema_record.is_machine_readable
    }


@router.get("/audit/{brand_id}")
def audit_schemas(brand_id: int, db: Session = Depends(get_db)):
    schemas = db.query(SchemaProtocol).filter(
        SchemaProtocol.brand_id == brand_id
    ).all()
    
    return {
        "brand_id": brand_id,
        "total_schemas": len(schemas),
        "machine_readable": sum(1 for s in schemas if s.is_machine_readable),
        "has_open_api": sum(1 for s in schemas if s.has_open_api),
        "has_c2pa": sum(1 for s in schemas if s.has_c2pa_signature),
        "schemas": [
            {
                "id": s.id,
                "url": s.source_url,
                "type": s.schema_type,
                "valid": s.is_machine_readable,
                "open_api": s.has_open_api,
                "c2pa": s.has_c2pa_signature
            } for s in schemas
        ]
    }


@router.get("/generate/{brand_id}")
def generate_optimal_schema(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    schema = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": brand.name,
        "url": f"https://{brand.domain}",
        "description": brand.description or f"{brand.name} - Official website",
        "logo": brand.logo_url or f"https://{brand.domain}/logo.png",
        "sameAs": [],
        "contactPoint": {
            "@type": "ContactPoint",
            "contactType": "customer service"
        }
    }
    
    if brand.wikipedia_url:
        schema["sameAs"].append(brand.wikipedia_url)
    if brand.wikidata_id:
        schema["sameAs"].append(f"https://www.wikidata.org/wiki/{brand.wikidata_id}")
    
    return {
        "brand": brand.name,
        "recommended_schema": schema,
        "embed_code": f"""<script type="application/ld+json">
{json.dumps(schema, indent=2)}
</script>""",
        "instructions": "Add this code to the <head> section of your homepage"
    }


@router.post("/c2pa-sign/{brand_id}")
def sign_content_c2pa(brand_id: int, content_url: str, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    c2pa_manifest = {
        "claim": {
            "name": f"{brand.name} Content Verification",
            "generator": "Off-Page SEO Engine C2PA Module",
            "assertions": [
                {"label": "c2pa.hash", "data": "content_hash"},
                {"label": "c2pa.signature", "data": "cryptographic_signature"},
                {"label": "c2pa.ingredient", "data": content_url}
            ]
        },
        "signature": "pending_generation",
        "public_key": f"-----BEGIN PUBLIC KEY-----\n{brand.domain}\n-----END PUBLIC KEY-----"
    }
    
    return {
        "brand": brand.name,
        "c2pa_manifest": c2pa_manifest,
        "instructions": "Apply this manifest to verify content authenticity for AI crawlers"
    }

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Brand, ZeroPartyDataAsset

router = APIRouter()


class ZeroPartyDataCreate(BaseModel):
    brand_id: int
    asset_name: str
    asset_type: str
    data_summary: Optional[dict] = None
    target_journalist: Optional[str] = None
    target_publication: Optional[str] = None


@router.post("/assets")
def create_data_asset(asset_data: ZeroPartyDataCreate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == asset_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    widget_embed = f"""<iframe 
    src="https://{brand.domain}/embed/data-widget/{asset_data.asset_name}" 
    width="100%" 
    height="400" 
    frameborder="0"
    title="{asset_data.asset_name}">
</iframe>"""
    
    asset = ZeroPartyDataAsset(
        **asset_data.model_dump(),
        widget_embed_code=widget_embed
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.get("/assets/{brand_id}")
def list_data_assets(brand_id: int, db: Session = Depends(get_db)):
    return db.query(ZeroPartyDataAsset).filter(
        ZeroPartyDataAsset.brand_id == brand_id
    ).all()


@router.get("/embed/{asset_id}")
def get_embed_code(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(ZeroPartyDataAsset).filter(ZeroPartyDataAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    return {
        "asset_id": asset.id,
        "asset_name": asset.asset_name,
        "embed_code": asset.widget_embed_code,
        "data_summary": asset.data_summary
    }


@router.post("/generate-widget/{brand_id}")
def generate_interactive_widget(
    brand_id: int,
    topic: str,
    db: Session = Depends(get_db)
):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    widget = {
        "brand": brand.name,
        "topic": topic,
        "widget_type": "interactive_chart",
        "embed_code": f"""<div id="data-widget-{brand.id}"></div>
<script src="https://{brand.domain}/widgets/data-embed.js"></script>
<script>
  DataWidget.init({{
    container: '#data-widget-{brand.id}',
    brand: '{brand.name}',
    topic: '{topic}',
    theme: 'light',
    interactive: true
  }});
</script>""",
        "data_points": [
            {"label": "Metric 1", "value": "dynamic", "source": "first_party_data"},
            {"label": "Metric 2", "value": "dynamic", "source": "first_party_data"}
        ],
        "journalist_instructions": f"Embed this interactive widget in your article about {topic}. The data updates dynamically from {brand.name}'s API."
    }
    
    return widget


@router.get("/syndication-pitch/{brand_id}")
def generate_syndication_pitch(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    assets = db.query(ZeroPartyDataAsset).filter(
        ZeroPartyDataAsset.brand_id == brand_id
    ).all()
    
    pitch = {
        "brand": brand.name,
        "subject": f"Exclusive Data: {brand.name} Industry Insights for Your Coverage",
        "body": f"""Hi [Journalist Name],

I saw your recent piece on industry trends. We have some exclusive first-party data from {brand.name} that could add depth to your reporting.

Available data widgets:
{chr(10).join(f"- {a.asset_name} ({a.asset_type})" for a in assets)}

These are interactive, embeddable widgets with real-time data that your readers can explore directly in the article.

Would you like access to any of these data assets?

Best regards""",
        "available_assets": len(assets),
        "value_proposition": "Free, exclusive, interactive data widgets for your articles"
    }
    
    return pitch

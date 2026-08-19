from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Brand, PassageAttention, Backlink

router = APIRouter()


class PassageScore(BaseModel):
    brand_id: int
    source_url: str
    passage_text: str
    has_backlink: bool = False


@router.post("/score")
def score_passage(passage_data: PassageScore, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == passage_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    tokens = passage_data.passage_text.split()
    token_count = len(tokens)
    
    attention_weight = min(1.0, token_count / 250)
    
    brand_mentions = passage_data.passage_text.lower().count(brand.name.lower())
    keyword_hits = sum(1 for kw in (brand.seed_keywords or []) 
                      if kw.lower() in passage_data.passage_text.lower())
    
    relevance_score = (brand_mentions * 0.3 + keyword_hits * 0.2 + attention_weight * 0.5)
    
    passage = PassageAttention(
        brand_id=passage_data.brand_id,
        source_url=passage_data.source_url,
        passage_text=passage_data.passage_text,
        passage_tokens=token_count,
        attention_weight=round(attention_weight, 4),
        cosine_similarity=round(relevance_score, 4),
        has_backlink=passage_data.has_backlink,
        scored_at=datetime.utcnow()
    )
    db.add(passage)
    db.commit()
    db.refresh(passage)
    
    return {
        "passage_id": passage.id,
        "source_url": passage_data.source_url,
        "token_count": token_count,
        "attention_weight": passage.attention_weight,
        "cosine_similarity": passage.cosine_similarity,
        "brand_mentions": brand_mentions,
        "keyword_hits": keyword_hits,
        "quality_rating": "high" if passage.cosine_similarity > 0.7 else
                         "medium" if passage.cosine_similarity > 0.4 else "low",
        "recommendation": "This passage carries strong search weight" if passage.attention_weight > 0.7
                         else "Consider placing content in higher-attention passages"
    }


@router.get("/analysis/{brand_id}")
def analyze_passage_distribution(brand_id: int, db: Session = Depends(get_db)):
    passages = db.query(PassageAttention).filter(
        PassageAttention.brand_id == brand_id
    ).all()
    
    if not passages:
        return {"message": "No passages analyzed yet"}
    
    high_attention = [p for p in passages if p.attention_weight > 0.7]
    medium_attention = [p for p in passages if 0.4 <= p.attention_weight <= 0.7]
    low_attention = [p for p in passages if p.attention_weight < 0.4]
    
    with_backlinks = [p for p in passages if p.has_backlink]
    high_value_with_links = [p for p in with_backlinks if p.attention_weight > 0.7]
    
    avg_similarity = sum(p.cosine_similarity for p in passages) / len(passages)
    
    return {
        "brand_id": brand_id,
        "total_passages": len(passages),
        "distribution": {
            "high_attention": len(high_attention),
            "medium_attention": len(medium_attention),
            "low_attention": len(low_attention)
        },
        "link_analysis": {
            "total_with_backlinks": len(with_backlinks),
            "high_value_with_links": len(high_value_with_links),
            "link_placement_quality": len(high_value_with_links) / len(with_backlinks) * 100 if with_backlinks else 0
        },
        "avg_cosine_similarity": round(avg_similarity, 4),
        "recommendation": f"{len(high_value_with_links)} backlinks are in high-attention passages. " +
                         f"{len(with_backlinks) - len(high_value_with_links)} backlinks could be moved to better positions."
    }


@router.get("/low-value/{brand_id}")
def find_low_value_passages(brand_id: int, db: Session = Depends(get_db)):
    passages = db.query(PassageAttention).filter(
        PassageAttention.brand_id == brand_id,
        PassageAttention.has_backlink == True,
        PassageAttention.attention_weight < 0.4
    ).all()
    
    return {
        "brand_id": brand_id,
        "low_value_passages": len(passages),
        "passages": [
            {
                "id": p.id,
                "source_url": p.source_url,
                "passage_text": p.passage_text[:200],
                "attention_weight": p.attention_weight,
                "cosine_similarity": p.cosine_similarity,
                "recommendation": "Move backlink to a passage with higher attention weight"
            } for p in passages
        ]
    }

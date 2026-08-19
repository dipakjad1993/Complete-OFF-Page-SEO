from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Brand, RedditConsensus

router = APIRouter()


class RedditMentionCreate(BaseModel):
    brand_id: int
    subreddit: str
    thread_url: str
    brand_mentioned: bool = True
    mention_context: Optional[str] = None
    sentiment: Optional[float] = None
    paired_terms: Optional[list] = None
    competitor_mentions: Optional[list] = None


@router.post("/track")
def track_reddit_mention(mention_data: RedditMentionCreate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == mention_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    mention = RedditConsensus(**mention_data.model_dump())
    db.add(mention)
    db.commit()
    db.refresh(mention)
    return mention


@router.get("/mentions/{brand_id}")
def list_reddit_mentions(
    brand_id: int,
    subreddit: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(RedditConsensus).filter(RedditConsensus.brand_id == brand_id)
    if subreddit:
        query = query.filter(RedditConsensus.subreddit == subreddit)
    return query.order_by(RedditConsensus.scraped_at.desc()).all()


@router.get("/sentiment/{brand_id}")
def get_reddit_sentiment(brand_id: int, db: Session = Depends(get_db)):
    mentions = db.query(RedditConsensus).filter(
        RedditConsensus.brand_id == brand_id
    ).all()
    
    if not mentions:
        return {"message": "No Reddit mentions tracked"}
    
    sentiments = [m.sentiment for m in mentions if m.sentiment is not None]
    avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0
    
    subreddit_sentiments = {}
    for m in mentions:
        sub = m.subreddit
        if sub not in subreddit_sentiments:
            subreddit_sentiments[sub] = {"count": 0, "sentiments": []}
        subreddit_sentiments[sub]["count"] += 1
        if m.sentiment is not None:
            subreddit_sentiments[sub]["sentiments"].append(m.sentiment)
    
    for sub in subreddit_sentiments:
        sents = subreddit_sentiments[sub]["sentiments"]
        subreddit_sentiments[sub]["avg_sentiment"] = sum(sents) / len(sents) if sents else 0
        del subreddit_sentiments[sub]["sentiments"]
    
    return {
        "brand_id": brand_id,
        "total_mentions": len(mentions),
        "average_sentiment": round(avg_sentiment, 4),
        "by_subreddit": subreddit_sentiments,
        "sentiment_trend": "positive" if avg_sentiment > 0.3 else "negative" if avg_sentiment < -0.3 else "neutral"
    }


@router.get("/co-occurrence/{brand_id}")
def get_co_occurrence(brand_id: int, db: Session = Depends(get_db)):
    mentions = db.query(RedditConsensus).filter(
        RedditConsensus.brand_id == brand_id
    ).all()
    
    term_frequency = {}
    competitor_frequency = {}
    
    for m in mentions:
        if m.paired_terms:
            for term in m.paired_terms:
                term_frequency[term] = term_frequency.get(term, 0) + 1
        
        if m.competitor_mentions:
            for comp in m.competitor_mentions:
                competitor_frequency[comp] = competitor_frequency.get(comp, 0) + 1
    
    return {
        "brand_id": brand_id,
        "co_occurring_terms": dict(sorted(term_frequency.items(), key=lambda x: x[1], reverse=True)[:20]),
        "competitor_mentions": dict(sorted(competitor_frequency.items(), key=lambda x: x[1], reverse=True)[:10]),
        "recommendation": "Focus content on frequently co-occurring terms to strengthen entity associations"
    }


@router.get("/threads/{brand_id}")
def get_brand_threads(brand_id: int, db: Session = Depends(get_db)):
    mentions = db.query(RedditConsensus).filter(
        RedditConsensus.brand_id == brand_id,
        RedditConsensus.brand_mentioned == True
    ).all()
    
    return {
        "brand_id": brand_id,
        "total_threads": len(mentions),
        "threads": [
            {
                "subreddit": m.subreddit,
                "url": m.thread_url,
                "context": m.mention_context,
                "sentiment": m.sentiment,
                "date": m.scraped_at.isoformat() if m.scraped_at else None
            } for m in mentions
        ]
    }

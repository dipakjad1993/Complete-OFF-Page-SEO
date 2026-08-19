from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Brand, ConsensusScore, BrandMention, RedditConsensus

router = APIRouter()


class ConsensusMeasurement(BaseModel):
    brand_id: int
    overall_sentiment: Optional[float] = None
    reddit_sentiment: Optional[float] = None
    forum_sentiment: Optional[float] = None
    review_sentiment: Optional[float] = None
    media_sentiment: Optional[float] = None
    total_mentions: int = 0
    positive_mentions: int = 0
    negative_mentions: int = 0
    neutral_mentions: int = 0


@router.post("/measure")
def measure_consensus(data: ConsensusMeasurement, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    total = data.positive_mentions + data.negative_mentions + data.neutral_mentions
    if total > 0:
        net_sentiment = (data.positive_mentions - data.negative_mentions) / total
    else:
        net_sentiment = 0
    
    consensus = ConsensusScore(
        brand_id=data.brand_id,
        overall_sentiment=data.overall_sentiment,
        reddit_sentiment=data.reddit_sentiment,
        forum_sentiment=data.forum_sentiment,
        review_sentiment=data.review_sentiment,
        media_sentiment=data.media_sentiment,
        total_mentions=data.total_mentions,
        positive_mentions=data.positive_mentions,
        negative_mentions=data.negative_mentions,
        neutral_mentions=data.neutral_mentions,
        consensus_gap=1.0 - abs(net_sentiment),
        measured_at=datetime.utcnow()
    )
    db.add(consensus)
    db.commit()
    db.refresh(consensus)
    return consensus


@router.get("/score/{brand_id}")
def get_consensus_score(brand_id: int, db: Session = Depends(get_db)):
    latest = db.query(ConsensusScore).filter(
        ConsensusScore.brand_id == brand_id
    ).order_by(ConsensusScore.measured_at.desc()).first()
    
    if not latest:
        return {"message": "No consensus data available", "score": None}
    
    return {
        "brand_id": brand_id,
        "overall_sentiment": latest.overall_sentiment,
        "reddit_sentiment": latest.reddit_sentiment,
        "forum_sentiment": latest.forum_sentiment,
        "review_sentiment": latest.review_sentiment,
        "media_sentiment": latest.media_sentiment,
        "total_mentions": latest.total_mentions,
        "sentiment_breakdown": {
            "positive": latest.positive_mentions,
            "negative": latest.negative_mentions,
            "neutral": latest.neutral_mentions
        },
        "consensus_gap": latest.consensus_gap,
        "measured_at": latest.measured_at.isoformat()
    }


@router.get("/history/{brand_id}")
def consensus_history(brand_id: int, db: Session = Depends(get_db)):
    history = db.query(ConsensusScore).filter(
        ConsensusScore.brand_id == brand_id
    ).order_by(ConsensusScore.measured_at.desc()).limit(30).all()
    
    return {
        "brand_id": brand_id,
        "history": [
            {
                "date": h.measured_at.isoformat(),
                "overall": h.overall_sentiment,
                "reddit": h.reddit_sentiment,
                "media": h.media_sentiment,
                "total_mentions": h.total_mentions
            } for h in history
        ]
    }


@router.get("/gaps/{brand_id}")
def identify_consensus_gaps(brand_id: int, db: Session = Depends(get_db)):
    latest = db.query(ConsensusScore).filter(
        ConsensusScore.brand_id == brand_id
    ).order_by(ConsensusScore.measured_at.desc()).first()
    
    if not latest:
        return {"message": "No consensus data available"}
    
    gaps = []
    
    if latest.reddit_sentiment is not None and latest.reddit_sentiment < 0.3:
        gaps.append({
            "channel": "Reddit",
            "current_score": latest.reddit_sentiment,
            "gap": 0.5 - latest.reddit_sentiment,
            "priority": "high",
            "recommendation": "Increase authentic community engagement on relevant subreddits"
        })
    
    if latest.media_sentiment is not None and latest.media_sentiment < 0.4:
        gaps.append({
            "channel": "Media",
            "current_score": latest.media_sentiment,
            "gap": 0.6 - latest.media_sentiment,
            "priority": "high",
            "recommendation": "Launch proactive digital PR campaign with tier-1 publications"
        })
    
    if latest.review_sentiment is not None and latest.review_sentiment < 0.5:
        gaps.append({
            "channel": "Reviews",
            "current_score": latest.review_sentiment,
            "gap": 0.7 - latest.review_sentiment,
            "priority": "medium",
            "recommendation": "Implement customer review generation program"
        })
    
    if latest.forum_sentiment is not None and latest.forum_sentiment < 0.4:
        gaps.append({
            "channel": "Forums",
            "current_score": latest.forum_sentiment,
            "gap": 0.5 - latest.forum_sentiment,
            "priority": "medium",
            "recommendation": "Engage in industry forums and Q&A platforms"
        })
    
    return {
        "brand_id": brand_id,
        "overall_consensus_gap": latest.consensus_gap,
        "identified_gaps": gaps,
        "total_gaps": len(gaps),
        "recommendation": "Focus on channels with highest priority gaps to improve AI Overview inclusion"
    }


@router.get("/reddit/{brand_id}")
def get_reddit_consensus(brand_id: int, db: Session = Depends(get_db)):
    reddit_mentions = db.query(RedditConsensus).filter(
        RedditConsensus.brand_id == brand_id
    ).all()
    
    if not reddit_mentions:
        return {"message": "No Reddit consensus data available"}
    
    sentiments = [r.sentiment for r in reddit_mentions if r.sentiment is not None]
    avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0
    
    subreddits = {}
    for r in reddit_mentions:
        sub = r.subreddit
        if sub not in subreddits:
            subreddits[sub] = {"mentions": 0, "avg_sentiment": 0, "sentiments": []}
        subreddits[sub]["mentions"] += 1
        if r.sentiment is not None:
            subreddits[sub]["sentiments"].append(r.sentiment)
    
    for sub in subreddits:
        sents = subreddits[sub]["sentiments"]
        subreddits[sub]["avg_sentiment"] = sum(sents) / len(sents) if sents else 0
        del subreddits[sub]["sentiments"]
    
    return {
        "brand_id": brand_id,
        "total_mentions": len(reddit_mentions),
        "average_sentiment": avg_sentiment,
        "by_subreddit": subreddits,
        "recommendation": "Monitor and engage with subreddits showing negative sentiment trends"
    }

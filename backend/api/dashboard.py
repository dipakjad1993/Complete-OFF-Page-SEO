from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta

from backend.core.database import get_db
from backend.models.models import (
    Brand, BrandMention, Backlink, Alert, Campaign,
    ToxicBacklink, RAGCitation, ConsensusScore, ShareOfSearch,
    VectorDistance, AnchorTextProfile, KnowledgeGraphTriple
)

router = APIRouter()


@router.get("/{brand_id}")
def executive_dashboard(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        return {"error": "Brand not found"}

    total_mentions = db.query(func.count(BrandMention.id)).filter(BrandMention.brand_id == brand_id).scalar()
    linked_mentions = db.query(func.count(BrandMention.id)).filter(
        BrandMention.brand_id == brand_id, BrandMention.has_link == True
    ).scalar()
    unlinked_mentions = db.query(func.count(BrandMention.id)).filter(
        BrandMention.brand_id == brand_id, BrandMention.has_link == False
    ).scalar()
    
    total_backlinks = db.query(func.count(Backlink.id)).filter(Backlink.brand_id == brand_id).scalar()
    toxic_backlinks = db.query(func.count(ToxicBacklink.id)).filter(ToxicBacklink.brand_id == brand_id).scalar()
    dofollow_links = db.query(func.count(Backlink.id)).filter(
        Backlink.brand_id == brand_id, Backlink.is_dofollow == True
    ).scalar()
    
    active_alerts = db.query(func.count(Alert.id)).filter(
        Alert.brand_id == brand_id, Alert.is_resolved == False
    ).scalar()
    critical_alerts = db.query(func.count(Alert.id)).filter(
        Alert.brand_id == brand_id, Alert.severity == "critical", Alert.is_resolved == False
    ).scalar()
    
    latest_consensus = db.query(ConsensusScore).filter(
        ConsensusScore.brand_id == brand_id
    ).order_by(ConsensusScore.measured_at.desc()).first()
    
    latest_sos = db.query(ShareOfSearch).filter(
        ShareOfSearch.brand_id == brand_id
    ).order_by(ShareOfSearch.measured_at.desc()).first()
    
    rag_citations = db.query(func.count(RAGCitation.id)).filter(
        RAGCitation.brand_id == brand_id
    ).scalar()
    rag_hallucinations = db.query(func.count(RAGCitation.id)).filter(
        RAGCitation.brand_id == brand_id, RAGCitation.hallucination_detected == True
    ).scalar()
    
    latest_vectors = db.query(VectorDistance).filter(
        VectorDistance.brand_id == brand_id
    ).order_by(VectorDistance.measurement_date.desc()).limit(5).all()
    
    active_campaigns = db.query(func.count(Campaign.id)).filter(
        Campaign.brand_id == brand_id, Campaign.status == "active"
    ).scalar()
    
    kg_triples = db.query(func.count(KnowledgeGraphTriple.id)).filter(
        KnowledgeGraphTriple.brand_id == brand_id
    ).scalar()

    return {
        "brand": {"id": brand.id, "name": brand.name, "domain": brand.domain},
        "mention_metrics": {
            "total_mentions": total_mentions,
            "linked_mentions": linked_mentions,
            "unlinked_mentions": unlinked_mentions,
            "link_conversion_rate": round((linked_mentions / total_mentions * 100), 2) if total_mentions > 0 else None
        },
        "backlink_metrics": {
            "total_backlinks": total_backlinks,
            "dofollow_links": dofollow_links,
            "toxic_backlinks": toxic_backlinks,
            "link_health_score": round(((total_backlinks - toxic_backlinks) / total_backlinks * 100), 2) if total_backlinks > 0 else None
        },
        "alert_metrics": {
            "active_alerts": active_alerts,
            "critical_alerts": critical_alerts
        },
        "consensus": {
            "overall_sentiment": latest_consensus.overall_sentiment if latest_consensus else None,
            "reddit_sentiment": latest_consensus.reddit_sentiment if latest_consensus else None,
            "media_sentiment": latest_consensus.media_sentiment if latest_consensus else None,
            "total_mentions_analyzed": latest_consensus.total_mentions if latest_consensus else 0
        },
        "share_of_search": {
            "market_share_pct": latest_sos.market_share_pct if latest_sos else None,
            "revenue_attributed": latest_sos.revenue_attributed if latest_sos else None,
            "period": latest_sos.period if latest_sos else None
        },
        "rag_monitoring": {
            "total_citations": rag_citations,
            "hallucinations_detected": rag_hallucinations,
            "accuracy_rate": round(((rag_citations - rag_hallucinations) / rag_citations * 100), 2) if rag_citations > 0 else None
        },
        "vector_distances": [
            {
                "target_entity": v.target_entity,
                "cosine_similarity": v.cosine_similarity,
                "distance_score": v.distance_score
            } for v in latest_vectors
        ],
        "campaigns": {"active_count": active_campaigns},
        "knowledge_graph": {"total_triples": kg_triples}
    }


@router.get("/{brand_id}/revenue-impact")
def revenue_impact(brand_id: int, db: Session = Depends(get_db)):
    sos_records = db.query(ShareOfSearch).filter(
        ShareOfSearch.brand_id == brand_id
    ).order_by(ShareOfSearch.measured_at.desc()).limit(12).all()
    
    if not sos_records:
        return {"message": "No Share of Search data available", "data": []}
    
    return {
        "brand_id": brand_id,
        "revenue_history": [
            {
                "period": s.period,
                "search_volume": s.search_volume,
                "market_share_pct": s.market_share_pct,
                "revenue_attributed": s.revenue_attributed,
                "source": s.source
            } for s in sos_records
        ],
        "total_revenue_attributed": sum(s.revenue_attributed or 0 for s in sos_records),
        "avg_market_share": sum(s.market_share_pct or 0 for s in sos_records) / len(sos_records) if sos_records else 0
    }

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Brand, PodcastPitch
from backend.services.search import search_web, verify_url
from backend.services.verification import is_verified, is_unavailable, utcnow_iso

router = APIRouter()

PODCAST_VIDEO_DOMAINS = ["podcasts.apple.com", "open.spotify.com", "youtube.com", "www.youtube.com",
                         "podbean.com", "spreaker.com", "iheart.com", "buzzsprout.com",
                         "podcast.apple.com", "anchor.fm", "vimeo.com", "twitch.tv"]


class PodcastPitchCreate(BaseModel):
    brand_id: int
    podcast_name: str
    podcast_url: Optional[str] = None
    host_name: Optional[str] = None
    episode_title: Optional[str] = None
    transcript_snippet: Optional[str] = None


@router.post("/detect")
async def detect_podcast_mentions(pitch_data: PodcastPitchCreate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == pitch_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    # Honest detection: verify the supplied podcast page actually mentions the brand.
    brand_mentioned = None
    has_link = None
    verification_note = ""
    if pitch_data.podcast_url:
        v = await verify_url(pitch_data.podcast_url, [brand.name, brand.domain or ""])
        if is_verified(v):
            brand_mentioned = v.value
            has_link = bool(v.metadata.get("terms_found") and any(
                (brand.domain and t.lower() == brand.domain.lower()) or t.lower() in (brand.domain or "").lower()
                for t in v.metadata.get("terms_found", [])))
            verification_note = "Live page fetch confirmed" + ("" if brand_mentioned else " no brand mention found.")
        else:
            verification_note = v.reason if is_unavailable(v) else "Could not verify page."
    else:
        verification_note = "No podcast URL supplied, so the mention could not be verified."

    pitch = PodcastPitch(**pitch_data.model_dump())
    pitch.brand_mentioned = bool(brand_mentioned)
    db.add(pitch)
    db.commit()
    db.refresh(pitch)

    return {
        "detection": {
            "podcast": pitch_data.podcast_name,
            "brand_mentioned": brand_mentioned,
            "has_link": has_link,
            "transcript_available": bool(pitch_data.transcript_snippet),
            "verification_note": verification_note,
        },
        "pitch": pitch,
    }


@router.get("/pitches/{brand_id}")
def list_podcast_pitches(
    brand_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(PodcastPitch).filter(PodcastPitch.brand_id == brand_id)
    if status:
        query = query.filter(PodcastPitch.pitch_status == status)
    return query.order_by(PodcastPitch.created_at.desc()).all()


@router.get("/search/{brand_id}")
async def search_podcast_opportunities(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    categories = brand.primary_categories or []
    keywords = brand.seed_keywords or []
    queries = [f'{brand.name} podcast', f'{brand.name} interview podcast']
    if keywords:
        queries.append(f'{keywords[0]} podcast guest')

    opportunities = []
    seen = set()
    for q in queries:
        res = await search_web(q, brand_name=brand.name, num=8)
        if not is_verified(res):
            continue
        for r in res.value:
            url = r.get("url", "")
            domain = (r.get("domain") or "").replace("www.", "")
            if url in seen or domain not in PODCAST_VIDEO_DOMAINS:
                continue
            seen.add(url)
            opportunities.append({
                "name": r.get("title", "")[:120],
                "url": url,
                "domain": domain,
                "relevance": r.get("relevance_score", 0),
                "snippet": r.get("snippet", "")[:250],
            })

    return {
        "brand": brand.name,
        "search_criteria": {
            "categories": categories,
            "keywords": keywords[:10],
            "queries": queries,
        },
        "recommended_podcasts": opportunities[:20],
        "total_opportunities": len(opportunities),
        "note": "Every recommended podcast is a real page surfaced by live search; none are synthesized.",
        "retrieved_at": utcnow_iso(),
    }


@router.get("/transcript-scan/{brand_id}")
def scan_transcripts(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    mentions = db.query(PodcastPitch).filter(
        PodcastPitch.brand_id == brand_id,
        PodcastPitch.brand_mentioned == True
    ).all()

    return {
        "brand": brand.name,
        "total_mentions": len(mentions),
        "mentions_without_links": sum(1 for m in mentions if not m.has_link),
        "pitches_sent": sum(1 for m in mentions if m.pitch_status == "outreach_sent"),
        "mentions": [
            {
                "podcast": m.podcast_name,
                "episode": m.episode_title,
                "host": m.host_name,
                "has_link": m.has_link,
                "status": m.pitch_status,
            } for m in mentions
        ],
        "note": "Counts reflect only podcast mentions you have actually logged/verified in this system.",
    }


@router.post("/generate-pitch-deck/{pitch_id}")
def generate_pitch_deck(pitch_id: int, db: Session = Depends(get_db)):
    pitch = db.query(PodcastPitch).filter(PodcastPitch.id == pitch_id).first()
    if not pitch:
        raise HTTPException(status_code=404, detail="Pitch not found")

    brand = db.query(Brand).filter(Brand.id == pitch.brand_id).first()

    pitch_deck = {
        "podcast_name": pitch.podcast_name,
        "host_name": pitch.host_name,
        "brand": brand.name,
        "template_note": "Template text only. Replace claims with verified facts from the brand before sending.",
        "slides": [
            {"slide": 1, "title": "Introduction", "content": f"Guest pitch for {brand.name} executive on {pitch.podcast_name}"},
            {"slide": 2, "title": "Expert Credentials", "content": f"Subject matter expertise in {', '.join(brand.primary_categories or [])}"},
            {"slide": 3, "title": "Topic Proposal", "content": f"Insights on {brand.seed_keywords[0] if brand.seed_keywords else 'industry trends'} and emerging patterns"},
            {"slide": 4, "title": "Value Proposition", "content": f"Exclusive data and first-party insights from {brand.name}"},
            {"slide": 5, "title": "Call to Action", "content": "Schedule recording session and prepare custom content"},
        ],
    }

    return pitch_deck

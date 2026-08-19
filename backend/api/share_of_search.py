from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Brand, ShareOfSearch
from backend.services.providers import serpapi
from backend.services.verification import is_verified, utcnow_iso

router = APIRouter()


class ShareOfSearchCreate(BaseModel):
    brand_id: int
    brand_name: Optional[str] = None
    search_volume: Optional[int] = None
    market_share_pct: Optional[float] = None
    revenue_attributed: Optional[float] = None
    period: Optional[str] = None
    source: Optional[str] = None


@router.post("/record")
def record_share_of_search(sos_data: ShareOfSearchCreate, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == sos_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    if not sos_data.brand_name:
        sos_data.brand_name = brand.name
    if not sos_data.source:
        sos_data.source = "manual_user_entry"

    sos = ShareOfSearch(**sos_data.model_dump())
    db.add(sos)
    db.commit()
    db.refresh(sos)
    return sos


@router.get("/measure/{brand_id}")
async def measure_share_of_search(brand_id: int, db: Session = Depends(get_db)):
    """Real SERP-share measurement via SerpAPI; records the verified result."""
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    if not serpapi.available:
        return {
            "brand": brand.name,
            "status": "unavailable",
            "requires": "SERPAPI_KEY",
            "detail": "Real SERP measurement needs a SerpAPI key. No share was guessed.",
        }

    cat = (brand.primary_categories or ["technology"])[0]
    queries = [brand.name, cat]
    measurements = []
    for q in queries:
        r = await serpapi.search(q, num=10)
        if not is_verified(r):
            continue
        results = r.value or []
        total = len(results)
        hits = sum(1 for x in results if brand.name.lower() in (x.get("title", "") + " " + x.get("url", "")).lower())
        share = round(hits / total * 100, 2) if total else None
        measurements.append({
            "query": q,
            "total_results": total,
            "brand_results": hits,
            "share_pct": share,
        })

    if not measurements:
        return {"brand": brand.name, "status": "unavailable", "requires": "SERPAPI_KEY", "detail": "SerpAPI query failed."}

    primary = measurements[0].get("share_pct")
    sos = ShareOfSearch(
        brand_id=brand.id,
        brand_name=brand.name,
        market_share_pct=primary,
        search_volume=measurements[0].get("total_results"),
        period=datetime.utcnow().strftime("%Y-%m"),
        source="serpapi_live_measurement",
    )
    db.add(sos)
    db.commit()
    db.refresh(sos)

    return {
        "brand": brand.name,
        "status": "measured",
        "measurements": measurements,
        "recorded": {"id": sos.id, "market_share_pct": sos.market_share_pct, "measured_at": sos.measured_at.isoformat()},
        "retrieved_at": utcnow_iso(),
    }


@router.get("/current/{brand_id}")
def get_current_share(brand_id: int, db: Session = Depends(get_db)):
    latest = db.query(ShareOfSearch).filter(
        ShareOfSearch.brand_id == brand_id
    ).order_by(ShareOfSearch.measured_at.desc()).first()

    if not latest:
        return {"message": "No Share of Search data available", "status": "no_data"}

    return {
        "brand_id": brand_id,
        "brand_name": latest.brand_name,
        "market_share_pct": latest.market_share_pct,
        "search_volume": latest.search_volume,
        "revenue_attributed": latest.revenue_attributed,
        "period": latest.period,
        "source": latest.source,
        "measured_at": latest.measured_at.isoformat(),
        "status": "ok",
    }


@router.get("/history/{brand_id}")
def share_history(brand_id: int, db: Session = Depends(get_db)):
    history = db.query(ShareOfSearch).filter(
        ShareOfSearch.brand_id == brand_id
    ).order_by(ShareOfSearch.measured_at.desc()).limit(24).all()

    return {
        "brand_id": brand_id,
        "history": [
            {
                "period": h.period,
                "market_share_pct": h.market_share_pct,
                "search_volume": h.search_volume,
                "revenue_attributed": h.revenue_attributed,
                "source": h.source,
                "date": h.measured_at.isoformat(),
            } for h in history
        ]
    }


@router.get("/trend/{brand_id}")
def share_trend(brand_id: int, db: Session = Depends(get_db)):
    history = db.query(ShareOfSearch).filter(
        ShareOfSearch.brand_id == brand_id
    ).order_by(ShareOfSearch.measured_at.asc()).all()

    if len(history) < 2:
        return {"message": "Insufficient data for trend analysis", "status": "no_data"}

    shares = [h.market_share_pct for h in history if h.market_share_pct is not None]

    if len(shares) < 2:
        return {"message": "Insufficient share data", "status": "no_data"}

    recent = shares[-6:] if len(shares) >= 6 else shares
    earlier = shares[:-6] if len(shares) > 6 else shares[:len(shares) // 2]

    avg_recent = sum(recent) / len(recent)
    avg_earlier = sum(earlier) / len(earlier) if earlier else avg_recent

    change = avg_recent - avg_earlier
    change_pct = (change / avg_earlier * 100) if avg_earlier > 0 else 0

    return {
        "brand_id": brand_id,
        "current_share": shares[-1],
        "previous_avg": round(avg_earlier, 2),
        "recent_avg": round(avg_recent, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "trend": "growing" if change > 0 else "declining" if change < 0 else "stable",
        "status": "ok",
        "note": "Trend is computed only from real recorded measurements.",
    }


@router.get("/revenue-attribution/{brand_id}")
def revenue_attribution(brand_id: int, db: Session = Depends(get_db)):
    records = db.query(ShareOfSearch).filter(
        ShareOfSearch.brand_id == brand_id
    ).order_by(ShareOfSearch.measured_at.desc()).limit(12).all()

    if not records:
        return {"message": "No revenue attribution data available", "status": "no_data"}

    total_revenue = sum(r.revenue_attributed or 0 for r in records)
    avg_share = sum(r.market_share_pct or 0 for r in records) / len(records)

    return {
        "brand_id": brand_id,
        "periods_analyzed": len(records),
        "total_revenue_attributed": total_revenue,
        "avg_market_share": round(avg_share, 2),
        "revenue_per_share_point": round(total_revenue / avg_share, 2) if avg_share > 0 else None,
        "attribution_source": records[0].source if records else "unknown",
        "note": "Revenue attribution reflects only values you supplied or that were measured with real data.",
    }

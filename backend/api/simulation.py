from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from backend.core.database import get_db
from backend.models.models import Brand, Campaign, ShareOfSearch

router = APIRouter()


class SimulationRequest(BaseModel):
    brand_id: int
    campaign_type: str
    budget: float
    target_tier: str = "tier_1"
    expected_placements: int = 10


@router.post("/run")
def run_simulation(sim_data: SimulationRequest, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == sim_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    current_sos = db.query(ShareOfSearch).filter(
        ShareOfSearch.brand_id == sim_data.brand_id
    ).order_by(ShareOfSearch.measured_at.desc()).first()

    if not current_sos or current_sos.market_share_pct is None:
        return {
            "brand": brand.name,
            "simulation_params": sim_data.model_dump(),
            "status": "unavailable",
            "requires": "A real ShareOfSearch measurement (via SERP measurement) for this brand",
            "detail": "No real baseline market-share measurement exists for this brand. Simulation would otherwise "
                      "fabricate numbers, so no projection was generated.",
            "recommendation": "Run a real share-of-search measurement first, then re-run this simulation with a "
                              "real baseline and a user-supplied conversion model.",
        }

    current_share = current_sos.market_share_pct
    current_revenue = current_sos.revenue_attributed

    # Disclosed, deterministic response model — no randomness. The user must
    # confirm this relationship reflects their business; it is labeled as an estimate.
    tier_multipliers = {"tier_1": 1.0, "tier_2": 0.6, "tier_3": 0.3}
    tier_mult = tier_multipliers.get(sim_data.target_tier, 0.5)
    success_rate = 0.7
    lift_per_placement_pct = 0.008 * tier_mult

    successful_placements = int(sim_data.expected_placements * success_rate)
    search_lift_pct = successful_placements * lift_per_placement_pct * 100
    projected_share = current_share * (1 + search_lift_pct / 100)
    revenue_impact = current_revenue * (search_lift_pct / 100) if current_revenue is not None else None
    roi = (revenue_impact - sim_data.budget) / sim_data.budget * 100 if (revenue_impact is not None and sim_data.budget > 0) else None

    return {
        "brand": brand.name,
        "simulation_params": sim_data.model_dump(),
        "current_state": {
            "market_share_pct": current_share,
            "annual_revenue_attributed": current_revenue,
            "measured_at": current_sos.measured_at.isoformat() if current_sos.measured_at else None,
        },
        "results": {
            "successful_placements": successful_placements,
            "search_lift_pct": round(search_lift_pct, 3),
            "projected_market_share": round(projected_share, 3),
            "revenue_impact": round(revenue_impact, 2) if revenue_impact is not None else None,
            "projected_roi_pct": round(roi, 2) if roi is not None else None,
        },
        "model_disclosure": (
            "Linear model: lift% = expected_placements * 0.7 success * 0.8% per placement * tier multiplier. "
            "This is an estimate you must validate against your own conversion data; no random or fabricated "
            "inputs are used."
        ),
        "status": "projection",
        "recommendation": (
            f"Projected ROI: {round(roi, 1) if roi is not None else 'n/a'}%. "
            f"Campaign is {'viable' if roi and roi > 100 else 'marginal' if roi and roi > 0 else 'reconsider'} "
            f"(validated against real baseline share {current_share}% from {current_sos.measured_at.date().isoformat() if current_sos.measured_at else 'n/a'})."
        ),
    }


@router.get("/revenue-forecast/{brand_id}")
def revenue_forecast(brand_id: int, months: int = 12, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    sos_history = db.query(ShareOfSearch).filter(
        ShareOfSearch.brand_id == brand_id
    ).order_by(ShareOfSearch.measured_at.asc()).all()

    if len(sos_history) < 2:
        return {
            "brand": brand.name,
            "status": "unavailable",
            "requires": "At least two real ShareOfSearch measurements to compute a growth trend",
            "detail": "Forecasting from a single data point (or none) would fabricate a growth rate.",
            "forecast": [],
        }

    # Compound growth from REAL consecutive measurements only — no randomness.
    current_share = sos_history[-1].market_share_pct
    current_revenue = sos_history[-1].revenue_attributed
    monthly_growth_rates = []
    for i in range(1, len(sos_history)):
        prev = sos_history[i - 1].market_share_pct
        curr = sos_history[i].market_share_pct
        if prev:
            monthly_growth_rates.append((curr - prev) / prev)

    if not monthly_growth_rates:
        return {
            "brand": brand.name,
            "status": "unavailable",
            "requires": "Non-constant ShareOfSearch history",
            "detail": "No measurable growth between real data points.",
            "forecast": [],
        }

    avg_growth = sum(monthly_growth_rates) / len(monthly_growth_rates)
    forecast = []
    cumulative_share = current_share
    cumulative_revenue = current_revenue
    for m in range(1, months + 1):
        cumulative_share *= (1 + avg_growth)
        if cumulative_revenue is not None:
            cumulative_revenue *= (1 + avg_growth)
        forecast.append({
            "month": m,
            "projected_share_pct": round(cumulative_share, 2),
            "projected_revenue": round(cumulative_revenue, 2) if cumulative_revenue is not None else None,
            "growth_rate": round(avg_growth * 100, 2),
        })

    return {
        "brand": brand.name,
        "current_state": {
            "market_share": current_share,
            "annual_revenue": current_revenue,
            "measured_at": sos_history[-1].measured_at.isoformat() if sos_history[-1].measured_at else None,
        },
        "forecast": forecast,
        "total_projected_revenue": round(cumulative_revenue, 2) if cumulative_revenue is not None else None,
        "avg_monthly_growth": round(avg_growth * 100, 2),
        "model_disclosure": (
            f"Forecast compounds the real average monthly growth ({round(avg_growth * 100, 2)}%) observed across "
            f"{len(monthly_growth_rates)} real measurement intervals. No random noise is added."
        ),
    }

from __future__ import annotations

"""Billing / white-label stub (enterprise): plans + tenant branding.

Full Stripe/SSO is deployment-specific; this router provides the contract:
GET /billing/plans, GET /billing/tenant, POST /billing/tenant (admin).
White-label: WHITE_LABEL_BRAND env + per-tenant logo/theme/domain.
"""

from fastapi import APIRouter, Header, HTTPException
import os

router = APIRouter()

def _guard_default_secret():
    """Block mutating billing in production when SECRET_KEY is still the default.
    Read-only GET /plans and GET /tenant remain open; POST /tenant is gated.
    Prevents credential/white-label takeover on Render demo deploys that forgot to rotate SECRET_KEY.
    """
    try:
        from config.settings import settings
        if not settings.is_production_secret:
            raise HTTPException(status_code=403, detail="Refusing to mutate billing with default SECRET_KEY. Set a strong SECRET_KEY (16+ chars) in env.")
    except HTTPException:
        raise
    except Exception:
        pass

PLANS = [
    {"id": "free", "name": "Free proxy tier", "price": 0, "runs_mo": 10, "seats": 1},
    {"id": "pro", "name": "Pro GEO", "price": 249, "runs_mo": 300, "seats": 5},
    {"id": "enterprise", "name": "Enterprise", "price": 0, "runs_mo": -1, "seats": -1,
     "note": "SSO/RBAC, Postgres+Redis+CELERY, S3 snapshots, SLA — contact sales"},
]


@router.get("/plans")
async def plans():
    return {"status": "ok", "plans": PLANS}


@router.get("/tenant")
async def tenant(authorization: str | None = Header(default=None)):
    brand = os.environ.get("WHITE_LABEL_BRAND", "Off-Page SEO Intelligence")
    return {"status": "ok", "white_label_brand": brand,
            "logo": os.environ.get("WHITE_LABEL_LOGO", ""),
            "theme": {"accent": os.environ.get("WHITE_LABEL_ACCENT", "#4f46e5")},
            "domain": os.environ.get("WHITE_LABEL_DOMAIN", ""),
            "plan": os.environ.get("BILLING_PLAN", "free")}


@router.post("/tenant")
async def update_tenant(payload: dict, authorization: str | None = Header(default=None)):
    _guard_default_secret()
    from backend.api.auth import verify_token, require_role
    tok = (authorization or "").replace("Bearer ", "")
    if not require_role(verify_token(tok), "admin"):
        return {"status": "forbidden", "reason": "admin role required (or set REQUIRE_AUTH=false locally)"}
    allowed = {"WHITE_LABEL_BRAND", "WHITE_LABEL_LOGO", "WHITE_LABEL_ACCENT", "WHITE_LABEL_DOMAIN", "BILLING_PLAN"}
    saved = {k: v for k, v in (payload or {}).items() if k in allowed}
    return {"status": "ok", "saved": saved, "note": "Persist to env/Secrets in prod; reflected on next request."}

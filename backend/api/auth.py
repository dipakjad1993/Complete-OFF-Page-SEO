from __future__ import annotations

"""JWT auth + audit log (uses existing python-jose dependency).

BYOK-friendly: no forced login for local single-user runs. When SECRET_KEY is
custom and REQUIRE_AUTH=true, write endpoints require Bearer JWT.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any

AUDIT_PATH = "data/audit_log.jsonl"


def audit(event: str, detail: dict | None = None) -> None:
    try:
        os.makedirs("data", exist_ok=True)
        with open(AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(__import__("json").dumps({
                "at": datetime.now(timezone.utc).isoformat(),
                "event": event, "detail": detail or {},
            }) + "\n")
    except Exception:
        pass


def create_token(subject: str, minutes: int = 60, role: str = "analyst", tenant: str = "default") -> str:
    from jose import jwt  # type: ignore
    from config.settings import settings
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return jwt.encode({"sub": subject, "role": role, "tenant": tenant, "exp": exp}, settings.SECRET_KEY, algorithm="HS256")


def verify_token(token: str) -> dict[str, Any] | None:
    try:
        from jose import jwt  # type: ignore
        from config.settings import settings
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except Exception:
        return None


def require_role(payload: dict[str, Any] | None, *allowed: str) -> bool:
    """RBAC: admin > manager > analyst > viewer. Returns True if payload role suffices."""
    order = {"viewer": 0, "analyst": 1, "manager": 2, "admin": 3}
    if not auth_required():
        return True  # local single-user mode
    if not payload:
        return False
    have = order.get(str(payload.get("role", "viewer")), 0)
    return any(have >= order.get(a, 99) for a in allowed)


def auth_required() -> bool:
    # Honor both settings.REQUIRE_AUTH (.env via pydantic) and raw env var.
    try:
        from config.settings import settings as _s
        if bool(getattr(_s, "REQUIRE_AUTH", False)):
            return True
    except Exception:
        pass
    return os.environ.get("REQUIRE_AUTH", "").lower() in ("1", "true", "yes")

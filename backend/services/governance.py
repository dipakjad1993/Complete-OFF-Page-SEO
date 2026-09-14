from __future__ import annotations

"""Governance: the risk slider 0-100 actually blocks tactics (not just stored).

 0 = Fortune-50 safe, 100 = venture aggressive.
 Rules:
  - risk < 40: block expired-domain, PBN, paid/sponsored suggestions hard.
  - risk < 60: flag commercial-anchor > 30% or single-domain concentration > 40%.
  - max_outreach_per_day, blocked_domains, blocked_topics, ftc/sec rules enforced
    in PR drafts (outreach filtered pre-send).
"""

from typing import Any


def risk_config_for(brand_cfg: dict | None) -> dict[str, Any]:
    cfg = (brand_cfg or {}).get("governance", {}) if isinstance(brand_cfg, dict) else {}
    try:
        risk = int(cfg.get("risk_score", cfg.get("risk", 30)))
    except Exception:
        risk = 30
    return {
        "risk_score": max(0, min(100, risk)),
        "max_outreach_per_day": int(cfg.get("max_outreach_per_day", 10) or 10),
        "blocked_domains": [d.lower() for d in (cfg.get("blocked_domains") or [])],
        "blocked_topics": [t.lower() for t in (cfg.get("blocked_topics") or [])],
        "allowed_tactics": cfg.get("allowed_tactics") or [],
        "ftc_rules": cfg.get("ftc_rules") or "disclose paid relationships; rel=sponsored/ugc required",
        "sec_rules": cfg.get("sec_rules") or "",
    }


def gate_tactics(tactics: list[str], risk_score: int) -> dict[str, Any]:
    blocked_hard = {"expired_domain", "pbn", "paid_links", "sponsored_without_disclosure"}
    allowed, blocked = [], []
    for t in tactics:
        tl = (t or "").lower()
        is_risky = any(k in tl for k in ("expired", "pbn", "paid link", "sponsor", "buy link"))
        if risk_score < 40 and is_risky:
            blocked.append({"tactic": t, "reason": f"risk {risk_score}<40 blocks high-risk tactic"})
        else:
            allowed.append(t)
    return {"allowed": allowed, "blocked": blocked, "risk_score": risk_score,
            "policy": "risk<40 blocks expired/PBN/paid; 40-59 warns; 60+ permits with disclosure"}


def anchor_warnings(commercial_ratio: float, top_domain_share: float) -> list[str]:
    warns = []
    if commercial_ratio > 0.30:
        warns.append(f"Commercial anchor {commercial_ratio:.0%} > 30% — dilute with branded/URL anchors (SpamBrain boundary).")
    if top_domain_share > 0.40:
        warns.append(f"Single-domain concentration {top_domain_share:.0%} > 40% — diversify sources.")
    return warns


def filter_outreach(drafts: list[dict], gov: dict) -> list[dict]:
    out = []
    blocked_d = set(gov.get("blocked_domains", []))
    blocked_t = set(gov.get("blocked_topics", []))
    for d in drafts:
        outlet = str(d.get("outlet", "")).lower()
        topic = str(d.get("topic", "") or d.get("hook", "")).lower()
        if outlet and any(b in outlet for b in blocked_d):
            d = {**d, "suppressed": True, "suppress_reason": "blocked domain"}
        elif any(b in topic for b in blocked_t):
            d = {**d, "suppressed": True, "suppress_reason": "blocked topic"}
        out.append(d)
    cap = int(gov.get("max_outreach_per_day", 10) or 10)
    sent = 0
    for d in out:
        if d.get("suppressed"):
            continue
        sent += 1
        if sent > cap:
            d["suppressed"] = True
            d["suppress_reason"] = f"max_outreach_per_day={cap} cap"
    return out

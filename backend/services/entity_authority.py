from __future__ import annotations

"""Entity Authority score — replaces DA-clone hero metric.

DA is a third-party estimate with ~zero correlation to AI citations.
Entity Authority 0-100 is computed from REAL measured sub-scores:

  entity_authority = 0.30*kg_coverage + 0.20*sameAs_corroboration
                   + 0.20*citation_rate(proxy SoV) + 0.15*aeo_readiness
                   + 0.15*vector_index/100  (+ FTC/compliance gate, -risk penalties)

All inputs are real module outputs. Missing inputs degrade honestly
(weight renormalizes) instead of fabricating.
"""

from typing import Any


def compute_entity_authority(parts: dict[str, Any]) -> dict[str, Any]:
    weights = {
        "kg_coverage": 0.30,
        "sameas": 0.20,
        "citation_rate": 0.20,
        "aeo": 0.15,
        "vector": 0.15,
    }
    vals: dict[str, float | None] = {
        "kg_coverage": parts.get("kg_coverage"),
        "sameas": parts.get("sameas"),
        "citation_rate": parts.get("citation_rate"),
        "aeo": parts.get("aeo"),
        "vector": parts.get("vector"),
    }
    used, total_w, acc = {}, 0.0, 0.0
    for k, w in weights.items():
        v = vals.get(k)
        if isinstance(v, (int, float)) and v is not None:
            v01 = max(0.0, min(1.0, float(v)))
            acc += v01 * w
            total_w += w
            used[k] = round(v01, 3)
    score = round((acc / total_w) * 100, 1) if total_w else 0.0
    if score >= 80:
        grade, verdict = "A", "Entity strongly established across KG, citations and agent surfaces."
    elif score >= 65:
        grade, verdict = "B", "Entity recognized with gaps — close KG/sameAs + citation deficits."
    elif score >= 50:
        grade, verdict = "C", "Entity partially established — priority KG + AEO + citation work."
    elif score >= 35:
        grade, verdict = "D", "Entity weak — foundational identity + corroboration required."
    else:
        grade, verdict = "F", "Entity largely invisible — full identity rebuild required."
    return {
        "entity_authority_0_100": score,
        "grade": grade,
        "verdict": verdict,
        "formula": "0.30*kg + 0.20*sameAs + 0.20*citation + 0.15*aeo + 0.15*vector (renormalized when inputs missing)",
        "inputs_used": used,
        "inputs_missing": [k for k in weights if k not in used],
        "note": "Replaces legacy DA-clone. Every input is a live measured signal.",
    }

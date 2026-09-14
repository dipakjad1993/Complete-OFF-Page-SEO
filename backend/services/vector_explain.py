from __future__ import annotations

"""Topical Vector Distance Index — explainable, not a black box.

score 0-100 where 100 = brand corpus is topically closest to the seed corpus.
Formula (documented for enterprise trust):
  1. Build TF-IDF vectors (or sentence-transformers when installed) over
     live search snippets for brand vs competitor set.
  2. cosine similarity brand<->seed centroid -> sim in [0,1].
  3. index = round(sim * 100).
Method + backend (tfidf|sbert) + competitor list + thresholds are always
returned alongside the number.
"""

import math
from collections import Counter
from typing import Any


def _tokens(s: str) -> list[str]:
    import re
    return [t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if len(t) > 2]


def tfidf_cosine(a: str, b: str) -> float:
    ta, tb = Counter(_tokens(a)), Counter(_tokens(b))
    vocab = set(ta) | set(tb)
    if not vocab:
        return 0.0
    dot = sum(ta[w] * tb[w] for w in vocab)
    na = math.sqrt(sum(v * v for v in ta.values())) or 1.0
    nb = math.sqrt(sum(v * v for v in tb.values())) or 1.0
    return dot / (na * nb)


def sbert_cosine(a: str, b: str) -> tuple[float | None, str]:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        import numpy as np  # type: ignore
        model = SentenceTransformer("all-MiniLM-L6-v2")
        ea, eb = model.encode([a[:2000], b[:2000]])
        denom = (float((ea ** 2).sum()) ** 0.5) * (float((eb ** 2).sum()) ** 0.5) or 1.0
        return float(float((ea * eb).sum()) / denom), "sbert(all-MiniLM-L6-v2)"
    except Exception:
        return None, "tfidf-fallback"


def vector_index(brand_corpus: str, seed_corpus: str,
                 competitors: list[str] | None = None) -> dict[str, Any]:
    sim_sbert, backend = sbert_cosine(brand_corpus, seed_corpus)
    sim = sim_sbert if sim_sbert is not None else tfidf_cosine(brand_corpus, seed_corpus)
    if backend == "tfidf-fallback":
        backend = "tfidf(cosine)"
    index = int(round(max(0.0, min(1.0, sim)) * 100))
    if index >= 70:
        band, action = "aligned", "Maintain topical focus; expand corroborating coverage."
    elif index >= 40:
        band, action = "drifting", "Close topical gaps vs seed corpus (add glossary/FAQ depth)."
    else:
        band, action = "distant", "Rebuild topical authority: seed-aligned hubs + expert bylines."
    return {
        "index_0_100": index,
        "cosine": round(sim, 4),
        "backend": backend,
        "formula": "index = round(cosine(brand_corpus, seed_centroid) * 100)",
        "competitors": competitors or [],
        "thresholds": {"aligned": ">=70", "drifting": "40-69", "distant": "<40"},
        "band": band,
        "action": action,
    }

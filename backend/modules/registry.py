from __future__ import annotations

"""Registry: canonical 35-module map + guarded runner.

ModuleResult-shaped dicts flow through run_module_guarded() with per-module
timeout (default 120s, overridable per module) + 1 retry + circuit breaker.
"""

from typing import Any
from .base import run_module_guarded

# num, key, domain, impl-attr, timeout
MODULES: list[tuple[int, str, str, str, int]] = [
    (1, "llm_perception", "llm", "feature_llm_perception", 90),
    (2, "pr_hooks", "pr", "feature_pr_hooks", 120),
    (3, "unlinked_citations", "kg", "feature_unlinked_citations", 120),
    (4, "link_poisoning", "risk", "feature_link_poisoning", 90),
    (5, "podcast_video", "pr", "feature_podcast_video", 120),
    (6, "vector_mapping", "llm", "feature_vector_mapping", 90),
    (7, "rag_repair", "llm", "feature_rag_repair", 90),
    (8, "consensus", "llm", "feature_consensus", 90),
    (9, "aeo", "technical", "feature_aeo", 60),
    (10, "pbn_detector", "risk", "feature_pbn_detector", 90),
    (11, "revenue_sim", "risk", "feature_revenue_sim", 60),
    (12, "dead_equity", "technical", "feature_dead_equity", 90),
    (13, "negative_seo", "risk", "feature_negative_seo", 90),
    (14, "github_citations", "kg", "feature_github_citations", 90),
    (15, "transcription", "pr", "feature_transcription", 90),
    (16, "kg_arbitrage", "kg", "feature_kg_arbitrage", 90),
    (17, "data_pr", "llm", "feature_data_pr", 60),
    (18, "simulation", "llm", "feature_simulation", 60),
    (19, "satellite", "pr", "feature_satellite", 90),
    (20, "rag_defense", "llm", "feature_rag_defense", 90),
    (21, "visual_audit", "kg", "feature_visual_audit", 60),
    (22, "apn_proxy", "technical", "feature_apn_proxy", 60),
    (23, "graph_decay", "kg", "feature_graph_decay", 60),
    (24, "c2pa", "kg", "feature_c2pa", 60),
    (25, "compliance_guard", "technical", "feature_compliance_guard", 60),
    (26, "geo_crawl", "technical", "feature_geo_crawl", 90),
    (27, "zero_party", "pr", "feature_zero_party", 60),
    (28, "passage_scoring", "llm", "feature_passage_scoring", 90),
    (29, "reddit_consensus", "kg", "feature_reddit_consensus", 120),
    (30, "competitor_bert", "llm", "feature_competitor_bert", 90),
    (31, "schema_auditor", "kg", "feature_schema_auditor", 60),
    (32, "anchor_entropy", "risk", "feature_anchor_entropy", 90),
    (33, "crawl_priority", "technical", "feature_crawl_priority", 60),
    (34, "ftc_compliance", "risk", "feature_ftc_compliance", 90),
    (35, "hreflang", "technical", "feature_hreflang", 60),
]

MODULE_TIMEOUTS = {key: t for _, key, _, _, t in MODULES}

_DOMAIN_MOD = {"llm": "backend.modules.llm", "pr": "backend.modules.pr",
               "kg": "backend.modules.kg", "technical": "backend.modules.technical",
               "risk": "backend.modules.risk"}


def _resolve(domain: str, attr: str):
    import importlib
    return getattr(importlib.import_module(_DOMAIN_MOD[domain]), attr)


def get_registry() -> list[dict[str, Any]]:
    out = []
    for num, key, domain, attr, timeout in MODULES:
        out.append({
            "num": num, "key": key, "domain": domain,
            "callable": _resolve(domain, attr),
            "timeout": timeout,
        })
    return out


async def run_one(key: str, *args: Any, **kwargs: Any) -> dict:
    for num, k, domain, attr, timeout in MODULES:
        if k == key:
            return await run_module_guarded(k, _resolve(domain, attr), *args,
                                            timeout_secs=timeout, retries=1, **kwargs)
    raise KeyError(f"unknown module {key}")

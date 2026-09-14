"""One-shot splitter: backend/api/analysis.py (4568 lines) -> backend/modules/*.

Code moves; analysis.py becomes thin orchestrator + compat re-exports.
Safe: exact source slices, no reformatting. Idempotent-ish (backs up first).
"""
import re, shutil, pathlib

SRC = pathlib.Path("backend/api/analysis.py")
MOD = pathlib.Path("backend/modules")
assert SRC.exists(), "run from repo root"

text = SRC.read_text(encoding="utf-8", errors="replace")
lines = text.splitlines(keepends=True)

# Map every top-level def/class line -> index
bounds = []  # (line_no_1idx, name)
for i, l in enumerate(lines, 1):
    m = re.match(r"^(async def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", l)
    if m:
        bounds.append((i, m.group(2)))
print(f"{len(bounds)} top-level defs")

def span(name):
    idx = next(i for i, (ln, n) in enumerate(bounds) if n == name)
    start = bounds[idx][0]
    end = bounds[idx + 1][0] if idx + 1 < len(bounds) else len(lines) + 1
    return start, end  # 1-idxed, end exclusive

def slice_of(name):
    s, e = span(name)
    return "".join(lines[s - 1:e - 1])

DOMAIN_MAP = {
    "llm": ["feature_llm_perception", "feature_vector_mapping", "feature_rag_repair",
            "feature_consensus", "feature_data_pr", "feature_simulation",
            "feature_rag_defense", "feature_passage_scoring", "feature_competitor_bert"],
    "pr": ["feature_pr_hooks", "feature_podcast_video", "feature_transcription",
           "feature_satellite", "feature_zero_party"],
    "kg": ["feature_unlinked_citations", "feature_github_citations", "feature_kg_arbitrage",
           "feature_visual_audit", "feature_graph_decay", "feature_c2pa",
           "feature_reddit_consensus", "feature_schema_auditor"],
    "technical": ["feature_aeo", "feature_dead_equity", "feature_compliance_guard",
                  "feature_geo_crawl", "feature_apn_proxy", "feature_crawl_priority",
                  "feature_hreflang"],
    "risk": ["feature_link_poisoning", "feature_pbn_detector", "feature_revenue_sim",
             "feature_negative_seo", "feature_anchor_entropy", "feature_ftc_compliance"],
}
COMMON_FNS = ["load_configs", "load_credentials", "_now_utc", "_progress", "_progress_path",
              "_update_progress", "_reset_progress", "extract_domain", "_is_brand_domain",
              "normalize_search_url", "_brand_tokens", "WRONG_ENTITY_LEXICON",
              "_entity_variants", "_entity_ok", "_entity_keep", "_source_keepable",
              "_source_title_cache", "_title_matches", "safe_fetch", "deep_fetch_website",
              "extract_comprehensive_data", "get_wikipedia", "get_wikidata",
              "_module_unavailable", "get_da"]

HEADER_IMPORTS = """from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
import httpx
import json
import os
import re
import math
import asyncio
from datetime import datetime, timezone
from collections import Counter
from urllib.parse import parse_qs, urlparse
from bs4 import BeautifulSoup

from backend.core.database import get_db
from backend.models.models import (
    Brand, BrandMention, Backlink, RAGCitation, VectorDistance,
    KnowledgeGraphTriple, ConsensusScore, Alert, Competitor, Executive,
    PassageAttention,
)
from backend.services.verification import (
    VerifiedData, UnavailableData, is_verified, is_unavailable, verified, unavailable,
)
from backend.services.providers import (
    ahrefs, moz, majestic, serpapi, openai, anthropic, perplexity, newsapi, google_kg,
)
from backend.services.search import search_web, verify_url, search_news
from backend.services import free_apis
from config.settings import settings
"""

# --- backup ---
shutil.copy(SRC, SRC.with_suffix(".py.bak"))
print("backup ->", SRC.with_suffix(".py.bak"))

# --- common.py: header + shared helpers (lines 1..793 region = everything before first feature) ---
first_feature_line, _ = span("feature_llm_perception")
common_src = HEADER_IMPORTS + "\nMODULE_TIMEOUT_SECS = 120\n\nHEADERS = {\n    \"User-Agent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36\",\n    \"Accept\": \"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8\",\n    \"Accept-Language\": \"en-US,en;q=0.9\",\n    \"Accept-Encoding\": \"gzip, deflate, br\",\n    \"Sec-Fetch-Dest\": \"document\",\n    \"Sec-Fetch-Mode\": \"navigate\",\n    \"Sec-Fetch-Site\": \"none\",\n    \"Upgrade-Insecure-Requests\": \"1\",\n}\n\nWIKI_HEADERS = {\n    \"User-Agent\": \"CompleteSEOScraper/2.0 (https://github.com/completeseo; contact@completeseo.com)\",\n    \"Accept\": \"application/json\",\n}\n\n"
# everything between end of header block and first feature = shared helpers region
# find end of WIKI_HEADERS in original = line with "^}" closing; simpler: slice lines from AnalysisRequest end to first feature
# Instead: collect slices for each COMMON_FNS entry + module-level constants region (lines 1-793 minus imports/header already covered).
# Pragmatic: take original lines[30:first_feature_line-1] (0-idxed) minus router/AnalysisRequest, keep constants+helpers verbatim.
region = "".join(lines[30:first_feature_line - 1])
# strip router + AnalysisRequest from region (they stay in analysis.py)
region = re.sub(r"router = APIRouter\(\)\n", "", region)
region = re.sub(r"class AnalysisRequest\(BaseModel\):\n(?:    .*\n)+", "", region)
common_src += region
(MOD / "common.py").write_text(common_src, encoding="utf-8")
print("common.py", len(common_src.splitlines()), "lines")

# --- domain modules ---
for domain, fns in DOMAIN_MAP.items():
    body = f'"""Domain module: {domain} — split from backend/api/analysis.py monolith.\n\nReal-data-only: every feature returns live-collected signals or honest\nunavailable states. See backend/modules/common.py for shared helpers.\n"""\nfrom .common import *  # noqa: F401,F403\n'
    for fn in fns:
        body += "\n\n" + slice_of(fn)
    (MOD / f"{domain}.py").write_text(body, encoding="utf-8")
    print(domain + ".py", len(body.splitlines()), "lines,", len(fns), "features")

# --- rewrite analysis.py: thin orchestrator ---
# keep everything from run_full_analysis to EOF verbatim (orchestrator + endpoints + PDF)
s_run, _ = span("run_full_analysis")
tail = "".join(lines[s_run - 1:])
new_head = '''"""Analysis engine — thin orchestrator (monolith split v2026.3).

Feature implementations live in backend/modules/{llm,pr,kg,technical,risk}.py
(shared helpers in backend/modules/common.py). This module keeps the runner,
progress tracking, deliverables/PDF assembly and HTTP endpoints, and re-exports
feature_* callables for backward compatibility (registry + tests import here).
"""
from backend.modules.common import *  # noqa: F401,F403
from backend.modules.llm import (  # noqa: F401
    feature_llm_perception, feature_vector_mapping, feature_rag_repair,
    feature_consensus, feature_data_pr, feature_simulation,
    feature_rag_defense, feature_passage_scoring, feature_competitor_bert,
)
from backend.modules.pr import (  # noqa: F401
    feature_pr_hooks, feature_podcast_video, feature_transcription,
    feature_satellite, feature_zero_party,
)
from backend.modules.kg import (  # noqa: F401
    feature_unlinked_citations, feature_github_citations, feature_kg_arbitrage,
    feature_visual_audit, feature_graph_decay, feature_c2pa,
    feature_reddit_consensus, feature_schema_auditor,
)
from backend.modules.technical import (  # noqa: F401
    feature_aeo, feature_dead_equity, feature_compliance_guard,
    feature_geo_crawl, feature_apn_proxy, feature_crawl_priority,
    feature_hreflang,
)
from backend.modules.risk import (  # noqa: F401
    feature_link_poisoning, feature_pbn_detector, feature_revenue_sim,
    feature_negative_seo, feature_anchor_entropy, feature_ftc_compliance,
)
from backend.modules.registry import MODULE_TIMEOUTS  # noqa: F401
from backend.modules.base import run_module_guarded  # noqa: F401

router = APIRouter()


class AnalysisRequest(BaseModel):
    brand_id: int
    analysis_type: str = "full"


'''
SRC.write_text(new_head + tail, encoding="utf-8")
print("analysis.py rewritten:", len((new_head + tail).splitlines()), "lines")

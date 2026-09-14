"""Backend modules package — domain-split view over the 35-module engine.

backend/api/analysis.py remains the canonical async implementation (no behaviour
change). This package provides:
  base.py      — ModuleResult dataclass + registry + timeout/retry/circuit-breaker
  llm.py       — LLM / RAG / simulation domain
  pr.py        — Digital PR domain
  kg.py        — Knowledge-graph / entity domain
  social.py    — UGC / Reddit / podcast / video domain
  technical.py — AEO / crawl / schema / redirect / hreflang domain
  risk.py      — toxicity / PBN / negative-SEO / FTC / compliance domain
  registry.py  — name -> (domain, feature_* callable) mapping + runner
  extended.py  — NEW 2026 modules 36-42 (bot governance, prompt tracking,
                 KG ops, UGC depth, image backlinks, author graph, PR 2.0)

Real-data-only: every module returns ModuleResult with status ok|unavailable|error,
never fabricated numbers.
"""

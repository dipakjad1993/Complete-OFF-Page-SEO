from __future__ import annotations
"""Social / UGC domain facade (DEPRECATED — kept for backward-compat imports).

Canonical implementations live in backend/modules/{llm,kg,pr}.py.
This shim re-exports them so legacy `import social` never crashes.
"""
try:
    from .llm import feature_consensus as feature_consensus
except Exception:  # pragma: no cover
    async def feature_consensus(*a, **k):  # type: ignore
        return {"status": "unavailable", "assessment": "consensus module not loaded", "metrics": {}, "sources": [], "recommendations": [], "methodology": "social shim fallback"}
try:
    from .kg import feature_reddit_consensus as feature_reddit_consensus
    from .kg import feature_github_citations as feature_github_citations
except Exception:  # pragma: no cover
    pass
try:
    from .pr import feature_podcast_video as feature_podcast_video
    from .pr import feature_transcription as feature_transcription
except Exception:  # pragma: no cover
    pass

__all__ = [n for n in ("feature_reddit_consensus", "feature_github_citations", "feature_podcast_video", "feature_transcription", "feature_consensus") if n in globals()]

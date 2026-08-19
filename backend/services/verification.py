from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class VerifiedData:
    """A single data point carrying full provenance so nothing can be fabricated.

    Every value produced by the engine must be wrapped in this object (or an
    explicit UnavailableData) so callers can always see where it came from,
    how it was obtained, when, and how confident we are in it.
    """
    value: Any
    source: str                    # provider/integration e.g. "ahrefs_api", "live_crawl", "wikidata_api"
    method: str                    # how obtained e.g. "ahrefs_v3_api", "duckduckgo_scrape", "openai_gpt4o"
    retrieved_at: str              # ISO timestamp of retrieval
    confidence: float = 1.0        # 0-1
    verified: bool = True          # True when it was checked against the source itself
    source_url: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(1.0, self.confidence))


@dataclass
class UnavailableData:
    """Honest representation of data that could not be obtained.

    Used instead of fabricating numbers. Always includes the reason and what
    is required to unblock it.
    """
    reason: str
    requires: str                 # e.g. "AHREFS_API_KEY"
    retrieved_at: str = field(default_factory=utcnow_iso)
    status: str = "unavailable"

    def to_dict(self) -> dict:
        return asdict(self)


def verified(
    value: Any,
    source: str,
    method: str,
    confidence: float = 1.0,
    verified: bool = True,
    source_url: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> VerifiedData:
    return VerifiedData(
        value=value,
        source=source,
        method=method,
        retrieved_at=utcnow_iso(),
        confidence=confidence,
        verified=verified,
        source_url=source_url,
        metadata=metadata or {},
    )


def unavailable(reason: str, requires: str) -> UnavailableData:
    return UnavailableData(reason=reason, requires=requires)


def is_verified(value: Any) -> bool:
    return isinstance(value, VerifiedData)


def is_unavailable(value: Any) -> bool:
    return isinstance(value, UnavailableData)

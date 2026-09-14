from __future__ import annotations

"""ModuleResult + registry + resilience primitives for the 35-module engine.

Every module returns a ModuleResult — never raises into the runner, never
fabricates. Per-module timeout + exponential-backoff retry + circuit breaker
make /progress/{brand_id} stable under provider outages.
"""

import asyncio
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Awaitable, Callable, Optional


@dataclass
class ModuleResult:
    key: str
    num: int
    name: str
    status: str  # ok | unavailable | error | low_signal
    assessment: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    sources: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    methodology: str = ""
    runtime_ms: int = 0
    confidence: float = 1.0
    provider: str = "free-tier"
    verified: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


# ---- circuit breaker (in-memory, per module key) ----
_breakers: dict[str, dict] = {}
_BREAKER_THRESHOLD = 3
_BREAKER_COOLDOWN_SECS = 300.0


def breaker_allows(key: str) -> bool:
    b = _breakers.get(key)
    if not b:
        return True
    if b["consecutive_failures"] < _BREAKER_THRESHOLD:
        return True
    return (time.time() - b["last_failure"]) > _BREAKER_COOLDOWN_SECS


def breaker_record(key: str, ok: bool) -> None:
    b = _breakers.setdefault(key, {"consecutive_failures": 0, "last_failure": 0.0})
    if ok:
        b["consecutive_failures"] = 0
    else:
        b["consecutive_failures"] += 1
        b["last_failure"] = time.time()


async def run_module_guarded(
    key: str,
    fn: Callable[..., Awaitable[dict]],
    *args: Any,
    timeout_secs: float = 120.0,
    retries: int = 1,
    **kwargs: Any,
) -> dict:
    """Run a feature_* callable with timeout + retry + circuit breaker.

    Returns the module's plain dict (with status/methodology/...). On total
    failure returns an honest error dict — never fabricated data.
    """
    started = time.time()
    if not breaker_allows(key):
        return {
            "status": "unavailable",
            "assessment": f"Circuit open for {key}: repeated provider failures. Cooldown active.",
            "metrics": {},
            "sources": [],
            "recommendations": ["Retry after cooldown; check provider keys in /api/v1/provider-status."],
            "methodology": "registry circuit-breaker (3 consecutive failures, 5-min cooldown). No live call attempted.",
            "runtime_ms": 0,
            "confidence": 1.0,
            "provider": "none",
        }
    last_err: Optional[str] = None
    for attempt in range(retries + 1):
        try:
            out = await asyncio.wait_for(fn(*args, **kwargs), timeout=timeout_secs)
            breaker_record(key, True)
            if isinstance(out, dict):
                out.setdefault("runtime_ms", int((time.time() - started) * 1000))
                return out
            return {
                "status": "error",
                "assessment": f"{key} returned non-dict payload.",
                "metrics": {},
                "sources": [],
                "recommendations": [],
                "methodology": "registry guard: unexpected return type.",
                "runtime_ms": int((time.time() - started) * 1000),
                "confidence": 1.0,
            }
        except asyncio.TimeoutError:
            last_err = f"timeout after {timeout_secs}s (attempt {attempt + 1})"
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {str(e)[:240]}"
        if attempt < retries:
            await asyncio.sleep(2 ** attempt)
    breaker_record(key, False)
    return {
        "status": "error",
        "assessment": f"{key} failed: {last_err}",
        "metrics": {},
        "sources": [],
        "recommendations": ["Re-run; if persistent, inspect server logs and provider status."],
        "methodology": "registry guard: timeout+retry exhausted. No data fabricated.",
        "runtime_ms": int((time.time() - started) * 1000),
        "confidence": 1.0,
        "provider": "none",
    }

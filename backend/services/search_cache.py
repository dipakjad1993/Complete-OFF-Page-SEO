from __future__ import annotations

"""SQLite disk cache for search results (7-day TTL).

Reduces provider burn + stabilizes re-runs. Table search_cache(query_hash,
query, payload_json, provider, created_at). Real cached payloads only — an
honest miss returns None so callers fall through to live providers.
"""

import hashlib
import json
import os
import sqlite3
import time

DB_PATH = os.environ.get("SEARCH_CACHE_DB", "search_cache.db")
TTL_SECS = 7 * 24 * 3600


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.execute(
        "CREATE TABLE IF NOT EXISTS search_cache "
        "(query_hash TEXT PRIMARY KEY, query TEXT, payload_json TEXT, "
        " provider TEXT, created_at REAL)"
    )
    c.commit()
    return c


def _hash(query: str, num: int, brand: str) -> str:
    return hashlib.sha256(f"{query}|{num}|{brand}".lower().encode()).hexdigest()


def cache_get(query: str, num: int = 10, brand: str = "") -> dict | None:
    try:
        h = _hash(query, num, brand)
        c = _conn()
        row = c.execute(
            "SELECT payload_json, provider, created_at FROM search_cache WHERE query_hash=?",
            (h,),
        ).fetchone()
        c.close()
        if not row:
            return None
        payload_json, provider, created_at = row
        if (time.time() - float(created_at)) > TTL_SECS:
            return None
        return {"payload": json.loads(payload_json), "provider": provider}
    except Exception:
        return None


def cache_put(query: str, num: int, brand: str, payload: list, provider: str) -> None:
    try:
        h = _hash(query, num, brand)
        c = _conn()
        c.execute(
            "INSERT OR REPLACE INTO search_cache(query_hash, query, payload_json, provider, created_at)"
            " VALUES(?,?,?,?,?)",
            (h, query[:400], json.dumps(payload)[:60000], provider, time.time()),
        )
        c.commit()
        c.close()
    except Exception:
        pass

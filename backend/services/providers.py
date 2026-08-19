from __future__ import annotations

"""Provider registry.

Central access point for all external data integrations. Each provider:

1. Checks whether the required credential is configured (from settings).
2. Makes REAL API calls when configured.
3. Returns VerifiedData with provenance, or UnavailableData with the exact
   reason and the required env var when not configured.

No provider in this module fabricates or synthesizes values.
"""

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote_plus

import httpx

from config.settings import settings
from backend.services.verification import VerifiedData, UnavailableData, utcnow_iso

REQUEST_TIMEOUT = 30.0
API_HEADERS = {"User-Agent": "OffPageSEO-Engine/2026.1 (+verified-data)"}


def utcnow() -> str:
    return utcnow_iso()


def _unavailable(provider: str, env_var: str, note: str = "") -> UnavailableData:
    reason = f"{provider} requires {env_var} to be set in .env."
    if note:
        reason += " " + note
    return UnavailableData(reason=reason, requires=env_var)


class AhrefsProvider:
    BASE = "https://apiv2.ahrefs.com"

    @property
    def key(self) -> Optional[str]:
        return settings.AHREFS_API_KEY

    @property
    def available(self) -> bool:
        return bool(self.key)

    async def _get(self, params: dict) -> dict:
        params.update({"output": "json", "token": self.key})
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=API_HEADERS) as c:
            r = await c.get(self.BASE, params=params)
            r.raise_for_status()
            return r.json()

    async def backlinks(self, target: str, limit: int = 100) -> Any:
        if not self.available:
            return _unavailable("Ahrefs", "AHREFS_API_KEY")
        try:
            data = await self._get({
                "from": "ahrefs_backlinks", "target": target,
                "mode": "domain", "limit": limit, "order_by": "domain_rating:desc",
            })
            links = data.get("backlinks", [])
            return VerifiedData(
                value=[{
                    "source_url": b.get("url_from"),
                    "source_domain": (b.get("url_from") or "").split("/")[0].replace("www.", ""),
                    "target_url": b.get("url_to"),
                    "anchor_text": b.get("anchor"),
                    "is_dofollow": b.get("link_type") == "dofollow",
                    "is_sponsored": b.get("link_type") == "sponsored",
                    "is_ugc": b.get("link_type") == "ugc",
                    "domain_rating": b.get("domain_rating"),
                    "first_seen": b.get("first_seen"),
                } for b in links],
                source="ahrefs_api", method="ahrefs_v3_backlinks",
                retrieved_at=utcnow(), confidence=1.0, verified=True,
                metadata={"total_reported": len(links)},
            )
        except Exception as e:  # noqa: BLE001
            return _unavailable("Ahrefs", "AHREFS_API_KEY", f"Request failed: {e}")

    async def domain_rating(self, target: str) -> Any:
        if not self.available:
            return _unavailable("Ahrefs", "AHREFS_API_KEY")
        try:
            data = await self._get({
                "from": "metrics", "target": target, "mode": "domain",
            })
            m = data.get("metrics", {})
            dr = m.get("domain_rating")
            return VerifiedData(
                value=dr, source="ahrefs_api", method="ahrefs_v3_domain_rating",
                retrieved_at=utcnow(), confidence=1.0, verified=True, metadata=m,
            )
        except Exception as e:  # noqa: BLE001
            return _unavailable("Ahrefs", "AHREFS_API_KEY", f"Request failed: {e}")


class MozProvider:
    """Moz Link Explorer API v2 (JSON, Basic auth with access_id:secret)."""

    BASE = "https://lsapi.seomoz.com/v2/url_metrics"

    @property
    def available(self) -> bool:
        return bool(settings.MOZ_ACCESS_KEY and settings.MOZ_SECRET_KEY)

    @property
    def _auth(self) -> str:
        cred = f"{settings.MOZ_ACCESS_KEY}:{settings.MOZ_SECRET_KEY}"
        return "Basic " + base64.b64encode(cred.encode()).decode()

    async def url_metrics(self, targets: list[str]) -> Any:
        if not self.available:
            return _unavailable("Moz", "MOZ_ACCESS_KEY / MOZ_SECRET_KEY")
        try:
            cols = ["domain_authority", "page_authority", "spam_score",
                    "root_domains", "linking_domains", "pages"]
            body = {"targets": targets[:100], "cols": cols}
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=API_HEADERS) as c:
                r = await c.post(self.BASE, json=body, headers={"Authorization": self._auth})
                r.raise_for_status()
                data = r.json()
            results = data.get("results", [])
            return VerifiedData(
                value=[{
                    "target": x.get("page"),
                    "domain_authority": x.get("domain_authority"),
                    "page_authority": x.get("page_authority"),
                    "spam_score": x.get("spam_score"),
                    "root_domains": x.get("root_domains"),
                    "linking_domains": x.get("linking_domains"),
                } for x in results],
                source="moz_api", method="moz_lsapi_v2",
                retrieved_at=utcnow(), confidence=1.0, verified=True,
                metadata={"columns": cols},
            )
        except Exception as e:  # noqa: BLE001
            return _unavailable("Moz", "MOZ_ACCESS_KEY / MOZ_SECRET_KEY", f"Request failed: {e}")


class MajesticProvider:
    BASE = "https://api.majestic.com/api/json"

    @property
    def available(self) -> bool:
        return bool(settings.MAJESTIC_API_KEY)

    async def _call(self, method: str, items: list[str], datasource: str) -> Any:
        params = {
            "app_api_key": settings.MAJESTIC_API_KEY,
            "cmd": method,
            "items": items[0],
            "item0": items[0] if len(items) == 1 else "",
            "datasource": datasource,
        }
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=API_HEADERS) as c:
            r = await c.get(self.BASE, params=params)
            r.raise_for_status()
            return r.json()

    async def get_index_item_info(self, targets: list[str]) -> Any:
        if not self.available:
            return _unavailable("Majestic", "MAJESTIC_API_KEY")
        try:
            if len(targets) != 1:
                return UnavailableData(
                    reason="Majestic GetIndexItemInfo supports exactly one item per call in this implementation.",
                    requires="MAJESTIC_API_KEY",
                )
            data = await self._call("GetIndexItemInfo", targets, "fresh")
            tables = data.get("DataTables", {}).get("Results", {}).get("Data", [])
            row = tables[0] if tables else {}
            return VerifiedData(
                value={
                    "domain": row.get("Item"),
                    "trust_flow": row.get("TrustFlow"),
                    "citation_flow": row.get("CitationFlow"),
                    "topical_trust_flow": row.get("TopicalTrustFlowTopic_0"),
                    "ref_domains": row.get("RefDomains"),
                    "backlinks": row.get("BackLinks"),
                },
                source="majestic_api", method="majestic_getindexiteminfo_fresh",
                retrieved_at=utcnow(), confidence=1.0, verified=True, metadata={"raw": row},
            )
        except Exception as e:  # noqa: BLE001
            return _unavailable("Majestic", "MAJESTIC_API_KEY", f"Request failed: {e}")


class SerpAPIProvider:
    BASE = "https://serpapi.com/search.json"

    @property
    def available(self) -> bool:
        return bool(settings.SERPAPI_KEY)

    async def search(self, query: str, num: int = 10, engine: str = "google") -> Any:
        if not self.available:
            return _unavailable("SerpAPI", "SERPAPI_KEY")
        try:
            params = {
                "engine": engine, "q": query, "num": num,
                "api_key": settings.SERPAPI_KEY,
                "gl": "us", "hl": "en",
            }
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=API_HEADERS) as c:
                r = await c.get(self.BASE, params=params)
                r.raise_for_status()
                data = r.json()
            organic = data.get("organic_results", []) or []
            return VerifiedData(
                value=[{
                    "position": o.get("position"),
                    "title": o.get("title"),
                    "url": o.get("link"),
                    "domain": (o.get("link") or "").split("/")[0].replace("www.", ""),
                    "snippet": (o.get("snippet") or "")[:400],
                } for o in organic],
                source="serpapi", method=f"serpapi_{engine}",
                retrieved_at=utcnow(), confidence=1.0, verified=True,
                metadata={"query": query, "total_results": data.get("search_information", {}).get("total_results")},
            )
        except Exception as e:  # noqa: BLE001
            return _unavailable("SerpAPI", "SERPAPI_KEY", f"Request failed: {e}")


class OpenAIClient:
    BASE = "https://api.openai.com/v1"

    @property
    def available(self) -> bool:
        return bool(settings.OPENAI_API_KEY)

    async def chat(self, messages: list[dict], model: str = "gpt-4o-mini", max_tokens: int = 1024) -> Any:
        if not self.available:
            return _unavailable("OpenAI", "OPENAI_API_KEY")
        try:
            body = {"model": model, "messages": messages, "max_tokens": max_tokens}
            async with httpx.AsyncClient(timeout=60, headers=API_HEADERS) as c:
                r = await c.post(f"{self.BASE}/chat/completions",
                                 json=body, headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"})
                r.raise_for_status()
                data = r.json()
            content = data["choices"][0]["message"]["content"]
            return VerifiedData(
                value=content, source="openai", method=f"openai_{model}",
                retrieved_at=utcnow(), confidence=1.0, verified=False,
                metadata={"model": model, "usage": data.get("usage")},
            )
        except Exception as e:  # noqa: BLE001
            return _unavailable("OpenAI", "OPENAI_API_KEY", f"Request failed: {e}")

    async def embeddings(self, texts: list[str], model: str = "text-embedding-3-small") -> Any:
        """Real embedding vectors for the supplied texts (used by vector modules)."""
        if not self.available:
            return _unavailable("OpenAI", "OPENAI_API_KEY")
        if not texts:
            return _unavailable("OpenAI", "OPENAI_API_KEY", "No text supplied to embed.")
        try:
            body = {"model": model, "input": texts}
            async with httpx.AsyncClient(timeout=60, headers=API_HEADERS) as c:
                r = await c.post(f"{self.BASE}/embeddings", json=body,
                                 headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"})
                r.raise_for_status()
                data = r.json()
            vectors = [d["embedding"] for d in data.get("data", [])]
            return VerifiedData(
                value=vectors, source="openai", method=f"openai_{model}",
                retrieved_at=utcnow(), confidence=1.0, verified=True,
                metadata={"model": model, "count": len(vectors)},
            )
        except Exception as e:  # noqa: BLE001
            return _unavailable("OpenAI", "OPENAI_API_KEY", f"Request failed: {e}")


class AnthropicClient:
    BASE = "https://api.anthropic.com/v1/messages"

    @property
    def available(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY)

    async def chat(self, messages: list[dict], model: str = "claude-3-5-sonnet-latest", max_tokens: int = 1024) -> Any:
        if not self.available:
            return _unavailable("Anthropic", "ANTHROPIC_API_KEY")
        try:
            system = [m["content"] for m in messages if m.get("role") == "system"]
            user = [m["content"] for m in messages if m.get("role") != "system"]
            body = {"model": model, "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": "\n".join(user)}]}
            if system:
                body["system"] = system[-1]
            async with httpx.AsyncClient(timeout=60, headers=API_HEADERS) as c:
                r = await c.post(self.BASE, json=body,
                                 headers={"x-api-key": settings.ANTHROPIC_API_KEY,
                                          "anthropic-version": "2023-06-01"})
                r.raise_for_status()
                data = r.json()
            content = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            return VerifiedData(
                value=content, source="anthropic", method=f"anthropic_{model}",
                retrieved_at=utcnow(), confidence=1.0, verified=False,
                metadata={"model": model, "usage": data.get("usage")},
            )
        except Exception as e:  # noqa: BLE001
            return _unavailable("Anthropic", "ANTHROPIC_API_KEY", f"Request failed: {e}")


class PerplexityClient:
    BASE = "https://api.perplexity.ai/chat/completions"

    @property
    def available(self) -> bool:
        return bool(settings.PERPLEXITY_API_KEY)

    async def chat(self, messages: list[dict], model: str = "sonar", max_tokens: int = 2048) -> Any:
        """Perplexity returns citations alongside answers — great for RAG monitoring."""
        if not self.available:
            return _unavailable("Perplexity", "PERPLEXITY_API_KEY")
        try:
            body = {"model": model, "messages": messages, "max_tokens": max_tokens}
            async with httpx.AsyncClient(timeout=60, headers=API_HEADERS) as c:
                r = await c.post(self.BASE, json=body,
                                 headers={"Authorization": f"Bearer {settings.PERPLEXITY_API_KEY}"})
                r.raise_for_status()
                data = r.json()
            content = data["choices"][0]["message"]["content"]
            citations = data.get("citations", [])
            return VerifiedData(
                value={"answer": content, "citations": citations},
                source="perplexity", method=f"perplexity_{model}",
                retrieved_at=utcnow(), confidence=1.0, verified=False,
                metadata={"model": model, "usage": data.get("usage")},
            )
        except Exception as e:  # noqa: BLE001
            return _unavailable("Perplexity", "PERPLEXITY_API_KEY", f"Request failed: {e}")


class NewsAPIProvider:
    BASE = "https://newsapi.org/v2"

    @property
    def available(self) -> bool:
        return bool(settings.NEWS_API_KEY)

    async def everything(self, query: str, from_days_ago: int = 14, page_size: int = 20) -> Any:
        if not self.available:
            return _unavailable("NewsAPI", "NEWS_API_KEY")
        try:
            params = {
                "q": query, "pageSize": page_size, "sortBy": "relevancy",
                "apiKey": settings.NEWS_API_KEY, "language": "en",
            }
            if from_days_ago:
                d = datetime.now(timezone.utc).fromordinal(datetime.now(timezone.utc).toordinal() - from_days_ago)
                params["from"] = d.strftime("%Y-%m-%d")
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=API_HEADERS) as c:
                r = await c.get(f"{self.BASE}/everything", params=params)
                r.raise_for_status()
                data = r.json()
            articles = data.get("articles", []) or []
            return VerifiedData(
                value=[{
                    "title": a.get("title"),
                    "url": a.get("url"),
                    "domain": (a.get("url") or "").split("/")[0].replace("www.", ""),
                    "description": a.get("description"),
                    "published_at": a.get("publishedAt"),
                    "source_name": a.get("source", {}).get("name"),
                } for a in articles],
                source="newsapi", method="newsapi_v2_everything",
                retrieved_at=utcnow(), confidence=1.0, verified=True,
                metadata={"query": query, "total_results": data.get("totalResults")},
            )
        except Exception as e:  # noqa: BLE001
            return _unavailable("NewsAPI", "NEWS_API_KEY", f"Request failed: {e}")


class GoogleKGProvider:
    BASE = "https://kgsearch.googleapis.com/v1/entities:search"

    @property
    def available(self) -> bool:
        return bool(settings.GOOGLE_API_KEY)

    async def search(self, query: str, types: list[str] | None = None, limit: int = 3) -> Any:
        if not self.available:
            return _unavailable("Google Knowledge Graph", "GOOGLE_API_KEY")
        try:
            params = {
                "query": query, "limit": limit,
                "key": settings.GOOGLE_API_KEY,
                "languages": "en",
            }
            if types:
                params["types"] = ",".join(types)
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=API_HEADERS) as c:
                r = await c.get(self.BASE, params=params)
                r.raise_for_status()
                data = r.json()
            items = data.get("itemListElement", []) or []
            return VerifiedData(
                value=[{
                    "mid": i.get("result", {}).get("@id"),
                    "name": i.get("result", {}).get("name"),
                    "description": i.get("result", {}).get("description"),
                    "url": (i.get("result", {}).get("url") or "")[:1] if i.get("result", {}).get("url") else None,
                    "score": i.get("resultScore"),
                } for i in items],
                source="google_kg", method="google_knowledge_graph",
                retrieved_at=utcnow(), confidence=1.0, verified=True,
                metadata={"query": query},
            )
        except Exception as e:  # noqa: BLE001
            return _unavailable("Google Knowledge Graph", "GOOGLE_API_KEY", f"Request failed: {e}")


class WikipediaClient:
    """Real Wikipedia + Wikidata API client for verified entity data."""

    WIKIPEDIA = settings.WIKIPEDIA_API_URL
    WIKIDATA = settings.WIKIDATA_API_URL

    async def page_summary(self, title: str) -> Any:
        try:
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote_plus(title)}"
            async with httpx.AsyncClient(timeout=15, headers=API_HEADERS) as c:
                r = await c.get(url)
                if r.status_code != 200:
                    return _unavailable("Wikipedia", "WIKIPEDIA_API_URL", "Page summary not found.")
                d = r.json()
            if d.get("type") == "disambiguation":
                return _unavailable("Wikipedia", "WIKIPEDIA_API_URL", "Result is a disambiguation page.")
            return VerifiedData(
                value={
                    "title": d.get("title"), "description": d.get("description"),
                    "extract": d.get("extract", "")[:2000],
                    "url": d.get("content_urls", {}).get("desktop", {}).get("page"),
                    "thumbnail": (d.get("thumbnail", {}) or {}).get("source"),
                },
                source="wikipedia", method="wikipedia_rest_v1_summary",
                retrieved_at=utcnow(), confidence=1.0, verified=True,
            )
        except Exception as e:  # noqa: BLE001
            return _unavailable("Wikipedia", "WIKIPEDIA_API_URL", f"Request failed: {e}")

    async def search_titles(self, query: str, limit: int = 5) -> Any:
        try:
            params = {"action": "query", "list": "search", "srsearch": query,
                      "format": "json", "srlimit": limit}
            async with httpx.AsyncClient(timeout=15, headers=API_HEADERS) as c:
                r = await c.get(self.WIKIPEDIA, params=params)
                r.raise_for_status()
                d = r.json()
            results = d.get("query", {}).get("search", []) or []
            return VerifiedData(
                value=[{"title": s.get("title"), "snippet": s.get("snippet", "")} for s in results],
                source="wikipedia", method="wikipedia_api_search",
                retrieved_at=utcnow(), confidence=1.0, verified=True,
                metadata={"query": query},
            )
        except Exception as e:  # noqa: BLE001
            return _unavailable("Wikipedia", "WIKIPEDIA_API_URL", f"Request failed: {e}")

    async def wikidata_entity(self, wikidata_id: str) -> Any:
        try:
            params = {"action": "wbgetentities", "ids": wikidata_id,
                      "format": "json", "props": "claims|labels|descriptions|sitelinks"}
            async with httpx.AsyncClient(timeout=15, headers=API_HEADERS) as c:
                r = await c.get(self.WIKIDATA, params=params)
                r.raise_for_status()
                d = r.json()
            entity = d.get("entities", {}).get(wikidata_id, {})
            return VerifiedData(
                value={
                    "id": wikidata_id,
                    "label": entity.get("labels", {}).get("en", {}).get("value"),
                    "description": entity.get("descriptions", {}).get("en", {}).get("value"),
                    "claims": entity.get("claims", {}),
                },
                source="wikidata", method="wikidata_wbgetentities",
                retrieved_at=utcnow(), confidence=1.0, verified=True,
            )
        except Exception as e:  # noqa: BLE001
            return _unavailable("Wikidata", "WIKIDATA_API_URL", f"Request failed: {e}")

    async def wikidata_search(self, query: str, limit: int = 5) -> Any:
        try:
            params = {"action": "wbsearchentities", "search": query, "language": "en",
                      "format": "json", "limit": limit}
            async with httpx.AsyncClient(timeout=15, headers=API_HEADERS) as c:
                r = await c.get(self.WIKIDATA, params=params)
                r.raise_for_status()
                d = r.json()
            results = d.get("search", []) or []
            return VerifiedData(
                value=[{"id": s.get("id"), "label": s.get("label"),
                        "description": s.get("description")} for s in results],
                source="wikidata", method="wikidata_wbsearchentities",
                retrieved_at=utcnow(), confidence=1.0, verified=True,
                metadata={"query": query},
            )
        except Exception as e:  # noqa: BLE001
            return _unavailable("Wikidata", "WIKIDATA_API_URL", f"Request failed: {e}")


# ---- Registry ----------------------------------------------------------------

def provider_status() -> dict[str, dict]:
    """Report which providers are configured vs missing (no secrets leaked)."""
    status = {
        "ahrefs": {"available": AhrefsProvider().available, "requires": "AHREFS_API_KEY"},
        "moz": {"available": MozProvider().available, "requires": "MOZ_ACCESS_KEY, MOZ_SECRET_KEY"},
        "majestic": {"available": MajesticProvider().available, "requires": "MAJESTIC_API_KEY"},
        "serpapi": {"available": SerpAPIProvider().available, "requires": "SERPAPI_KEY"},
        "openai": {"available": OpenAIClient().available, "requires": "OPENAI_API_KEY"},
        "anthropic": {"available": AnthropicClient().available, "requires": "ANTHROPIC_API_KEY"},
        "perplexity": {"available": PerplexityClient().available, "requires": "PERPLEXITY_API_KEY"},
        "newsapi": {"available": NewsAPIProvider().available, "requires": "NEWS_API_KEY"},
        "google_knowledge_graph": {"available": GoogleKGProvider().available, "requires": "GOOGLE_API_KEY"},
        "wikipedia": {"available": True, "requires": "None (public API)"},
        "wikidata": {"available": True, "requires": "None (public API)"},
    }
    return status


ahrefs = AhrefsProvider()
moz = MozProvider()
majestic = MajesticProvider()
serpapi = SerpAPIProvider()
openai = OpenAIClient()
anthropic = AnthropicClient()
perplexity = PerplexityClient()
newsapi = NewsAPIProvider()
google_kg = GoogleKGProvider()
wikipedia = WikipediaClient()

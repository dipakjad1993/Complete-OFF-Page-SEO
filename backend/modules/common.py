from fastapi import APIRouter, HTTPException, Depends
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

MODULE_TIMEOUT_SECS = 120

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

WIKI_HEADERS = {
    "User-Agent": "CompleteSEOScraper/2.0 (https://github.com/completeseo; contact@completeseo.com)",
    "Accept": "application/json",
}

# NOTE: Wikidata requires a descriptive User-Agent with contact info (browser UAs get 403).




def load_configs():
    try:
        with open("data/brand_configs.json", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception:
        return {}


def load_credentials():
    try:
        with open("data/api_credentials.json", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception:
        return {}


def _now_utc():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------
# Live analysis progress
# ---------------------------------------------------------------
_progress = {}


def _progress_path(brand_id):
    return os.path.join("data", "analysis_progress", f"{brand_id}.json")


def _update_progress(brand_id, **kwargs):
    state = _progress.setdefault(brand_id, {
        "status": "running",
        "started_at": _now_utc(),
        "module_index": 0,
        "total_modules": 35,
        "current_module": "",
        "current_module_label": "",
        "elapsed_secs": 0,
        "eta_secs": 0,
        "modules": {},
    })
    state.update(kwargs)
    state["updated_at"] = _now_utc()
    try:
        os.makedirs("data/analysis_progress", exist_ok=True)
        with open(_progress_path(brand_id), "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)
    except Exception:
        pass
    return state


def _reset_progress(brand_id):
    if brand_id in _progress:
        del _progress[brand_id]
    try:
        if os.path.exists(_progress_path(brand_id)):
            os.remove(_progress_path(brand_id))
    except Exception:
        pass


# ---------------------------------------------------------------
# URL / text helpers (real filtering, no fabrication)
# ---------------------------------------------------------------
def extract_domain(url):
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def _is_brand_domain(d, domain, name=""):
    """True when a domain is the brand's own (including subdomains like epaper.thehindu.com
    and registrable variants like branchioth.thehindu.co.in)."""
    if not d or not domain:
        return False
    d = d.lower().strip(".")
    dom = domain.lower().strip(".")
    if d == dom or d.endswith("." + dom):
        return True
    if name:
        token = re.sub(r"[^a-z0-9]", "", name.lower())
        if token and token in d.split("."):
            return True
    return False


def normalize_search_url(url):
    """Decode search-engine redirect wrappers back to the real destination URL."""
    try:
        import base64
        low = url.lower()
        if "bing.com/ck/a" in low:
            u = parse_qs(urlparse(url).query).get("u", [None])[0]
            if u:
                s = u[2:] if u.startswith("a1") else u
                s += "=" * ((4 - len(s) % 4) % 4)
                decoded = base64.urlsafe_b64decode(s.encode()).decode("utf-8", "ignore")
                if decoded.startswith("http"):
                    return decoded
        elif "google.com/url" in low or "googleusercontent.com" in low:
            q = parse_qs(urlparse(url).query).get("q", [None])[0]
            if q and q.startswith("http"):
                return q
        elif "uddg=" in url:
            u = parse_qs(urlparse(url).query).get("uddg", [None])[0]
            if u and u.startswith("http"):
                return u
    except Exception:
        pass
    return url


# Source relevance / quality controls for the report's "sources" library.
JUNK_SOURCE_DOMAINS = [
    "xnxx", "pornhub", "xvideos", "xhamster", "youporn", "redtube", "hentai", "hanime",
    "adult", "porno", "porn", "e-hentai", "lucioushentai", "jav", "avgle",
    "fanyi", "translate.yandex", "bing.com/translator", "deepl.com/translator",
    "random", "link-list", "spam", "casino", "betting", "gambling", "lottery",
    "crypto-pump", "free-tiktok", "insta-followers", "get-views", "download-mp3",
]
JUNK_SOURCE_PATHS = [
    "jpg-to-pdf", "pdf-to-", "png-to-", "heic-to", "online-convert", "convertio",
    "file-converter", "free-converter", "remove-watermark", "mp3-downloader",
]
GENERIC_SOURCE_TOKENS = {
    "home", "news", "media", "blog", "shop", "store", "best", "top", "free",
    "online", "world", "today", "group", "company", "inc", "llc", "corp",
    "about", "contact", "login", "sign", "apps", "app", "page", "main",
    "video", "live", "the", "new", "this", "our", "your", "more", "all",
    "ltd", "global", "digital", "official", "products", "product", "solution",
    "solutions", "services", "service", "business", "technology", "technologies",
}
CATEGORY_KEYWORDS = {
    "cybersecurity": ["security", "cyber", "threat", "malware", "ransomware", "firewall", "endpoint", "zero trust", "siem"],
    "cloud computing": ["cloud", "aws", "azure", "kubernetes", "docker", "saas", "infrastructure", "hosting"],
    "artificial intelligence": ["artificial intelligence", "ai", "machine learning", "llm", "generative", "chatbot", "gpt", "neural", "model"],
    "fintech": ["payment", "banking", "finance", "fintech", "trading", "lending", "blockchain", "wallet", "credit card"],
    "healthcare": ["healthcare", "medical", "clinical", "patient", "telehealth", "pharma", "health", "hospital", "clinic"],
    "e-commerce": ["e-commerce", "ecommerce", "shopping", "store", "retail", "marketplace", "checkout", "product", "cart"],
    "enterprise software": ["enterprise", "crm", "erp", "workflow", "productivity", "collaboration", "business software", "project management"],
    "developer tools": ["developer", "api", "sdk", "devops", "code", "repository", "open source", "programming", "software"],
    "data analytics": ["data", "analytics", "business intelligence", "dashboard", "reporting", "visualization", "data science", "insights"],
    "social media": ["social media", "social network", "follower", "engagement", "hashtag", "content", "marketing"],
    "marketing": ["seo", "marketing", "content", "campaign", "advertising", "analytics", "search engine", "backlink", "link building", "keyword", "brand"],
    "news media": ["news", "journalism", "headlines", "breaking news", "reporting", "newspaper", "media"],
}
# Specific, low-false-positive terms used to judge whether a page is relevant
# to the brand's vertical (used for source title verification).
STRONG_CATEGORY_KEYWORDS = {
    "cybersecurity": ["cybersecurity", "cyber security", "malware", "ransomware", "firewall", "zero trust", "threat intelligence", "endpoint security"],
    "cloud computing": ["cloud computing", "cloud platform", "aws", "microsoft azure", "google cloud", "kubernetes", "cloud infrastructure"],
    "artificial intelligence": ["artificial intelligence", "machine learning", "large language model", "generative ai", "chatgpt", "gpt", "llm", "neural network", "ai model", "ai assistant"],
    "fintech": ["fintech", "payment", "online payment", "digital banking", "blockchain", "crypto", "financial technology", "digital wallet"],
    "healthcare": ["healthcare", "health care", "telehealth", "medical", "clinical", "patient care", "health system", "hospital"],
    "e-commerce": ["e-commerce", "ecommerce", "online shopping", "ecommerce platform", "online store", "retail", "marketplace", "add to cart"],
    "enterprise software": ["enterprise software", "crm", "erp", "enterprise resource", "business software", "project management", "workflow automation"],
    "developer tools": ["developer", "sdk", "api", "devops", "open source", "programming", "software development", "code repository"],
    "data analytics": ["data analytics", "business intelligence", "data science", "data platform", "analytics", "data warehouse", "dashboard"],
    "social media": ["social media", "social media marketing", "instagram", "tiktok", "youtube", "social network", "social platform"],
    "marketing": ["seo", "search engine optimization", "backlink", "link building", "digital marketing", "content marketing", "seo tool", "keyword research", "google analytics", "search console"],
    "news media": ["breaking news", "news media", "headlines", "journalism", "newspaper", "news outlet", "news channel"],
}


def _brand_tokens(brand_name):
    return [t for t in re.split(r"[\W_]+", (brand_name or "").lower()) if len(t) >= 4 and t not in GENERIC_SOURCE_TOKENS]


# Words that indicate a DIFFERENT meaning of an ambiguous brand name (e.g. "The Hindu"
# newspaper vs the Hindu religion). When such a word co-occurs with the brand name
# and the page is not on the brand's own domain, the result is wrong-entity junk.
WRONG_ENTITY_LEXICON = {
    "religion", "religious", "temple", "god", "gods", "goddess", "mythology", "myth", "myths",
    "scripture", "scriptures", "bhagavad", "gita", "veda", "vedas", "vedic", "yoga", "hinduism",
    "nationalist", "supremacist", "fascism", "pagan", "paganism", "deity", "deities", "worship",
    "shrine", "puja", "panchang", "astrology", "horoscope", "astrolog", "shiva", "krishna",
    "ramayana", "mahabharata", "upanishad", "sadhguru", "adiyogi", "guru", "mandir", "devotee",
    "pilgrimage", "hindutva", "sangh", "kush", "himalaya", "calendar", "spiritual", "yogi",
    "ancient", "reincarnation", "karma", "dharma", "sacred", "holy", "faith", "belief",
    "nationalism", "right-wing", "right wing", "communal", "far-right", "hindu right", "hardline",
}


def _entity_variants(brand_name):
    """Canonical text forms of the brand that still refer to the SAME entity."""
    low = (brand_name or "").strip().lower()
    if not low:
        return []
    variants = {low, re.sub(r"\s+", "", low)}
    for article in ("the ", "a ", "an "):
        if low.startswith(article):
            variants.add(low[len(article):])
    return sorted(v for v in variants if len(v) >= 4)


def _entity_ok(brand_name, url="", title="", snippet="", brand_domain=""):
    """Return True only when a result (url/title/snippet) refers to the SAME entity as
    the brand. Rejects wrong-entity collisions (e.g. 'The Hindu' newspaper vs the
    Hindu religion) and partial-token noise. Single-word unique brands are accepted.
    """
    if not brand_name or len(brand_name.split()) == 1:
        return True
    variants = _entity_variants(brand_name)
    if not variants:
        return True
    text = f"{url} {title} {snippet}".lower()
    if brand_domain and brand_domain in url.lower():
        return True
    if not any(v in text for v in variants):
        return False
    # Any wrong-entity signal on a third-party page => reject.
    if any(w in text for w in WRONG_ENTITY_LEXICON):
        return False
    return True


def _entity_keep(results, brand_name, brand_domain=""):
    """Filter a list of result dicts through the entity gate (in place)."""
    kept = []
    for r in results:
        if _entity_ok(brand_name, r.get("url", ""), r.get("title", ""), r.get("snippet", "") or r.get("description", ""), brand_domain):
            kept.append(r)
    return kept


def _source_keepable(url, brand_name, brand_domain, brand_category=""):
    """Return True only for sources that are plausibly relevant to THIS brand."""
    try:
        low = url.lower()
        d = extract_domain(low)
        if not d:
            return False
        if brand_domain and brand_domain in low:
            return True
        if any(j in d for j in JUNK_SOURCE_DOMAINS):
            return False
        if any(bp in low for bp in JUNK_SOURCE_PATHS):
            return False
        brand_toks = _brand_tokens(brand_name)
        if brand_toks and any(t in low for t in brand_toks):
            # Entity gate: reject wrong-entity URLs (e.g. hinduism/bhagavad-gita for "The Hindu").
            return _entity_ok(brand_name, url=low, brand_domain=brand_domain)
        return False
    except Exception:
        return False


_source_title_cache = {}


def _title_matches(url, brand_name, brand_category):
    """Return True if the page title contains the brand name or a strong
    category keyword. Uses a per-run cache to avoid re-fetching duplicates."""
    if url in _source_title_cache:
        return _source_title_cache[url]
    result = False
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=6, follow_redirects=True, verify=True)
        if resp.status_code == 200 and resp.text:
            soup = BeautifulSoup(resp.text, "html.parser")
            title = soup.title.get_text(strip=True) if soup.title else ""
            if _entity_ok(brand_name, title=title, brand_domain=url):
                result = True
    except Exception:
        pass
    _source_title_cache[url] = result
    return result


async def safe_fetch(url, client, timeout=10):
    try:
        resp = await client.get(url, headers=HEADERS, timeout=timeout, follow_redirects=True)
        if resp.status_code == 200 and len(resp.text) > 100:
            return resp.text
    except Exception:
        pass
    return None


async def deep_fetch_website(domain, client):
    """Deep crawl a website across multiple pages to get comprehensive data."""
    urls_to_try = [
        f"https://{domain}",
        f"https://www.{domain}",
        f"https://{domain}/about",
        f"https://{domain}/about-us",
        f"https://{domain}/company",
        f"https://{domain}/team",
        f"https://{domain}/leadership",
        f"https://{domain}/products",
        f"https://{domain}/solutions",
        f"https://{domain}/services",
        f"https://{domain}/blog",
        f"https://{domain}/news",
        f"https://{domain}/contact",
        f"https://{domain}/investors",
        f"https://{domain}/press",
    ]
    results = await asyncio.gather(*(safe_fetch(u, client, timeout=8) for u in urls_to_try))
    return {u: html for u, html in zip(urls_to_try, results) if html and len(html) > 200}


def extract_comprehensive_data(pages_data):
    """Extract comprehensive brand data from multiple crawled pages."""
    all_text = ""
    titles = []
    descriptions = []
    headings = []
    paragraphs = []
    social_links = set()
    schema_orgs = []
    exec_found = []
    links = []

    for url, html in pages_data.items():
        try:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            all_text += " " + text

            t = soup.find("title")
            if t:
                titles.append(t.get_text(strip=True))

            for meta in soup.find_all("meta"):
                name_attr = meta.get("name", "").lower()
                prop = meta.get("property", "").lower()
                content = meta.get("content", "")
                if name_attr == "description" or prop == "og:description":
                    if content:
                        descriptions.append(content[:500])
                if name_attr == "keywords" and content:
                    titles.append("KEYWORDS:" + content)

            for h in soup.find_all(["h1", "h2", "h3", "h4"]):
                ht = h.get_text(strip=True)
                if ht and len(ht) > 3:
                    headings.append(ht)

            for p in soup.find_all("p"):
                pt = p.get_text(strip=True)
                if pt and len(pt) > 30:
                    paragraphs.append(pt[:500])

            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        schema_orgs.append(data)
                        if data.get("sameAs"):
                            same_as = data["sameAs"] if isinstance(data["sameAs"], list) else [data["sameAs"]]
                            for sa in same_as:
                                social_links.add(sa)
                        if data.get("url"):
                            links.append(data["url"])
                except Exception:
                    pass

            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                for platform in ["linkedin.com", "twitter.com", "x.com", "facebook.com", "youtube.com", "instagram.com", "github.com"]:
                    if platform in href:
                        social_links.add(href)

            exec_patterns = [
                r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s*[-–—,]\s*(CEO|CTO|CFO|COO|CMO|CISO|CRO|CPO|President|Founder|Co-Founder|Chairman|VP|Vice President|Director)',
                r'(CEO|CTO|CFO|COO|CMO|CISO|CRO|CPO|President|Founder|Co-Founder|Chairman)\s*[-–—:]\s*([A-Z][a-z]+\s+[A-Z][a-z]+)',
                r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s+((?:Chief|Head|VP|Vice President|Director)\s+\w+(?:\s+\w+)?)',
            ]
            for pattern in exec_patterns:
                for match in re.findall(pattern, soup.get_text()):
                    if len(match) >= 2:
                        name_part = match[0] if any(t in match[0] for t in ["CEO", "CTO", "CFO", "COO", "CMO", "President", "Founder", "Chairman", "VP", "Director", "Chief", "Head"]) else match[1]
                        title_part = match[1] if name_part == match[0] else match[0]
                        if len(name_part) > 3 and len(title_part) > 2:
                            exec_found.append({"name": name_part, "title": title_part})

            for a_tag in soup.find_all("a", href=True):
                full_href = a_tag.get("href", "")
                link_text = a_tag.get_text(strip=True)
                if full_href.startswith("http") and link_text:
                    links.append({"url": full_href, "text": link_text[:100]})

        except Exception:
            pass

    seen_execs = set()
    unique_execs = []
    for e in exec_found:
        key = e["name"].lower()
        if key not in seen_execs and len(e["name"]) > 4:
            seen_execs.add(key)
            unique_execs.append(e)

    return {
        "all_text": all_text[:50000],
        "titles": titles,
        "descriptions": descriptions,
        "headings": headings[:50],
        "paragraphs": paragraphs[:100],
        "social_links": list(social_links)[:30],
        "schema_orgs": schema_orgs,
        "executives": unique_execs[:10],
        "page_links": links[:200],
        "total_paragraphs": len(paragraphs),
        "total_headings": len(headings),
        "page_count": len(pages_data),
    }


async def get_wikipedia(name, client):
    results = {"url": "", "description": "", "extract": "", "summary": "", "categories": [], "links": []}
    try:
        resp = await client.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{name}", headers=WIKI_HEADERS, timeout=10)
        if resp.status_code == 200:
            d = resp.json()
            results["url"] = d.get("content_urls", {}).get("desktop", {}).get("page", "")
            results["description"] = d.get("description", "")
            results["extract"] = d.get("extract", "")[:1500]
            results["summary"] = d.get("extract", "")[:800]
    except Exception:
        pass
    if not results["url"]:
        alt_names = [name.replace(" ", "_"), name.replace(" ", "-"), name.split()[0] if " " in name else name]
        for alt in alt_names:
            try:
                resp = await client.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{alt}", headers=WIKI_HEADERS, timeout=8)
                if resp.status_code == 200:
                    d = resp.json()
                    results["url"] = d.get("content_urls", {}).get("desktop", {}).get("page", "")
                    results["description"] = d.get("description", "")
                    results["extract"] = d.get("extract", "")[:1500]
                    break
            except Exception:
                pass
    return results


async def get_wikidata(name, client, wd_id=None):
    """Fetch a Wikidata entity and return its claims keyed by PROPERTY ID (P31, P17...).

    When wd_id is supplied it is used directly (stored brand entity). Otherwise a
    name search is performed. Claim values that are Q-entity ids are resolved to
    human-readable labels via a single batched wbgetentities call.
    """
    results = {"id": "", "label": "", "description": "", "claims": {}, "prop_labels": {}, "sitelinks": 0, "aliases": []}
    try:
        if not wd_id:
            resp = await client.get(
                f"https://www.wikidata.org/w/api.php?action=wbsearchentities&search={name}&language=en&format=json&limit=3",
                headers=WIKI_HEADERS, timeout=10)
            if resp.status_code != 200:
                return results
            search_results = resp.json().get("search", [])
            if not search_results:
                return results
            wd_id = search_results[0].get("id", "")
            results["label"] = search_results[0].get("label", "")
            results["description"] = search_results[0].get("description", "")
            results["aliases"] = search_results[0].get("aliases", [])

        results["id"] = wd_id
        claims_resp = await client.get(
            f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={wd_id}&format=json&props=claims|labels|descriptions|sitelinks",
            headers=WIKI_HEADERS, timeout=12)
        if claims_resp.status_code != 200:
            return results
        entity = claims_resp.json().get("entities", {}).get(wd_id, {})
        claims = entity.get("claims", {})
        results["sitelinks"] = entity.get("sitelinks")
        if not results["label"]:
            results["label"] = entity.get("labels", {}).get("en", {}).get("value", wd_id)
        if not results["description"]:
            results["description"] = entity.get("descriptions", {}).get("en", {}).get("value", "")

        prop_map = {
            "P31": "instance_of", "P17": "country", "P159": "headquarters",
            "P112": "founders", "P452": "industry", "P856": "website",
            "P2002": "twitter", "P2013": "facebook", "P18": "image",
            "P463": "member_of", "P1056": "product", "P127": "owned_by",
            "P169": "chief_executive_officer", "P488": "chairperson",
            "P749": "parent_organization", "P154": "logo",
            "P2003": "instagram", "P400": "platform", "P176": "manufacturer",
            "P279": "subclass_of", "P571": "inception", "P414": "stock_exchange",
        }
        results["prop_labels"] = prop_map
        raw_values = {}
        qids_needed = set()
        for pid in prop_map:
            if pid not in claims:
                continue
            vals = []
            for claim in claims[pid]:
                ms = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                if isinstance(ms, dict):
                    v = ms.get("id", ms.get("text", ms.get("amount", "")))
                else:
                    v = str(ms)
                if v:
                    vals.append(v)
                    if str(v).startswith("Q") and str(v)[1:].isdigit():
                        qids_needed.add(str(v))
            if vals:
                raw_values[pid] = vals[0] if len(vals) == 1 else vals

        label_map = {}
        if qids_needed:
            qids_needed = sorted(qids_needed)[:40]
            try:
                lbl_resp = await client.get(
                    "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=" + "|".join(qids_needed) +
                    "&format=json&props=labels|descriptions", headers=WIKI_HEADERS, timeout=12)
                if lbl_resp.status_code == 200:
                    for qid, ent in lbl_resp.json().get("entities", {}).items():
                        lbl = ent.get("labels", {}).get("en", {}).get("value")
                        if lbl:
                            label_map[qid] = lbl
            except Exception:
                pass

        for pid, vals in raw_values.items():
            if isinstance(vals, list):
                display = []
                for v in vals:
                    display.append(label_map.get(v, v) if v in label_map else v)
                results["claims"][pid] = display if len(display) > 1 else display[0]
            else:
                results["claims"][pid] = label_map.get(vals, vals) if vals in label_map else vals
    except Exception:
        pass
    return results


# ---------------------------------------------------------------
# Honest data access helpers (never fabricate)
# ---------------------------------------------------------------
def _module_unavailable(feature_name, requires, reason):
    return {
        "feature_name": feature_name,
        "status": "unavailable",
        "verified": False,
        "requires": requires,
        "detail": reason,
        "assessment": "unavailable",
        "recommendation": f"Requires {requires} to produce verified data. {reason}",
        "detailed_analysis": (
            f"No data was fabricated for \"{feature_name}\". Configure {requires} "
            f"and re-run the analysis to get real, verified output. Reason: {reason}"
        ),
    }


_search_cache: dict = {}
_SEARCH_CACHE_TTL = 600


async def _search(query, brand_name, num=12, require_relevance=True, domain=None):
    """Real, relevance-filtered web search filtered through the entity gate.
    Returns a list of result dicts that refer to the same brand entity."""
    key = f"{brand_name}|{num}|{require_relevance}|{query}"
    hit = _search_cache.get(key)
    if hit and hit[0] > __import__("time").time() - _SEARCH_CACHE_TTL:
        results = hit[1]
    else:
        r = await search_web(query, brand_name=brand_name, num=num, require_relevance=require_relevance)
        results = r.value if (is_verified(r) and r.value) else []
        _search_cache[key] = (__import__("time").time(), results)
    if not results or len(brand_name.split()) <= 1:
        return results
    return _entity_keep(results, brand_name, domain or "")


async def _resolve_news_url(client, url):
    """Follow a Google News /rss/articles/ redirect to its real publisher URL."""
    if "news.google.com/rss/articles" not in url:
        return url
    try:
        resp = await client.get(url, headers=HEADERS, timeout=12, follow_redirects=True)
        if resp.status_code == 200 and str(resp.url).startswith("http") and "news.google.com" not in str(resp.url):
            return str(resp.url)
        # Google News serves a meta-refresh page for JS-less clients; parse it.
        m = re.search(r'content="[^"]*url=[\'"]?([^"\'>\s]+)', resp.text, re.IGNORECASE)
        if m:
            target = m.group(1)
            if target.startswith("http") and "news.google.com" not in target:
                return target
    except Exception:
        pass
    return url


async def _site_probe(client, domain, paths, timeout=8):
    """Probe a list of paths on the brand's domain. Returns real responses."""
    out = []
    for p in paths:
        try:
            resp = await client.get(f"https://{domain}{p}", headers=HEADERS, timeout=timeout, follow_redirects=True)
            out.append({
                "path": p,
                "status": resp.status_code,
                "content_type": resp.headers.get("content-type", ""),
                "size": len(resp.text),
                "final_url": str(resp.url),
            })
        except Exception:
            out.append({"path": p, "status": None, "content_type": "", "size": 0, "final_url": ""})
    return out


def _has_llm():
    return openai.available or anthropic.available or perplexity.available


async def _llm_chat(messages):
    """Send a chat to the first configured LLM provider. Returns VerifiedData or None."""
    for prov in (perplexity, openai, anthropic):
        if prov.available:
            r = await prov.chat(messages)
            if is_verified(r):
                return r
    return None


def _llm_text(r):
    if not is_verified(r):
        return ""
    if isinstance(r.value, dict):
        return r.value.get("answer", "")
    return str(r.value)


def _llm_citations(r):
    if is_verified(r) and isinstance(r.value, dict):
        return r.value.get("citations", []) or []
    return []


async def _llm_json(messages):
    """Ask an LLM for a JSON object. Returns parsed dict or None."""
    r = await _llm_chat([{"role": "system", "content": "Respond with ONLY a valid JSON object. No markdown, no explanation."}] + messages)
    if not r:
        return None
    text = _llm_text(r).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


async def _sentiment_llm(text):
    """Real LLM sentiment in [0,1]. Returns None when unavailable/unparseable."""
    r = await _llm_chat([
        {"role": "system", "content": "You are a sentiment analyzer. Respond with ONLY a single float between 0.0 (very negative) and 1.0 (very positive). No explanation."},
        {"role": "user", "content": text[:2000]},
    ])
    if not r:
        return None
    try:
        return max(0.0, min(1.0, float(_llm_text(r).strip())))
    except Exception:
        return None


_da_cache = {}


async def get_da(domain):
    """Real domain authority/rating from configured providers (Moz > Ahrefs > Majestic)."""
    domain = (domain or "").lower().replace("www.", "")
    if not domain:
        return unavailable("No domain supplied.", "MOZ_ACCESS_KEY+MOZ_SECRET_KEY or AHREFS_API_KEY or MAJESTIC_API_KEY")
    if domain in _da_cache:
        return _da_cache[domain]
    if len(_da_cache) >= getattr(settings, "MAX_BACKLINK_REQUESTS", 100):
        return unavailable("Domain-authority lookups exhausted for this run.", "MAX_BACKLINK_REQUESTS")
    result = None
    try:
        rm = await moz.url_metrics([domain])
        if is_verified(rm) and rm.value and rm.value[0].get("domain_authority") is not None:
            result = verified(rm.value[0].get("domain_authority"), source="moz_api",
                              method="moz_lsapi_v2_url_metrics", source_url=f"https://{domain}",
                              metadata=rm.value[0])
        else:
            ra = await ahrefs.domain_rating(domain)
            if is_verified(ra) and ra.value is not None:
                result = verified(ra.value, source="ahrefs_api", method="ahrefs_v3_domain_rating",
                                  source_url=f"https://{domain}", metadata=ra.metadata)
            else:
                rj = await majestic.get_index_item_info([domain])
                if is_verified(rj) and rj.value and rj.value.get("trust_flow") is not None:
                    result = verified(rj.value.get("trust_flow"), source="majestic_api",
                                      method="majestic_trust_flow", source_url=f"https://{domain}",
                                      metadata=rj.value)
    except Exception:
        pass
    if result is None:
        result = unavailable("No backlink-authority provider is configured.",
                             "MOZ_ACCESS_KEY+MOZ_SECRET_KEY or AHREFS_API_KEY or MAJESTIC_API_KEY")
    _da_cache[domain] = result
    return result


async def _da_embed(mentions):
    """Attach real DA to mention dicts (capped, cached). Returns mentions unchanged."""
    for m in mentions:
        d = m.get("domain") or extract_domain(m.get("url", ""))
        da = await get_da(d)
        if is_verified(da):
            m["da"] = da.value
            m["da_source"] = da.source
        else:
            m["da"] = None
            m["da_unavailable"] = da.requires
    return mentions


def _result(feature_name, method, data):
    return {
        "feature_name": feature_name,
        "status": "ok",
        "verified": True,
        "method": method,
        "retrieved_at": _now_utc(),
        **data,
    }


# ============================================================
# FEATURE 1: LLM Co-Mention & Perception Auditing
# ============================================================


# Shared signal lexicons (moved here in monolith split; used across domain modules).
FORUM_DOMAINS = ["reddit.com", "old.reddit.com", "quora.com", "stackoverflow.com", "news.ycombinator.com",
                 "hackernews.com", "discuss."]
PODCAST_VIDEO_DOMAINS = ["podcasts.apple.com", "open.spotify.com", "youtube.com", "www.youtube.com",
                         "podbean.com", "spreaker.com", "iheart.com", "buzzsprout.com", "podcast.apple.com",
                         "anchor.fm", "vimeo.com", "twitch.tv"]
STALE_INDICATORS = ["was founded", "previously known", "used to be", "discontinued", "shut down",
                    "no longer", "old version", "deprecated", "legacy", "obsolete", "end of life", "sunset"]
TOXIC_TLD_KEYWORDS = ["casino", "gambling", "bet", "porn", "sex", "adult", "pharma", "viagra", "cbd", "loan", "payday", "spam", "free-", "vpn-blog"]


__all__ = [
    "APIRouter",
    "Alert",
    "Backlink",
    "BaseModel",
    "BeautifulSoup",
    "Brand",
    "BrandMention",
    "CATEGORY_KEYWORDS",
    "Competitor",
    "ConsensusScore",
    "Counter",
    "Depends",
    "Executive",
    "FORUM_DOMAINS",
    "GENERIC_SOURCE_TOKENS",
    "HEADERS",
    "HTTPException",
    "JUNK_SOURCE_DOMAINS",
    "JUNK_SOURCE_PATHS",
    "KnowledgeGraphTriple",
    "MODULE_TIMEOUT_SECS",
    "PODCAST_VIDEO_DOMAINS",
    "PassageAttention",
    "RAGCitation",
    "STALE_INDICATORS",
    "STRONG_CATEGORY_KEYWORDS",
    "Session",
    "TOXIC_TLD_KEYWORDS",
    "UnavailableData",
    "VectorDistance",
    "VerifiedData",
    "WIKI_HEADERS",
    "WRONG_ENTITY_LEXICON",
    "_SEARCH_CACHE_TTL",
    "_brand_tokens",
    "_da_cache",
    "_da_embed",
    "_entity_keep",
    "_entity_ok",
    "_entity_variants",
    "_has_llm",
    "_is_brand_domain",
    "_llm_chat",
    "_llm_citations",
    "_llm_json",
    "_llm_text",
    "_module_unavailable",
    "_now_utc",
    "_progress",
    "_progress_path",
    "_reset_progress",
    "_resolve_news_url",
    "_result",
    "_search",
    "_sentiment_llm",
    "_site_probe",
    "_source_keepable",
    "_source_title_cache",
    "_title_matches",
    "_update_progress",
    "ahrefs",
    "anthropic",
    "asyncio",
    "datetime",
    "deep_fetch_website",
    "extract_comprehensive_data",
    "extract_domain",
    "free_apis",
    "get_da",
    "get_db",
    "get_wikidata",
    "get_wikipedia",
    "google_kg",
    "httpx",
    "is_unavailable",
    "is_verified",
    "json",
    "load_configs",
    "load_credentials",
    "majestic",
    "math",
    "moz",
    "newsapi",
    "normalize_search_url",
    "openai",
    "os",
    "parse_qs",
    "perplexity",
    "re",
    "safe_fetch",
    "search_news",
    "search_web",
    "serpapi",
    "settings",
    "timezone",
    "unavailable",
    "urlparse",
    "verified",
    "verify_url",
]

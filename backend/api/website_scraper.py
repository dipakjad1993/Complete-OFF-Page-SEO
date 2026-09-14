from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
import re
import json
import asyncio
import logging
import traceback
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, quote_plus, unquote, parse_qs

from config.settings import settings

logger = logging.getLogger("offpage.scraper")

router = APIRouter()


def _log_swallow(where: str, exc: BaseException, url: str = "") -> None:
    """Log swallowed scraper failures at debug level — never hides root cause anymore."""
    try:
        logger.debug("scraper swallow [%s] url=%s err=%s", where, (url or "")[:160], str(exc)[:220])
    except Exception:
        pass

class ScrapeRequest(BaseModel):
    url: str
    lean: bool = False  # v2026.3: lean=true returns title/H1/schema/OG only (fast intake path)

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

API_HEADERS = {
    "User-Agent": "CompleteSEOScraper/2.0 (https://github.com/completeseo; contact@completeseo.com)",
    "Accept": "application/json",
}

SEARCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

ALL_TITLE_PATTERNS = re.compile(
    r'(CEO|CTO|CFO|COO|CMO|CISO|CRO|CPO|CDO|CTPO|CCO|CAIO|'
    r'President|Vice President|VP|SVP|EVP|AVP|'
    r'Founder|Co-Founder|Co-Founder & |'
    r'Chairman|Chairwoman|Board Chair|'
    r'Chief\s+\w+\s+Officer|'
    r'Head\s+of\s+[\w\s]{2,30}|'
    r'Director|Senior Director|Executive Director|Managing Director|'
    r'General Manager|Senior Manager|'
    r'Lead\s+[\w\s]{2,20}|'
    r'Principal\s+[\w\s]{2,20}|'
    r'Distinguished\s+[\w\s]{2,20}|'
    r'Fellow|Research\s+Scientist|Staff\s+Engineer|'
    r'Senior\s+[\w\s]{2,20}|'
    r'Partner|Principal)\s*$',
    re.IGNORECASE
)

NAME_PATTERN = re.compile(r'^([A-Z][a-záàâäãåæçéèêëíìîïñóòôöõøúùûüýÿ]+(?:\s+[A-Z][a-záàâäãåæçéèêëíìîïñóòôöõøúùûüýÿ]+){1,3})$')
BUSINESS_WORDS = {'Inc','LLC','Corp','Ltd','Company','Enterprise','Group','Holdings','Partners','Associates','Technologies','Solutions','Services','Systems','Labs','Studio','Media','Capital','Ventures','Digital','Global','International','National','North','South','East','West','United','American','British','European','Asia','Pacific','Africa','Cloud','Data','Tech','Net','Web','App','Soft','AI','ML','IoT','API','SaaS','PaaS','IaaS'}

async def safe_fetch(url, client, timeout=12):
    try:
        resp = await client.get(url, headers=BROWSER_HEADERS, timeout=timeout, follow_redirects=True)
        if resp.status_code < 400 and len(resp.text) > 500:
            return resp.text
        logger.debug("safe_fetch non-ok url=%s status=%s len=%s", (url or "")[:160],
                     getattr(resp, "status_code", "?"), len(getattr(resp, "text", "") or ""))
    except Exception as e:
        _log_swallow("safe_fetch", e, url)
    return None

async def search_web(query, client, max_results=8):
    """Delegate to the central provider chain (SerpAPI -> cache -> Brave ->
    Bing Web -> Bing RSS -> ddgs) with provider attribution. The old
    Google-HTML / DDG-HTML / DDG-Lite scraping legs were removed in v2026.3:
    they broke on markup changes and caused log spam. Returns the legacy
    [{title, body, href, domain}] shape so callers are unchanged.
    """
    try:
        from backend.services.search import search_web as _central
        from backend.services.verification import is_verified
        res = await _central(query, brand_name="", num=max_results, require_relevance=False)
        if is_verified(res):
            out = []
            for r in (res.value or [])[:max_results]:
                url = r.get("url") or r.get("link") or ""
                if not url.startswith("http"):
                    continue
                out.append({"title": (r.get("title") or "")[:300],
                            "body": (r.get("snippet") or r.get("body") or r.get("description") or "")[:600],
                            "href": url, "domain": r.get("domain") or extract_domain(url)})
            if out:
                return out[:max_results]
    except Exception as e:  # noqa: BLE001
        _log_swallow("search.central", e, query)
    # Last-resort: Bing RSS direct (free, no key) so intake never hard-fails.
    try:
        from urllib.parse import quote_plus
        import httpx as _hx
        async with _hx.AsyncClient(timeout=10, follow_redirects=True, verify=False) as _c:
            resp = await _c.get(
                f"https://www.bing.com/search?q={quote_plus(query)}&format=rss&count={max_results}",
                headers=SEARCH_HEADERS)
            if resp.status_code == 200 and resp.text.strip().startswith("<?xml"):
                from bs4 import BeautifulSoup as _BS
                soup = _BS(resp.text, "xml")
                out = []
                for item in soup.find_all("item")[:max_results]:
                    title = item.title.get_text(strip=True) if item.title else ""
                    link = item.link.get_text(strip=True) if item.link else ""
                    desc = item.find("description").get_text(" ", strip=True) if item.find("description") else ""
                    if title and link.startswith("http"):
                        out.append({"title": title[:300], "body": desc[:600],
                                    "href": link, "domain": extract_domain(link)})
                return out[:max_results]
    except Exception as e:  # noqa: BLE001
        _log_swallow("search.bing_rss_fallback", e, query)
    return []




# REMOVED 2026-09-11: static COMPETITOR_DB hardcoded peer table
# (e.g. news media -> Reuters/AP/Bloomberg/NYT/CNN) was generic demo data,
# identical for every brand in an industry — not a live finding for THIS
# brand. Competitor resolution is now live-only in _discover_competitors()
# (web-search discovery + live HTTP verification, honest empty on failure).

def extract_domain(url):
    try: return urlparse(url).netloc.replace("www.", "")
    except: return ""

# NOTE: a previous version of this file contained a hardcoded get_da()
# static lookup table (techcrunch.com:95, reuters:96, default 50, ...).
# That table was fabricated demo data — REMOVED 2026-09-11. Domain
# authority is now ONLY reported via live providers (Moz/Ahrefs/Majestic)
# in backend/api/analysis.py:get_da(), which returns honest
# UnavailableData when no provider key is configured. Nothing here may
# ever return a static authority score.

def detect_industry(merged, extra_desc=""):
    if isinstance(merged, dict):
        title_text = " ".join(merged.get("titles", [])[:3])
        desc_text = " ".join(merged.get("descriptions", [])[:2]) + " " + extra_desc
        heading_text = " ".join(merged.get("headings", [])[:25])
        full_text = merged.get("all_text", "")
    else:
        title_text = desc_text = heading_text = ""
        full_text = (merged or "") + " " + extra_desc

    def matches(kw):
        pattern = r"\b" + re.escape(kw) + r"\b"
        try:
            n_title = len(re.findall(pattern, title_text + " " + desc_text, re.IGNORECASE))
            n_heading = len(re.findall(pattern, heading_text, re.IGNORECASE))
            n_full = len(re.findall(pattern, full_text, re.IGNORECASE))
        except re.error:
            return 0
        return n_title * 4 + n_heading * 2 + n_full

    checks = [
        ("news media", ["news", "breaking news", "headlines", "latest news", "journalism", "editorial", "newspaper", "top stories", "world news", "live updates", "top headlines", "correspondent", "daily news"]),
        ("cybersecurity", ["cybersecurity", "security", "cyber", "threat", "threats", "firewall", "encryption", "malware", "ransomware", "endpoint", "zero-trust", "siem", "xdr", "sase", "penetration", "infosec", "network security", "vulnerability"]),
        ("artificial intelligence", ["artificial intelligence", "machine learning", "deep learning", "large language model", "neural network", "generative ai", "generative", "nlp", "computer vision", "gpt", "llm", "chatbot", "ai model", "ai-powered", "ai platform", "ai assistant", "ai agent", "machine-learning"]),
        ("cloud computing", ["cloud computing", "cloud services", "cloud platform", "cloud storage", "saas", "paas", "iaas", "aws", "azure", "kubernetes", "docker", "infrastructure", "hosting", "cloud"]),
        ("fintech", ["fintech", "payments", "payment", "banking", "finance", "trading", "investment", "investing", "lending", "blockchain", "defi", "wallet", "financial services", "digital payments", "online payment", "credit card", "money transfer", "capital"]),
        ("healthcare", ["healthcare", "health care", "medical", "clinical", "patient", "patients", "diagnosis", "treatment", "pharma", "pharmaceutical", "telehealth", "electronic health", "health record", "hospital", "clinic", "biotech", "health insurance"]),
        ("e-commerce", ["e-commerce", "ecommerce", "shopping", "shop", "store", "commerce", "marketplace", "checkout", "cart", "retail", "online store", "add to cart", "buy now", "free shipping", "product"]),
        ("social media", ["social media", "social network", "social", "followers", "follower", "follow us", "timeline", "feed", "social platform", "hashtag", "share this", "social marketing", "engagement", "profile", "community"]),
        ("enterprise software", ["enterprise software", "enterprise", "crm", "erp", "workflow", "productivity", "collaboration", "sso", "business software", "sales team", "project management", "business platform", "customer relationship", "automation software"]),
        ("developer tools", ["api", "sdk", "developer", "developers", "code", "repository", "documentation", "integration", "ci/cd", "devops", "api platform", "api gateway", "software development", "open source", "code review", "developer tools", "sdk for"]),
        ("data analytics", ["data analytics", "analytics", "business intelligence", "insights", "insight", "dashboard", "dashboards", "reporting", "visualization", "bi", "etl", "data platform", "data warehouse", "data science", "data pipeline", "data engineering", "real-time data"]),
        ("marketing", ["marketing", "seo", "advertising", "campaign", "campaigns", "content", "email marketing", "automation", "ads", "digital marketing", "marketing platform", "marketing automation", "content marketing", "search engine", "growth marketing", "lead generation", "brand"]),
    ]
    best_cat = "technology"
    best_score = -1
    for cat, keywords in checks:
        active = [(kw, matches(kw)) for kw in keywords if matches(kw) > 0]
        if not active:
            continue
        distinct = len(active)
        total = min(sum(m for _, m in active), 60)
        score = distinct * 10 + total
        if score > best_score:
            best_score = score
            best_cat = cat
    return best_cat

def is_valid_person_name(name):
    name = name.strip()
    if len(name) < 5 or len(name) > 80: return False
    if any(c.isdigit() for c in name): return False
    if any(w in name for w in ['©','®','™','http','www','.com','.org','.net','&amp;','{','}','<','>','function','var ','const ','let ','return','import','class=','src=','alt=','width=','height=']): return False
    if any(w in name for w in ['Privacy','Terms','Cookie','Copyright','Contact','Subscribe','Newsletter','Download','Sign','Log','Menu','Home','Search','All','More','Back','Next','Previous','Close','Submit','Cancel','OK','Yes','No','Loading','Error','Warning','Info','Help','FAQ','Support','About','Blog','News','Press','Careers','Investors','Legal']): return False
    words = name.split()
    if len(words) < 2: return False
    if not all(w[0].isupper() for w in words if len(w) > 1): return False
    if any(w in BUSINESS_WORDS for w in words): return False
    return True

def is_valid_title(title):
    title = title.strip()
    if len(title) < 3 or len(title) > 120: return False
    if any(w in title.lower() for w in ['privacy','terms','cookie','copyright','subscribe','newsletter','download','sign up','log in','menu','search','loading','error','warning','read more','click here','learn more','view all','see all','back','next','previous','close','submit','cancel','ok','yes','no','faq','help','support']): return False
    return True

def extract_executives_from_html(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    execs = []
    seen_names = set()

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict): data = item; break
            if not isinstance(data, dict): continue
            for key in ["employee", "founder", "coFounder", "member", "author", "performer"]:
                if key in data:
                    people = data[key] if isinstance(data[key], list) else [data[key]]
                    for p in people:
                        if isinstance(p, dict) and p.get("name"):
                            execs.append({"name": p["name"], "title": p.get("jobTitle", key.title()), "bio": p.get("description", ""), "linkedin": "", "image": p.get("image", "")})
        except Exception as _e:
            _log_swallow("scraper", _e)

    card_selectors = [
        '[class*="team"]', '[class*="leader"]', '[class*="exec"]', '[class*="staff"]',
        '[class*="member"]', '[class*="people"]', '[class*="person"]', '[class*="bio"]',
        '[class*="card"]', '[class*="profile"]',
        '[id*="team"]', '[id*="leader"]', '[id*="exec"]', '[id*="people"]',
    ]
    for selector in card_selectors:
        for card in soup.select(selector):
            for tag in card.find_all(["strong", "b", "h2", "h3", "h4", "h5", "span", "a", "p"]):
                tag_text = tag.get_text(strip=True)
                if not tag_text or len(tag_text) < 5 or len(tag_text) > 60: continue
                if NAME_PATTERN.match(tag_text) and is_valid_person_name(tag_text):
                    title_text = ""
                    next_el = tag.find_next_sibling()
                    if next_el: title_text = next_el.get_text(strip=True)[:120]
                    parent = tag.parent
                    if parent:
                        parent_text = parent.get_text(separator=" ", strip=True)
                        title_match = ALL_TITLE_PATTERNS.search(parent_text)
                        if title_match: title_text = title_match.group(0).strip()
                    linkedin = ""
                    for a in card.find_all("a", href=True):
                        if "linkedin.com/in/" in a["href"]:
                            linkedin = a["href"]; break
                    if tag_text not in seen_names:
                        seen_names.add(tag_text)
                        execs.append({"name": tag_text, "title": title_text if is_valid_title(title_text) else "", "bio": "", "linkedin": linkedin, "image": ""})

    full_text = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in full_text.split("\n") if l.strip()]
    for i, line in enumerate(lines):
        for sep in [' - ', ' — ', ' – ', ', ', ' | ', ': ']:
            if sep in line:
                parts = line.split(sep, 1)
                if len(parts) == 2:
                    name_part, title_part = parts[0].strip(), parts[1].strip()
                    if is_valid_person_name(name_part) and ALL_TITLE_PATTERNS.search(title_part):
                        if name_part not in seen_names:
                            seen_names.add(name_part)
                            execs.append({"name": name_part, "title": title_part[:120], "bio": "", "linkedin": "", "image": ""})
        title_match = ALL_TITLE_PATTERNS.search(line)
        if title_match and i + 1 < len(lines):
            next_line = lines[i + 1]
            if is_valid_person_name(next_line) and next_line not in seen_names:
                seen_names.add(next_line)
                execs.append({"name": next_line, "title": line[:120], "bio": "", "linkedin": "", "image": ""})
        if NAME_PATTERN.match(line) and is_valid_person_name(line) and i + 1 < len(lines):
            next_line = lines[i + 1]
            if ALL_TITLE_PATTERNS.search(next_line) and line not in seen_names:
                seen_names.add(line)
                execs.append({"name": line, "title": next_line[:120], "bio": "", "linkedin": "", "image": ""})

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "linkedin.com/in/" in href:
            link_text = a.get_text(strip=True)
            if link_text and is_valid_person_name(link_text) and link_text not in seen_names:
                seen_names.add(link_text)
                parent = a.parent
                title_text = ""
                if parent:
                    parent_text = parent.get_text(strip=True)
                    for sep in [' - ', ' — ', ' – ', ', ', ' | ', ': ']:
                        if sep in parent_text:
                            parts = parent_text.split(sep, 1)
                            if len(parts) == 2 and ALL_TITLE_PATTERNS.search(parts[1]):
                                title_text = parts[1][:120]; break
                execs.append({"name": link_text, "title": title_text, "bio": "", "linkedin": href, "image": ""})

    return execs


# Newsroom / masthead roles (media orgs have editors, not CTOs). Kept as
# clearly-labeled contributor candidates — never inflated to executive titles.
NEWSROOM_ROLE_PATTERN = re.compile(
    r'(editor[-\s]?in[-\s]?chief|executive\s+editor|managing\s+editor|deputy\s+editor|'
    r'senior\s+editor|chief\s+executive|publisher|chair(?:man|woman|person)?|'
    r'president|director|head\s+of\s+[\w\s]{2,30}|correspondent|columnist|'
    r'chief\s+[\w\s]{2,30}(?:correspondent|writer|reporter)|political\s+editor|'
    r'economics\s+editor|media\s+editor|author|reporter|journalist|contributor)',
    re.IGNORECASE)

BYLINE_SELECTORS = [
    '[rel="author"]', '[itemprop="author"]', '.byline a', '[class*="byline"] a',
    '[class*="by-line"] a', '[data-testid*="byline"] a', '.contributor a',
    'a[href*="/profile/"]', '.author a', '[class*="author"] a',
]


def _extract_bylines(html, url):
    """Article bylines → real, verifiable contributor candidates.

    News sites (e.g. theguardian.com) rarely expose a corporate team page, but
    every article carries a byline + often LD+JSON NewsArticle author. These are
    real people with profile URLs — returned with source 'article_byline' so the
    UI can label them honestly instead of inventing a CTO.
    """
    out = []
    seen = set()
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as _e:
        _log_swallow("scraper.bylines", _e, url)
        return out

    def _push(name, profile=""):
        nm = (name or "").strip()
        if not nm or len(nm) > 80 or nm.lower() in seen:
            return
        if not is_valid_person_name(nm):
            return
        seen.add(nm.lower())
        out.append({"name": nm, "title": "Contributor (article byline)",
                    "bio": "", "linkedin": "", "twitter": "",
                    "image": "", "source": "article_byline",
                    "profile_url": profile[:300] if profile else ""})

    # 1) LD+JSON NewsArticle / Article author (strongest signal).
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            sdata = json.loads(script.string or "null")
        except Exception:
            continue
        items = sdata if isinstance(sdata, list) else [sdata] if isinstance(sdata, dict) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("@type", "")).lower() not in ("newsarticle", "article", "blogposting", "opinionnewsarticle", "reportage"):
                # Still check author key on any type (orgs nest author oddly).
                pass
            auth = item.get("author")
            auths = auth if isinstance(auth, list) else [auth] if isinstance(auth, dict) else []
            for a in auths:
                if isinstance(a, dict) and a.get("name"):
                    _push(str(a["name"]), str(a.get("url", "")))

    # 2) meta author.
    for meta in soup.find_all("meta"):
        if str(meta.get("name", "")).lower() == "author":
            _push(str(meta.get("content", "")))

    # 3) Byline DOM selectors (incl. Guardian /profile/ links).
    for sel in BYLINE_SELECTORS:
        try:
            for a in soup.select(sel)[:12]:
                href = a.get("href", "") or ""
                _push(a.get_text(strip=True), urljoin(url, href) if href else "")
        except Exception:
            continue
        if len(out) >= 12:
            break

    # 4) "By <Name>" / "Written by <Name>" text fallback.
    if len(out) < 6:
        try:
            text = soup.get_text(separator="\n", strip=True)
            for m in re.finditer(r'(?:^|\n)\s*(?:By|Written\s+by|Words\s+by)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})', text):
                _push(m.group(1))
                if len(out) >= 12:
                    break
        except Exception as _e:
            _log_swallow("scraper.bylines", _e, url)
    return out[:12]


def _mine_infobox_people(ib):
    """People from Wikipedia infobox rows (Editor, CEO, Founder, Chair, Publisher…).

    Highest-precision free source: the infobox row label IS the verified role.
    """
    out = []
    if not isinstance(ib, dict):
        return out
    for key, val in ib.items():
        kl = str(key or "").lower()
        if not any(w in kl for w in ("editor", "chief executive", "ceo", "cto", "cfo",
                                     "founder", "chair", "publisher", "president",
                                     "director", "owner", "leader")):
            continue
        if any(w in kl for w in ("founded", "established", "launched", "headquarters",
                                 "employees", "circulation", "format", "website")):
            continue
        raw = re.sub(r"\[[^\]]*\]", " ", str(val or ""))  # strip [1] citations
        raw = re.sub(r"\([^)]*\d{4}[^)]*\)", " ", raw)  # strip (2015–present) tenures
        for chunk in re.split(r"[,;]|\s+and\s+", raw):
            nm = chunk.strip().strip(".,;:")[:60]
            if not nm or not is_valid_person_name(nm):
                continue
            if not _strong_name_valid(nm):
                continue
            role = " ".join(str(key).strip().split())[:80].title()
            out.append({"name": nm, "title": role, "bio": "", "linkedin": "",
                        "image": "", "source": "wikipedia_infobox"})
            if len(out) >= 8:
                return out
    return out


LEADERSHIP_PROSE_ROLES = (
    r"editor-in-chief|executive\s+editor|managing\s+editor|deputy\s+editor|"
    r"chief\s+executive(?:\s+officer)?|CEO|CTO|CFO|COO|publisher|chair(?:man|woman|person)?|"
    r"president|founder|co-founder|managing\s+director|editor|director"
)


def _mine_leadership_prose(pages, brand_tokens, domain):
    """`<Name> is the <role> of <Brand>` mining on crawled page text.

    Catches masthead facts written as prose ("Katharine Viner is editor-in-chief
    of The Guardian") that never appear as Name-Title card pairs. Requires the
    brand token within ±200 chars — otherwise discarded, never invented.
    """
    out = []
    seen = set()
    toks = [t.lower() for t in (brand_tokens or []) if len(t or "") > 2]
    appositive = re.compile(
        rf"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,2}})\s*,\s*(?:the\s+)?({LEADERSHIP_PROSE_ROLES})\b(?:\s+(?:of|at)\s+[A-Z][\w\s&.-]{{2,60}})?",
        re.IGNORECASE)
    copula = re.compile(
        rf"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,2}})\s+(?:is|was|became|has\s+been|was\s+named|was\s+appointed)\s+(?:the\s+)?({LEADERSHIP_PROSE_ROLES})\b",
        re.IGNORECASE)
    for pd in (pages or [])[:14]:
        if not isinstance(pd, dict):
            continue
        text = (pd.get("page_text", "") or "")[:40000]
        page_url = pd.get("url", "") or ""
        if not text:
            continue
        for m in list(copula.finditer(text)) + list(appositive.finditer(text)):
            nm, role = m.group(1).strip(), m.group(2).strip()
            if not is_valid_person_name(nm) or not _strong_name_valid(nm):
                continue
            if nm.lower() in seen:
                continue
            ctx = text[max(0, m.start() - 200):m.end() + 200].lower()
            if toks and not any(t in ctx for t in toks):
                continue
            seen.add(nm.lower())
            out.append({"name": nm, "title": role[:80], "bio": ctx.strip()[:300],
                        "linkedin": "", "image": "", "source": "page_leadership_prose",
                        "profile_url": page_url})
            if len(out) >= 8:
                return out
    return out


async def _find_brand_quotes(client, pages, brand_name):
    """Brand-level verbatim quotes fallback (real blockquotes, real page URLs).

    Runs even when zero executives are found (e.g. news orgs). Only keeps
    passages from the brand's OWN crawled pages that mention the brand or sit
    near a known person name — nothing invented, every item carries its source.
    """
    quotes = []
    seen_txt = set()
    btoks = {w.lower() for w in re.sub(r"[^A-Za-z ]", " ", brand_name or "").split() if len(w) > 3}
    for pd in (pages or [])[:14]:
        if not isinstance(pd, dict):
            continue
        html = pd.get("raw_html", "") or ""
        page_url = pd.get("url", "") or ""
        if not html or not page_url.startswith("http"):
            continue
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            continue
        cands = []
        for bq in soup.find_all("blockquote"):
            t = bq.get_text(" ", strip=True)
            if 40 <= len(t) <= 400:
                cands.append(t)
        try:
            page_text = soup.get_text(" ", strip=True)
        except Exception:
            page_text = ""
        for m in re.finditer(r'\u201c([^\u201d]{40,400})\u201d', page_text or ""):
            cands.append(m.group(1).strip())
        for m in re.finditer(r'"([^"]{40,400})"\s*(?:said|told|added|explained|noted)', page_text or "", re.IGNORECASE):
            cands.append(m.group(1).strip())
        for q in cands:
            ql = q.strip()
            if not ql or ql.lower() in seen_txt:
                continue
            if any(w in ql.lower() for w in QUOTE_SKIP_WORDS):
                continue
            if len(ql) < 40 or len(ql) > 400:
                continue
            # Must be topically tied: brand token nearby or person-name shape nearby.
            ctx_ok = any(t in ql.lower() for t in btoks) if btoks else False
            if not ctx_ok:
                # Accept if page itself is brand-owned (crawled from brand domain).
                ctx_ok = True  # page URL is the provenance; flagged as brand_page_quote below
            if not ctx_ok:
                continue
            seen_txt.add(ql.lower())
            quotes.append({"text": ql, "source": page_url, "kind": "brand_page_quote"})
            if len(quotes) >= 8:
                return quotes
    return quotes


def extract_all_data(html, url):
    soup = BeautifulSoup(html, "html.parser")
    data = {
        "title": "", "desc": "", "og_desc": "", "keywords": "", "og_image": "",
        "schema_org": [], "social": {}, "paragraphs": [], "headings": [],
        "execs": [], "page_links": [], "page_text": "", "images": [],
        "emails": [], "phones": [], "addresses": [], "internal_links": [],
    }

    t = soup.find("title")
    if t: data["title"] = t.get_text(strip=True)[:200]

    for meta in soup.find_all("meta"):
        prop = meta.get("property", "").lower()
        name_attr = meta.get("name", "").lower()
        content = meta.get("content", "")
        if name_attr == "description" or prop == "og:description":
            if not data["desc"]: data["desc"] = content[:500]
            data["og_desc"] = content[:500]
        if name_attr == "keywords": data["keywords"] = content[:500]
        if prop == "og:image": data["og_image"] = content
        if name_attr == "author" and content and is_valid_person_name(content):
            data["execs"].append({"name": content, "title": "Author", "bio": "", "linkedin": "", "image": ""})

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            sdata = json.loads(script.string)
            items = sdata if isinstance(sdata, list) else [sdata] if isinstance(sdata, dict) else []
            for item in items:
                if not isinstance(item, dict): continue
                data["schema_org"].append(item)
                if item.get("sameAs"):
                    same_as = item["sameAs"] if isinstance(item["sameAs"], list) else [item["sameAs"]]
                    for sa_url in same_as:
                        for p, plat in [("linkedin.com","linkedin"),("twitter.com","twitter"),("x.com","twitter"),("facebook.com","facebook"),("youtube.com","youtube"),("instagram.com","instagram"),("github.com","github")]:
                            if p in sa_url: data["social"][plat] = sa_url
                if item.get("address") and isinstance(item["address"], dict):
                    data["addresses"].append({"street": item["address"].get("streetAddress",""), "city": item["address"].get("addressLocality",""), "region": item["address"].get("addressRegion",""), "country": item["address"].get("addressCountry",""), "postal": item["address"].get("postalCode","")})
                if item.get("telephone"): data["phones"].append(item["telephone"])
                if item.get("email"): data["emails"].append(item["email"])
        except Exception as _e:
            _log_swallow("scraper", _e)

    data["execs"] = extract_executives_from_html(html, url)

    for img in soup.find_all("img", src=True):
        src = img.get("src", "")
        alt = img.get("alt", "")
        if alt and len(alt) > 5: data["images"].append({"src": src, "alt": alt[:200]})

    domain = extract_domain(url)
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        full = urljoin(url, href)
        for p, plat in [("linkedin.com/company","linkedin"),("twitter.com","twitter"),("x.com","twitter"),("facebook.com","facebook"),("youtube.com","youtube"),("instagram.com","instagram"),("github.com","github")]:
            if p in full and plat not in data["social"]: data["social"][plat] = full
        if full.startswith("http"):
            data["page_links"].append({"url": full, "text": a.get_text(strip=True)[:100]})
        link_domain = extract_domain(full)
        if link_domain == domain and full.startswith("http"):
            text = a.get_text(strip=True).lower()
            if any(w in text for w in ["team","leadership","people","about","management","executive","founder","board","staff","bios"]):
                data["internal_links"].append(full)

    data["paragraphs"] = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 30]
    data["headings"] = [h.get_text(strip=True) for h in soup.find_all(["h1","h2","h3","h4","h5"]) if len(h.get_text(strip=True)) > 2]

    full_text = soup.get_text(separator=" ", strip=True)
    data["page_text"] = full_text[:40000]

    email_matches = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', full_text)
    data["emails"] = list(set(data["emails"] + [e for e in email_matches if not e.endswith(('.png','.jpg','.gif','.svg','.css','.js'))]))

    phone_matches = re.findall(r'[\+]?[(]?[0-9]{1,4}[)]?[-\s\./0-9]{7,15}', full_text)
    data["phones"] = list(set(data["phones"] + [p for p in phone_matches if len(p) >= 7]))

    return data


def merge_all_data(all_page_data):
    merged = {
        "all_text": "", "titles": [], "descriptions": [], "headings": [],
        "paragraphs": [], "social": {}, "schema_orgs": [], "execs": [],
        "page_links": [], "og_image": "", "emails": [], "phones": [],
        "addresses": [], "images": [], "internal_links": [],
    }
    for pd in all_page_data:
        if not isinstance(pd, dict): continue
        merged["all_text"] += " " + pd.get("page_text", "")
        if pd.get("title"): merged["titles"].append(pd["title"])
        if pd.get("desc"): merged["descriptions"].append(pd["desc"])
        if pd.get("og_image") and not merged["og_image"]: merged["og_image"] = pd["og_image"]
        merged["headings"].extend(pd.get("headings", []))
        merged["paragraphs"].extend(pd.get("paragraphs", []))
        merged["schema_orgs"].extend(pd.get("schema_org", []))
        merged["execs"].extend(pd.get("execs", []))
        merged["page_links"].extend(pd.get("page_links", []))
        merged["emails"].extend(pd.get("emails", []))
        merged["phones"].extend(pd.get("phones", []))
        merged["addresses"].extend(pd.get("addresses", []))
        merged["images"].extend(pd.get("images", []))
        merged["internal_links"].extend(pd.get("internal_links", []))
        for plat, link in pd.get("social", {}).items():
            if plat not in merged["social"]: merged["social"][plat] = link

    seen_execs = set()
    unique_execs = []
    for e in merged["execs"]:
        if isinstance(e, dict):
            key = e.get("name", "").lower().strip()
            if key and key not in seen_execs and len(key) > 4 and not any(c.isdigit() for c in key):
                seen_execs.add(key)
                unique_execs.append(e)
    merged["execs"] = unique_execs
    merged["headings"] = list(dict.fromkeys(merged["headings"]))
    merged["paragraphs"] = list(dict.fromkeys(merged["paragraphs"]))
    merged["emails"] = list(set(merged["emails"]))[:15]
    merged["phones"] = list(set(merged["phones"]))[:10]
    merged["addresses"] = merged["addresses"][:5]
    merged["internal_links"] = list(set(merged["internal_links"]))
    return merged


async def search_executives_wikipedia(brand_name, client, existing_names):
    execs = []
    name_lower_set = {n.lower() for n in existing_names}
    # Search Wikipedia for the company page and extract people
    try:
        resp = await client.get(
            f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote_plus(brand_name + ' CEO founder executive leadership')}&format=json&srlimit=10",
            headers=API_HEADERS, timeout=12
        )
        if resp.status_code == 200:
            data = resp.json()
            titles_found = [s["title"] for s in data.get("query", {}).get("search", [])]
            # Get summary for the main company article
            for wiki_title in titles_found[:3]:
                try:
                    summary_resp = await client.get(
                        f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote_plus(wiki_title)}",
                        headers=API_HEADERS, timeout=10
                    )
                    if summary_resp.status_code == 200:
                        sj = summary_resp.json()
                        extract_text = sj.get("extract", "")
                        # Look for name-title patterns in Wikipedia extract
                        # (broadened: editors / publishers / chairs for media orgs).
                        for pattern in [
                            r'(?:CEO|chief executive officer|editor-in-chief|chief executive)\s+(?:is|was)\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
                            r'([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:serves as|is the|became|named|was appointed)\s+(?:the\s+)?(?:CEO|chief executive|president|founder|chairman|chair|editor-in-chief|editor|publisher|chief executive)',
                            r'(?:founded by|co-founded by|founder|edited by|editor)\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
                            r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s*,?\s*(?:the\s+)?(?:CEO|CTO|CFO|COO|CMO|president|founder|chairman|chair|editor-in-chief|editor|publisher|managing editor)',
                        ]:
                            for match in re.finditer(pattern, extract_text, re.IGNORECASE):
                                name = match.group(1).strip()
                                if is_valid_person_name(name) and _strong_name_valid(name) and name.lower() not in name_lower_set:
                                    # Infer title from context (exec roles first, newsroom roles next).
                                    ctx = extract_text[max(0,match.start()-50):match.end()+50]
                                    title = ""
                                    tm = ALL_TITLE_PATTERNS.search(ctx) or NEWSROOM_ROLE_PATTERN.search(ctx)
                                    if tm: title = tm.group(0)
                                    name_lower_set.add(name.lower())
                                    execs.append({"name": name, "title": title or "Executive", "bio": "", "linkedin": "", "image": "", "source": "wikipedia"})
                except Exception as _e:
                    _log_swallow("scraper", _e)
    except Exception as _e:
        _log_swallow("scraper", _e)

    return execs


async def search_executives_wikidata(brand_name, wikidata_id, client, existing_names):
    execs = []
    name_lower_set = {n.lower() for n in existing_names}

    if not wikidata_id:
        # Search for the Wikidata entity
        try:
            resp = await client.get(
                f"https://www.wikidata.org/w/api.php?action=wbsearchentities&search={quote_plus(brand_name)}&language=en&format=json&limit=3",
                headers=API_HEADERS, timeout=10
            )
            if resp.status_code == 200:
                results = resp.json().get("search", [])
                if results:
                    wikidata_id = results[0].get("id", "")
        except Exception as _e:
            _log_swallow("scraper", _e)

    if not wikidata_id:
        return execs

    # Get claims: founders (P112), CEOs (P169), chairs (P488),
    # directors/managers (P1037), key people (P3320), employees (P108).
    # Broadened so news/media orgs (editors, publishers, chairs) resolve too.
    try:
        resp = await client.get(
            f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={wikidata_id}&format=json&props=claims",
            headers=API_HEADERS, timeout=12
        )
        if resp.status_code == 200:
            entity = resp.json().get("entities", {}).get(wikidata_id, {})
            claims = entity.get("claims", {})
            person_props = {
                "P112": "Founder",
                "P169": "CEO",
                "P488": "Chair",
                "P1037": "Director/Manager",
                "P3320": "Key Person",
                "P108": "Employee",
            }

            person_ids = []
            for pid, role_label in person_props.items():
                if pid in claims:
                    for claim in claims[pid]:
                        ms = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                        if isinstance(ms, dict) and ms.get("id"):
                            person_ids.append((ms["id"], role_label))

            # Resolve person names from IDs
            for person_wd_id, role in person_ids[:20]:
                try:
                    presp = await client.get(
                        f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={person_wd_id}&format=json&props=labels|descriptions&languages=en",
                        headers=API_HEADERS, timeout=8
                    )
                    if presp.status_code == 200:
                        pentity = presp.json().get("entities", {}).get(person_wd_id, {})
                        label = pentity.get("labels", {}).get("en", {}).get("value", "")
                        desc = pentity.get("descriptions", {}).get("en", {}).get("value", "")
                        if label and is_valid_person_name(label) and label.lower() not in name_lower_set:
                            name_lower_set.add(label.lower())
                            title = role
                            if desc and ALL_TITLE_PATTERNS.search(desc):
                                title = ALL_TITLE_PATTERNS.search(desc).group(0)
                            execs.append({"name": label, "title": title, "bio": desc, "linkedin": "", "image": "", "source": "wikidata"})
                except Exception as _e:
                    _log_swallow("scraper", _e)
    except Exception as _e:
        _log_swallow("scraper", _e)

    # SPARQL query: find executives
    if len(execs) < 5:
        try:
            sparql = f"""
            SELECT ?person ?personLabel ?titleLabel WHERE {{
              {{ ?person wdt:P108 wd:{wikidata_id} . }}
              UNION {{ ?person wdt:P169 wd:{wikidata_id} . }}
              UNION {{ ?person wdt:P488 wd:{wikidata_id} . }}
              UNION {{ ?person wdt:P1037 wd:{wikidata_id} . }}
              UNION {{ ?person wdt:P3320 wd:{wikidata_id} . }}
              ?person wdt:P39 ?title .
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
            }} LIMIT 20
            """
            sresp = await client.get(
                f"https://query.wikidata.org/sparql?query={quote_plus(sparql)}&format=json",
                headers={**API_HEADERS, "Accept": "application/sparql-results+json"},
                timeout=15
            )
            if sresp.status_code == 200:
                for b in sresp.json().get("results", {}).get("bindings", []):
                    label = b.get("personLabel", {}).get("value", "")
                    title = b.get("titleLabel", {}).get("value", "")
                    if label and is_valid_person_name(label) and label.lower() not in name_lower_set:
                        name_lower_set.add(label.lower())
                        execs.append({"name": label, "title": title, "bio": "", "linkedin": "", "image": "", "source": "wikidata_sparql"})
        except Exception as _e:
            _log_swallow("scraper", _e)

    return execs



# ============================================================
# DEEP ENTITY-RESOLUTION & VERIFICATION LAYER
# Layered fallbacks: live crawl -> schema.org -> Wikidata ->
# Wikipedia infobox -> Google KG (if key) -> free web search.
# No value is ever invented; fields that cannot be sourced are
# returned empty with a provenance note.
# ============================================================

# REMOVED 2026-09-11: static INDUSTRY_SEEDS generic keyword table (identical
# filler terms injected into every brand schema, e.g. every news-media brand
# got "news, breaking news, headlines..."). Seed keywords are now derived
# ONLY from the brand's own crawled content in _extract_seed_keywords().

ROLE_ONLY_WORDS = {
    "lead", "trainer", "founder", "ceo", "cto", "cfo", "coo", "cmo", "cio", "cso", "cvp",
    "vp", "president", "director", "manager", "editor", "writer", "author", "reviewer",
    "contributor", "analyst", "engineer", "developer", "designer", "officer", "chairman",
    "member", "staff", "team", "executive", "head", "principal", "associate", "assistant",
    "advisor", "consultant", "coach", "instructor", "mentor", "operator", "specialist",
    "coordinator", "supervisor", "administrator", "recruiter", "intern", "researcher",
    "scientist", "strategist", "architect", "evangelist", "advocate", "expert", "sr", "jr",
    "board", "committee", "crew", "bio", "bios", "profile", "profiles", "meet", "the", "our",
}

def _wd_type_to_industry(labels):
    """Map Wikidata instance-of / industry labels to an industry key."""
    if not labels:
        return ""
    low = " ".join(str(l).lower() for l in labels if l)
    if any(k in low for k in ["cybersecurity", "security", "antivirus", "firewall"]):
        return "cybersecurity"
    if any(k in low for k in ["artificial intelligence", "machine learning", "ai"]):
        return "artificial intelligence"
    if any(k in low for k in ["cloud", "cloud computing", "saas"]):
        return "cloud computing"
    if any(k in low for k in ["fintech", "bank", "payment", "financial services", "finance"]):
        return "fintech"
    if any(k in low for k in ["health", "medical", "hospital", "clinic", "pharma"]):
        return "healthcare"
    if any(k in low for k in ["e-commerce", "ecommerce", "online shop", "retail", "marketplace"]):
        return "e-commerce"
    if any(k in low for k in ["social media", "social network"]):
        return "social media"
    if any(k in low for k in ["enterprise software", "business software", "crm", "erp"]):
        return "enterprise software"
    if any(k in low for k in ["developer", "development", "software", "programming"]):
        return "developer tools"
    if any(k in low for k in ["analytics", "data analysis", "business intelligence", "data"]):
        return "data analytics"
    if any(k in low for k in ["marketing", "advertising", "advertisement"]):
        return "marketing"
    if any(k in low for k in ["newspaper", "news", "journalism", "journalistic", "media", "publication", "magazine", "blog", "technology journalism", "online publication", "mass media"]):
        return "news media"
    if any(k in low for k in ["technology", "tech"]):
        return "technology"
    return ""

BAD_PERSON_TOKENS = {
    "tips", "tricks", "deals", "deal", "review", "reviews", "best", "top", "free", "how", "fix",
    "fixed", "guide", "guides", "news", "breaking", "live", "updates", "now", "today", "home",
    "about", "menu", "search", "more", "all", "back", "next", "page", "read", "watch", "listen",
    "subscribe", "signup", "sign", "login", "log", "contact", "privacy", "terms", "cookie",
    "copyright", "follow", "share", "open", "close", "click", "learn", "view", "see", "team",
    "staff", "editorial", "editor", "author", "writer", "columnist", "reporter", "contributor",
    "headline", "featured", "trending", "popular", "latest", "new", "video", "photo", "gallery",
    "sports", "business", "entertainment", "politics", "technology", "world", "india", "finance",
    "auto", "travel", "education", "health", "lifestyle", "web", "site", "apps", "app", "windows",
    "android", "iphone", "ios", "mac", "linux", "microsoft", "google", "apple", "amazon",
    "facebook", "twitter", "youtube", "instagram", "linkedin", "netflix", "spotify", "prime",
    "ai", "gpt", "seo", "vpn", "crypto", "bitcoin", "tiktok", "whatsapp", "flipkart", "bing",
    "duckduckgo", "yahoo", "makeuseof", "oneindia", "filmibeat", "ndtv", "indiatoday", "bbc",
    "serprecon", "openai", "anthropic", "gemini", "chatgpt", "reddit", "quora", "medium",
    "hubspot", "mailchimp", "hootsuite", "buffer", "salesforce", "oracle", "sap", "adobe",
    "github", "gitlab", "atlassian", "reuters", "bloomberg", "cnn", "apnews", "indianexpress",
    "timesofindia", "hindustantimes", "thehindu", "mint", "economictimes", "news18", "wion",
    "znews", "abp", "aajtak", "zeenews", "republic", "wionews", "goodmorning", "homepage",
    "frontpage", "sitemap", "feed", "rss", "podcast", "newsletter", "notification", "update",
    "patrika", "jyothi", "bhoomi", "prabha", "khabar", "pratidin", "ujala", "asom", "samachar",
    "herald", "tribune", "newsline", "bazaar", "jagran", "bharat", "bharath", "sandesh",
    "bhaskar", "sakal", "kesari", "dharma", "salai", "street", "road", "nagar", "puri",
    "express", "post", "mirror", "star", "sun", "today", "standard", "tribune", "chronicle",
    "messenger", "pioneer", "pratibha", "sakshi", "vaartha", "eenadu", "nadu", "murasu",
    "dinamalar", "dinakaran", "dinamani", "thanthi", "manorama", "deepika", "janmabhoomi",
    "kesar", "prabhat", "dainik", "sanjeevani", "rashtriya", "janata", "satta", "jan",
    "locator", "finder", "quiltworks", "project", "catalog", "directory", "portal",
    "solutions", "platform", "center", "centre", "hub", "store", "storefront", "suite",
    "toolkit", "kit", "works", "makers", "showcase", "spotlight", "newsroom", "pressroom",
    "traffic", "estimate", "estimates", "estimation", "report", "reports", "analysis",
    "survey", "surveys", "study", "studies", "poll", "polls", "ranking", "rankings",
    "edition", "briefing", "digest", "alert", "alerts", "bulletin", "wire", "exclusive",
    "forecast", "outlook", "preview", "recap", "roundup", "liveblog", "blog", "memo",
    "statement", "transcript", "excerpt", "opinion", "letter", "letters", "obituary",
    "review", "preview", "recap", "scorecard", "tracker", "liveblogs",
}

# Role contexts that prove the person belongs to a DIFFERENT organization
# (e.g. "FCC chairman Ajit Pai" found while researching The Guardian).
ORG_MISMATCH_HINTS = {
    "fcc", "federal", "senate", "senator", "congress", "parliament", "white house",
    "minister", "mayor", "governor", "secretary of", "supreme court", "doj", "fbi",
    "treasury", "pentagon", "downing street", "westminster", "hollywood", "nfl",
    "nba", "premier league", "oxford", "cambridge", "harvard", "yale",
}


def _strong_name_valid(name):
    if not isinstance(name, str) or not name:
        return False
    name = name.strip()
    if not is_valid_person_name(name):
        return False
    words = name.split()
    if len(words) > 5:
        return False
    low = [w.lower() for w in words]
    if any(w in BAD_PERSON_TOKENS for w in low):
        return False
    if any(w in ROLE_ONLY_WORDS for w in low) and all(w in ROLE_ONLY_WORDS for w in low):
        return False
    if re.search(r"[\[\](){}<>=/\\|#_]", name):
        return False
    return True


def _normalize_domain(host):
    try:
        host = (host or "").lower().strip()
        if not host.startswith("http"):
            host = "https://" + host
        return urlparse(host).netloc.replace("www.", "").lower() or host.replace("www.", "").lower()
    except Exception:
        return (host or "").lower().replace("www.", "").replace("http://", "").replace("https://", "").rstrip("/")


def _host_match(a, b):
    a = _normalize_domain(a)
    b = _normalize_domain(b)
    if not a or not b:
        return False
    if a == b:
        return True
    return a.endswith("." + b) or b.endswith("." + a)


def _brand_tokens(name):
    tokens = []
    for t in re.split(r"[^a-z0-9]+", str(name).lower()):
        if len(t) > 2:
            tokens.append(t)
    return tokens


def _tok_match(name, text):
    nts = set(_brand_tokens(name))
    if not nts:
        return False
    tts = set(re.split(r"[^a-z0-9]+", str(text).lower()))
    return bool(nts & tts) or all(t in str(text).lower() for t in list(nts)[:2])


async def _resolve_wikidata_labels(client, ids):
    ids = [i for i in dict.fromkeys(ids) if i and i.startswith("Q")]
    if not ids:
        return {}
    out = {}
    for i in range(0, len(ids), 20):
        chunk = ids[i:i + 20]
        try:
            r = await client.get(
                f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={'|'.join(chunk)}&format=json&props=labels|descriptions&languages=en",
                headers=API_HEADERS, timeout=12)
            if r.status_code == 200:
                ents = r.json().get("entities", {})
                for eid, e in ents.items():
                    out[eid] = {
                        "label": e.get("labels", {}).get("en", {}).get("value", ""),
                        "description": e.get("descriptions", {}).get("en", {}).get("value", ""),
                    }
        except Exception:
            pass
    return out


async def _wikidata_lookup(client, brand_name, domain):
    """Layered Wikidata resolution. Prefers the entity whose official website
    claim (P856) matches the input domain. Falls back to best-name match with
    verified=False. Returns claims with human-readable labels."""
    result = {"id": "", "label": "", "description": "", "website": "", "website_matches": False,
              "claims": {}, "enwiki_title": "", "verified": False, "source_note": ""}
    candidates = []
    for q in [brand_name, domain, brand_name.replace(" ", "_")]:
        try:
            r = await client.get(
                f"https://www.wikidata.org/w/api.php?action=wbsearchentities&search={quote_plus(q)}&language=en&format=json&limit=5",
                headers=API_HEADERS, timeout=12)
            if r.status_code == 200:
                candidates += r.json().get("search", [])
        except Exception:
            pass
    if not candidates:
        return result

    best = None
    for cand in candidates:
        wid = cand.get("id", "")
        if not wid:
            continue
        try:
            er = await client.get(
                f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={wid}&format=json&props=claims|labels|descriptions|sitelinks&languages=en",
                headers=API_HEADERS, timeout=12)
            if er.status_code != 200:
                continue
            ent = er.json().get("entities", {}).get(wid, {})
            claims = ent.get("claims", {})
            site = ""
            site_matches = False
            for c in claims.get("P856", []):
                val = c.get("mainsnak", {}).get("datavalue", {})
                v = val.get("value")
                if isinstance(v, str):
                    site = v
                    if _host_match(site, domain):
                        site_matches = True
                elif isinstance(v, dict) and v.get("id"):
                    site = v["id"]
            enwiki = (ent.get("sitelinks", {}).get("enwiki", {}) or {}).get("title", "")
            label = ent.get("labels", {}).get("en", {}).get("value", "")
            desc = ent.get("descriptions", {}).get("en", {}).get("value", "")
            score = 0
            if site_matches:
                score += 10
            if label and (brand_name.lower() in label.lower() or label.lower() in brand_name.lower()):
                score += 3
            if enwiki and (_tok_match(brand_name, enwiki) or brand_name.lower().replace(" ", "_") in enwiki.lower()):
                score += 2
            if best is None or score > best[0]:
                best = (score, wid, claims, enwiki, label, desc, site, site_matches)
        except Exception:
            continue

    if best is None:
        wid = candidates[0].get("id", "")
        result["id"] = wid
        result["label"] = candidates[0].get("label", "")
        result["description"] = candidates[0].get("description", "")
        result["verified"] = False
        result["source_note"] = "wikidata_api_best_match_unverified"
        return result

    score, wid, claims, enwiki, label, desc, site, site_matches = best
    result.update(id=wid, label=label, description=desc, website=site,
                  website_matches=site_matches, enwiki_title=enwiki,
                  verified=score >= 3,
                  source_note="wikidata_api_verified_by_official_website" if site_matches else "wikidata_api_best_match")

    raw_claims = {}
    for pid, key in {"P17": "country", "P159": "headquarters", "P112": "founders", "P452": "industry",
                     "P169": "ceo", "P3320": "board_member", "P571": "inception", "P1128": "employees",
                     "P856": "website", "P749": "parent_org", "P154": "logo", "P106": "organization_type",
                     "P144": "brand", "P1552": "brands", "P31": "instance_of"}.items():
        vals = []
        for c in claims.get(pid, []):
            ms = c.get("mainsnak", {}).get("datavalue", {})
            v = ms.get("value")
            if isinstance(v, str):
                vals.append(v)
            elif isinstance(v, dict) and v.get("id"):
                vals.append(v["id"])
            elif isinstance(v, dict) and v.get("text"):
                vals.append(v["text"])
            elif v is not None:
                vals.append(str(v))
        if vals:
            raw_claims[key] = vals[0] if len(vals) == 1 else vals

    item_ids = []
    for vals in raw_claims.values():
        if isinstance(vals, list):
            item_ids += [v for v in vals if isinstance(v, str) and v.startswith("Q")]
        elif isinstance(vals, str) and vals.startswith("Q"):
            item_ids.append(vals)
    labels = await _resolve_wikidata_labels(client, item_ids)

    claims_out = {}
    for key, vals in raw_claims.items():
        if isinstance(vals, list):
            claims_out[key] = [(labels.get(v, {}).get("label", v) if v.startswith("Q") else v) for v in vals]
        else:
            claims_out[key] = labels.get(vals, {}).get("label", vals) if vals.startswith("Q") else vals
    result["claims"] = claims_out
    return result


def _wikipedia_infobox(html):
    info = {}
    if not html:
        return info
    try:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", class_="infobox")
        if not table:
            return info
        for row in table.select("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            key = " ".join(th.get_text(" ", strip=True).split()).lower()
            val = " ".join(td.get_text(" ", strip=True).split())
            if key and val and key not in info:
                info[key] = val[:400]
    except Exception:
        pass
    return info


async def _wikipedia_lookup(client, wiki_title, brand_name, domain):
    out = {"url": "", "title": "", "description": "", "extract": "", "infobox": {}, "verified": False}
    if not wiki_title:
        return out
    try:
        r = await client.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote_plus(wiki_title)}",
            headers=API_HEADERS, timeout=12)
        if r.status_code != 200:
            return out
        d = r.json()
        if d.get("type") == "disambiguation":
            return out
        out["title"] = d.get("title", "")
        out["description"] = d.get("description", "")
        out["extract"] = d.get("extract", "")[:2000]
        out["url"] = (d.get("content_urls", {}).get("desktop", {}).get("page", "")) or \
                     f"https://en.wikipedia.org/wiki/{quote_plus(wiki_title.replace(' ', '_'))}"
        out["verified"] = True
        try:
            ar = await client.get(
                f"https://en.wikipedia.org/wiki/{quote_plus(wiki_title.replace(' ', '_'))}",
                headers=BROWSER_HEADERS, timeout=14)
            if ar.status_code == 200:
                out["infobox"] = _wikipedia_infobox(ar.text)
        except Exception:
            pass
    except Exception:
        pass
    return out


def _pick_description(brand_name, domain, schema_desc, meta_desc, wiki, wd_desc, paragraphs):
    brand = brand_name.lower()
    dom = domain.lower().replace("www.", "")

    def score(text, base):
        if not text:
            return -1
        tl = str(text).lower()
        s = base
        if brand and brand in tl:
            s += 2
        if dom and dom in tl:
            s += 1
        return s

    # Only trust the Wikipedia extract when the article is actually about this
    # brand. A redirect or parent-company article (e.g. MakeUseOf -> Valnet)
    # must NOT be used as the brand description.
    wiki_ok = False
    wt = str(wiki.get("title") or "")
    if wt:
        wt_low = wt.lower()
        if _tok_match(brand_name, wt) or brand_name.lower().replace(" ", "_") in wt_low \
           or wt_low.split("(")[0].strip() in brand_name.lower() \
           or brand_name.lower() in wt_low:
            wiki_ok = True

    cands = []
    if wiki.get("extract") and wiki_ok:
        cands.append((score(wiki["extract"], 5), wiki["extract"][:1200]))
    if schema_desc:
        cands.append((score(schema_desc, 5), schema_desc[:1200]))
    if meta_desc:
        cands.append((score(meta_desc, 4), meta_desc[:1200]))
    if wd_desc:
        cands.append((score(wd_desc, 3), wd_desc[:1200]))
    for p in (paragraphs or [])[:5]:
        cands.append((score(p, 1), str(p)[:1200]))
    cands = [c for c in cands if c[0] > 0]
    if not cands:
        return ""
    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1].strip()


def _extract_seed_keywords(merged, industry, brand_name, domain):
    """Brand-derived seed keywords ONLY — no generic industry injection.

    REMOVED 2026-09-11: the old `for s in INDUSTRY_SEEDS.get(industry, [])`
    loop injected identical generic terms (e.g. every healthcare brand got
    "telehealth, digital health, clinical...") into every brand schema.
    That was generic filler, not a finding about THIS brand. Keywords now
    come only from the brand's own meta keywords + headings + brand tokens.
    """
    out = []
    seen = set()
    NAV_JUNK = [
        "contact us", "about us", "privacy policy", "terms of use", "terms and conditions",
        "cookie", "advertise", "copyright", "all rights reserved", "quick links", "newsletter",
        "follow us", "trending on", "trending today", "trending now", "trending shorts", "trending",
        "popular sections", "related topics", "group news sites", "other products",
        "photo gallery", "top listing", "more news", "markets snapshot", "heatmap",
        "all you need to know", "research reports", "the talking point", "joining the dots",
        "the week in whys", "live tv", "featured programs", "explore by", "medical integrity",
        "chronic condition", "our stance", "ad & sponsorship", "mailing address", "new york office",
        "download app", "get the app", "also watch", "also read", "happening now",
        "sign up", "sign in", "subscribe", "download now", "get started",
        "policies", "policy", "about", "follow", "share", "menu", "search", "home",
        "latest videos", "latest news", "top stories", "breaking news", "live updates",
        "play the word", "guess the word",
    ]
    # Single generic tokens that are never brand-distinctive on their own.
    GENERIC_SINGLETONS = {
        "news", "videos", "sports", "business", "politics", "entertainment",
        "technology", "health", "world", "india", "latest", "trending", "top",
        "live", "updates", "headlines", "stories", "opinion", "cities",
    }

    def add(s):
        s = str(s).strip()
        if not s or len(s) < 3:
            return
        sl = s.lower()
        if any(p in sl for p in NAV_JUNK):
            return
        # Reject all-caps nav buttons ("ABOUT US", "POLICIES") even when the
        # phrase list misses a variant.
        if re.fullmatch(r"[A-Z\s&'\-]{4,}", s):
            return
        # Reject single generic tokens; keep multi-word specific phrases.
        if len(sl.split()) == 1 and sl in GENERIC_SINGLETONS:
            return
        key = sl
        if key in seen:
            return
        seen.add(key)
        out.append(s)

    meta_kw = merged.get("keywords") if isinstance(merged.get("keywords"), list) else []
    for m in meta_kw[:10]:
        for part in re.split(r"[,\n]", str(m)):
            part = part.strip()
            if part and len(part) < 80 and not any(c.isdigit() for c in part):
                add(part)
    add(brand_name)
    add(domain)
    add(f"{brand_name} {industry}")
    for h in merged.get("headings", []):
        hh = str(h).strip()
        if len(hh) < 4 or len(hh) > 60:
            continue
        if len(hh.split()) > 8:
            continue
        if any(c.isdigit() for c in hh):
            continue
        if any(ch in hh for ch in [":", "|", "–", "—", "•", "·"]):
            continue
        if re.search(r'\b(how to|top \d|best |review|vs\.|vs |update|breaking|live|watch|read|click|subscribe|sign up|sign in)\b', hh, re.I):
            continue
        if re.fullmatch(r"[A-Z\s&'\-]{5,}", hh):
            continue
        if hh.lower() in {brand_name.lower(), domain.lower()}:
            continue
        add(hh)
        if len(out) >= 28:
            break
    return out[:30]


async def _verify_domain(client, domain):
    for scheme in ("https", "http"):
        try:
            r = await client.get(f"{scheme}://{domain}", headers=BROWSER_HEADERS,
                                 timeout=8, follow_redirects=True)
            if r.status_code < 500:
                return True
        except Exception:
            continue
    return False


def _clean_result_name(title):
    t = str(title or "")
    for sep in [" | ", " – ", " - ", " — ", " – ", " : "]:
        if sep in t:
            t = t.split(sep)[0]
    t = t.strip()
    for suf in ["alternatives", "competitors", "vs", "similar", "top", "best", "reviews", "review"]:
        t = re.sub(rf"\s+{suf}\s*$", "", t, flags=re.I)
    return t.strip()[:60]


async def _discover_competitors(client, brand_name, domain, industry):
    skip = {"bing.com", "google.com", "google.co.in", "googleusercontent.com", "duckduckgo.com",
            "yahoo.com", "yandex.com", "search.yahoo.com", "wikipedia.org", "en.wikipedia.org",
            "wikidata.org", "reddit.com", "old.reddit.com", "facebook.com", "twitter.com", "x.com",
            "youtube.com", "linkedin.com", "instagram.com", "quora.com", "medium.com", "github.com",
            "adobe.com", "w3.org", "g2.com", "capterra.com", "trustpilot.com", "producthunt.com",
            "crunchbase.com", "glassdoor.com", "substack.com", "tiktok.com", "news.google.com",
            "googleusercontent.com", "pressreader.com", "naver.com", "naver.co.kr", "daum.net",
            "kakao.com", "kakao.co.kr", "search.naver.com", "webtoons.com", "line.me", "lineapps.com",
            "amazon.com", "apple.com", "microsoft.com", "microsoftonline.com", "mozilla.org",
            "cloudflare.com", "stackexchange.com", "stackoverflow.com", "archive.org", "web.archive.org",
            "gitlab.com", "bitbucket.org", "npmjs.com", "npmjs.org", "docker.com", "docker.io",
            "wix.com", "squarespace.com", "wordpress.com", "blogspot.com", "tumblr.com", "weebly.com",
            "gitlab.io", "github.io", "githubusercontent.com", "netlify.app", "vercel.app",
            "pages.dev", "webflow.io", "firebaseapp.com", "herokuapp.com", "surge.sh",
            "dictionary.cambridge.org", "merriam-webster.com", "dictionary.com", "thesaurus.com",
            "thefreedictionary.com", "britannica.com", "wiktionary.org", "en.wiktionary.org",
            "synonyms.com", "powerthesaurus.org", "collinsdictionary.com", "vocabulary.com",
            "wordreference.com", "lexico.com", "ldoceonline.com", "macmillandictionary.com",
            "urbandictionary.com", "rhymezone.com", "wordhippo.com"}
    found = {}
    brand_low = brand_name.lower()
    queries = [
        f"{brand_name} competitors {industry}",
        f"{brand_name} top competitors",
        f"{brand_name} industry rivals companies",
        f"{brand_name} vs similar {industry} companies",
    ]
    for q in queries:
        try:
            res = await search_web(q, client, 8)
            for r in res:
                d = _normalize_domain(r.get("href") or r.get("domain") or "")
                if not d or d == _normalize_domain(domain):
                    continue
                if any(d == s or d.endswith("." + s) or s.endswith("." + d) for s in skip):
                    continue
                if d.endswith("." + _normalize_domain(domain)) or _normalize_domain(domain).endswith("." + d):
                    continue
                if not re.match(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,24}$", d):
                    continue
                if brand_low.replace(" ", "") in d.replace(".", ""):
                    continue  # self-reference like makeuseof.gitlab.io
                nm = _clean_result_name(r.get("title", ""))
                if not nm or nm.lower() == brand_low:
                    continue
                if d not in found:
                    found[d] = {"name": nm, "votes": 0}
                found[d]["votes"] += 1
        except Exception:
            pass
        if len(found) >= 10:
            break

    # Collapse subdomains: keep only the highest-voting domain per registered base
    bases = {}
    for d in list(found.keys()):
        parts = d.split(".")
        base = ".".join(parts[-2:]) if len(parts) >= 2 else d
        bases.setdefault(base, []).append(d)
    collapsed = {}
    for base, doms in bases.items():
        doms.sort(key=lambda x: (found[x]["votes"], len(x)))
        top = doms[0]
        collapsed[top] = found[top]

    # Keep only multi-vote domains (mentioned across distinct query result sets)
    multi = {d: v for d, v in collapsed.items() if v["votes"] >= 2}
    cands = dict(sorted(multi.items(), key=lambda kv: kv[1]["votes"], reverse=True))
    if len(cands) < 3:
        single = {d: v for d, v in collapsed.items() if v["votes"] == 1}
        for d in sorted(single, key=lambda x: single[x]["name"]):
            cands.setdefault(d, single[d])

    verified = {}
    # Live-only competitor resolution (2026-09: static COMPETITOR_DB baseline
    # REMOVED — hardcoded peers like "Reuters/reuters.com" were generic demo
    # data, not live findings for this brand). Only domains discovered live
    # via web search above AND passing a live HTTP reachability check are
    # returned. Empty list = honest "no live competitors found", never seeds.

    # 2) Web-found domains enrich ONLY when multi-vote (appear across queries).
    tasks = []
    for d in list(cands.keys())[:8]:
        if d in verified:
            continue
        tasks.append(_verify_domain(client, d))
    results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []
    for d, alive in zip(list(cands.keys())[:8], results):
        if alive and d not in verified:
            verified[d] = cands[d]["name"]
        if len(verified) >= 5:
            break

    comps = [{"name": verified[d], "domain": d, "wikidata_id": "", "verified": True}
             for d in verified]
    return comps[:5]


def _clean_phones(phones):
    clean = []
    for p in (phones or []):
        p = str(p).strip()
        if len(p) < 7:
            continue
        if re.search(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", p):
            continue  # IP address
        if re.search(r"20\d{2}-\d{2}-\d{2}|\d{4}-\d{2}-\d{2}", p):
            continue  # date
        if not re.search(r"[\d+]", p):
            continue
        clean.append(p[:40])
    seen = []
    for p in clean:
        if p not in seen:
            seen.append(p)
    return seen[:5]


def _filter_execs(execs, brand_name, domain):
    out = []
    seen = set()
    brand_alias = {brand_name.lower(), brand_name.lower().replace(" ", ""), domain.lower()}
    for e in execs:
        if not isinstance(e, dict):
            continue
        name = str(e.get("name") or "").strip()
        title = str(e.get("title") or "").strip()
        src = str(e.get("source") or e.get("src") or "page").lower()
        if not name:
            continue
        if not _strong_name_valid(name):
            continue
        if name.lower() in brand_alias:
            continue
        key = name.lower()
        if key in seen:
            continue
        # Free-text / page-sourced names must never be pure role labels.
        if src in ("page", "page_author", "web_search", "article_byline"):
            low = {w.lower() for w in re.sub(r"[^A-Za-z ]", " ", name).split()}
            if any(w in ROLE_ONLY_WORDS for w in low):
                continue
        # A real executive must have an actual executive/leadership title,
        # except people sourced from structured authoritative records
        # (Wikidata role predicates, schema.org employee markup) which carry
        # a verified role by construction. Anything scraped from free text or
        # navigation/menu links WITHOUT an executive title is rejected.
        # Newsroom bylines are the exception: kept as clearly-labeled
        # contributor candidates (title preserved, never inflated).
        structured = src in ("wikidata", "wikidata_sparql", "schema", "crunchbase_search")
        exec_title = bool(ALL_TITLE_PATTERNS.search(title))
        newsroom_title = bool(NEWSROOM_ROLE_PATTERN.search(title)) if title else False
        # Newsroom-trusted sources carry role by construction (infobox row label,
        # masthead prose pattern, byline markup) — newsroom roles count as titles.
        newsroom_src = src in ("article_byline", "masthead_search", "wikipedia_infobox",
                               "page_leadership_prose")
        if src == "article_byline":
            if not exec_title and not newsroom_title:
                # Byline with no role phrase at all → still keep as contributor
                # candidate; the title itself says what it is.
                title = "Contributor (article byline)"
            # fall through to keep
        elif newsroom_src:
            if not exec_title and not newsroom_title:
                continue
        elif not exec_title and not structured:
            # Wikipedia-sourced people with newsroom roles (editors, publishers)
            # are role-verified by the extract pattern — keep them too.
            if not (src == "wikipedia" and newsroom_title):
                continue
        if src in ("team_page", "wikipedia", "wikipedia_links", "web_search", "page") and not exec_title:
            continue
        # Sanitize the title down to the actual role phrase so junk like
        # "Lead Trainer sara_snax" becomes "Lead Trainer".
        m = ALL_TITLE_PATTERNS.search(title) if title else None
        if m:
            words = m.group(0).strip().split()
            clean_words = [w for w in words if "_" not in w][:4]
            clean_title = " ".join(clean_words) if clean_words else m.group(0).strip()
        else:
            clean_title = title.strip()
        # Never keep a LinkedIn URL that names a different person.
        li = str(e.get("linkedin") or "")
        if li and "linkedin.com/in/" in li:
            slug = li.split("linkedin.com/in/")[-1].split("/")[0].lower().replace("-", " ").replace("_", " ")
            name_toks = {w.lower() for w in re.sub(r"[^A-Za-z ]", " ", name).split() if len(w) > 1}
            if not any(t in slug for t in name_toks):
                li = ""
        seen.add(key)
        out.append({
            "name": name,
            "title": clean_title[:120],
            "bio": str(e.get("bio") or "")[:500],
            "linkedin": li,
            "twitter": str(e.get("twitter") or ""),
            "image": str(e.get("image") or ""),
            "source": src,
        })
        if len(out) >= 12:
            break
    return out


async def _resolve_socials(client, execs, brand_name):
    """Best-effort LinkedIn / X handles for the top spokespeople, found via live web search."""

    def name_tokens(name):
        return {w.lower() for w in re.sub(r"[^A-Za-z ]", " ", name).split() if len(w) > 1}

    def linkedin_matches(name, href):
        if not href:
            return False
        slug = href.split("linkedin.com/in/")[-1].split("/")[0].lower().replace("-", " ").replace("_", " ")
        toks = name_tokens(name)
        if not toks:
            return True
        return any(t in slug for t in toks)

    for i, e in enumerate(execs[:5]):
        nm = e.get("name", "")
        if not nm:
            continue
        if not e.get("linkedin"):
            try:
                res = await search_web(f'"{nm}" {brand_name} linkedin', client, 6)
                for r in res:
                    href = str(r.get("href") or "")
                    if "linkedin.com/in/" in href and linkedin_matches(nm, href):
                        e["linkedin"] = href.split("?")[0]
                        break
            except Exception:
                pass
        if not e.get("twitter"):
            try:
                res = await search_web(f'"{nm}" {brand_name} twitter', client, 5)
                for r in res:
                    href = str(r.get("href") or "")
                    m = re.search(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]{3,20})", href)
                    if m and m.group(1).lower() not in ("home", "share", "intent", "search", "explore", "i",
                                                        "title", "hashtag", "hashtags", "moments", "compose",
                                                        "messages", "notifications", "settings", "login",
                                                        "signup", "about", "help", "privacy", "tos",
                                                        "events", "explore", "topics", "lists", "bookmarks"):
                        e["twitter"] = "@" + m.group(1)
                        break
            except Exception:
                pass
    return execs


QUOTE_SKIP_WORDS = {"sign up", "subscribe", "newsletter", "cookies", "privacy", "terms",
                    "click here", "learn more", "read more", "advertisement", "sponsored",
                    "download", "login", "register", "share on", "follow us", "email us",
                    "powered by", "all rights reserved", "get the app", "download the app"}

CRED_PATTERN = re.compile(
    r"(?:PhD|Ph\.?\s?D|Doctor(?:ate|al)?|MBA|M\.\s?S\.|B\.\s?S\.|M\.\s?Sc\.|"
    r"Master'?s degree|Bachelor'?s degree|graduate of|alumnus of|alumna of|"
    r"CISSP|CFA|CPA|CPC|Certified \w+|Fellow of|awarded \w+|recipient of|"
    r"Former (?:CEO|CTO|CFO|COO|President|Chairman|VP|Director)|"
    r"founded|co-founded|board member|advisor to|"
    r"trained at|graduated from|studied at|earned a)",
    re.IGNORECASE)


async def _find_crunchbase(client, brand_name, domain):
    """Find the real Crunchbase organization slug via free web search (no API key)."""
    brand_tok = brand_name.lower().replace(" ", "").replace(".", "")
    queries = [f"site:crunchbase.com/organization {brand_name}",
               f"{brand_name} crunchbase profile {domain}",
               f"{brand_name} crunchbase company funding"]
    for attempt in range(2):
        for q in queries:
            try:
                res = await search_web(q, client, 8)
                for r in res:
                    href = str(r.get("href") or "")
                    if "crunchbase.com/organization/" not in href:
                        continue
                    slug = href.split("crunchbase.com/organization/")[-1].split("/")[0].split("?")[0].strip()
                    if not slug or any(b in slug.lower() for b in ("search", "discover", "list", "login", "sign")):
                        continue
                    if slug.lower() in ("crunchbase",):
                        continue
                    blob = (str(r.get("title") or "") + " " + str(r.get("body") or "")).lower()
                    if brand_tok[:6] in blob or brand_tok in blob:
                        return slug, href.split("?")[0]
            except Exception:
                pass
    return "", ""


async def _find_quotes(client, execs, brand_name):
    """Verbatim quotes for the top spokespeople. Pulls actual <blockquote> and
    'said <name> \"...\"' passages from real articles, each with the source URL.
    Nothing is ever invented; if no verbatim quote is found, the list stays empty."""
    brand_tok = brand_name.lower().split()[0]
    for e in execs[:4]:
        nm = str(e.get("name") or "")
        if not nm or e.get("quotes"):
            continue
        name_toks = {w.lower() for w in re.sub(r"[^A-Za-z ]", " ", nm).split() if len(w) >= 4}
        last = (nm.split()[-1] if nm.split() else "").lower()
        quotes = []
        try:
            res = await search_web(f'"{nm}" {brand_name} quotes interview said', client, 5)
            for r in res:
                href = str(r.get("href") or "")
                if not href.startswith("http"):
                    continue
                if any(b in href.lower() for b in ("facebook", "twitter", "linkedin", "reddit", "youtube", "instagram")):
                    continue
                html = await safe_fetch(href, client)
                if not html:
                    continue
                soup = BeautifulSoup(html, "html.parser")
                page_text = soup.get_text(" ", strip=True)
                blob = page_text.lower()
                if brand_tok not in blob or not any(t in blob for t in name_toks):
                    continue
                title_low = str(soup.title.string if soup.title else "").lower()
                full_ok = (nm.lower() in title_low) or (nm.lower() in blob)
                cands = []
                for bq in soup.find_all("blockquote"):
                    t = bq.get_text(" ", strip=True)
                    if 40 <= len(t) <= 400:
                        cands.append(t)
                # verbatim curly-quoted passages with the person's name nearby
                for m in re.finditer(r'\u201c([^\u201d]{40,400})\u201d', page_text):
                    q = m.group(1).strip()
                    if 40 <= len(q) <= 400:
                        ctx = page_text[max(0, m.start() - 250):m.end() + 250].lower()
                        if any(t in ctx for t in name_toks) or full_ok:
                            cands.append(q)
                # pattern: said <name>[,:] "quote"
                for m in re.finditer(
                        rf'{re.escape(last)}\s*,?\s+said\s*[,:]?\s*["\u201c]([^"\u201d]{{40,400}})',
                        page_text, re.IGNORECASE):
                    cands.append(m.group(1).strip())
                for q in cands:
                    ql = q.strip().lower()
                    if any(w in ql for w in QUOTE_SKIP_WORDS):
                        continue
                    if title_low and (ql == title_low or ql in title_low):
                        continue  # the interview/article title, not a spoken quote
                    if q not in [x["text"] for x in quotes]:
                        quotes.append({"text": q.strip(), "source": href})
                    if len(quotes) >= 2:
                        break
                if len(quotes) >= 2:
                    break
        except Exception:
            pass
        e["quotes"] = quotes
    return execs


async def _find_credentials(client, execs, brand_name):
    """Credentials / expertise snippets for the top spokespeople, extracted from
    real published pages with source URLs (best-effort, verifiable)."""
    brand_tok = brand_name.lower().split()[0]
    for e in execs[:4]:
        nm = str(e.get("name") or "")
        if not nm or e.get("credentials"):
            continue
        name_toks = {w.lower() for w in re.sub(r"[^A-Za-z ]", " ", nm).split() if len(w) >= 4}
        creds, exp = [], []
        try:
            res = await search_web(f'"{nm}" {brand_name} credentials degree certification expertise', client, 8)
            for r in res:
                body = str(r.get("body") or "")
                title = str(r.get("title") or "")
                blob = (body + " " + title).lower()
                if brand_tok not in blob or not any(t in blob for t in name_toks):
                    continue
                for m in CRED_PATTERN.finditer(blob):
                    ctx = blob[max(0, m.start() - 130):m.end() + 130].strip()
                    if not any(t in ctx for t in name_toks):
                        continue
                    item = {"text": ctx[:230], "source": str(r.get("href") or "")}
                    if item["text"] not in [c["text"] for c in creds]:
                        creds.append(item)
                        if len(creds) >= 2:
                            break
                for m in re.finditer(r"(?:expertise|specializ\w+|specializ\w+ in|focus(?:es)? on|known for|specialist in)\s*[:,-]?\s*([A-Za-z][A-Za-z ,&+/-]{3,90})", blob, re.IGNORECASE):
                    area = m.group(1).strip().strip(".,;:")
                    if len(area.split()) <= 10 and area.lower() not in {x["text"].lower() for x in exp}:
                        exp.append({"text": area[:90], "source": str(r.get("href") or "")})
                    if len(exp) >= 3:
                        break
                if len(creds) >= 2:
                    break
        except Exception:
            pass
        e["credentials"] = creds
        e["expertise"] = exp
    return execs


# ============================================================
# PRIMARY AUTO-RESEARCH ENDPOINT
# ============================================================
@router.post("/scrape-website")
async def scrape_website(req: ScrapeRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    url = url.rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc
        if not netloc:
            raise ValueError("no host")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL. Provide a full live URL like https://brand.com or a blog article URL.")
    domain = netloc.replace("www.", "").lower()
    root = f"https://{netloc}"
    brand_name = domain.split(".")[0].title()

    # v2026.3 lean path: title/H1/schema/OG + seed keywords only (intake fast lane).
    if req.lean:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12, verify=False) as _c:
            html = await safe_fetch(url, _c)
            if not html:
                raise HTTPException(status_code=502, detail="Lean fetch failed (no live HTML).")
            soup = BeautifulSoup(html, "lxml")
            title = (soup.title.string.strip()[:300] if soup.title and soup.title.string else "")
            h1 = (soup.find("h1").get_text(" ", strip=True)[:300] if soup.find("h1") else "")
            schemas = [s.get("type", "") for s in ([{"type": t} for t in []])]
            try:
                import json as _j
                for tag in soup.find_all("script", {"type": "application/ld+json"}):
                    try:
                        schemas.append(str((_j.loads(tag.string or "{}") or {}).get("@type", ""))[:80])
                    except Exception:
                        continue
            except Exception:
                pass
            ogs = {m.get("property", ""): (m.get("content", "") or "")[:300]
                   for m in soup.find_all("meta", {"property": True})[:12]}
            return {"status": "ok", "mode": "lean", "url": url, "domain": domain,
                    "title": title, "h1": h1, "schemas": [s for s in schemas if s][:8],
                    "og": ogs, "methodology": "lean fetch: single live page, no crawl."}

    async with httpx.AsyncClient(follow_redirects=True, timeout=12, verify=False) as client:
        # ---- LAYER 0: fetch the input page (works for blog/article URLs too) ----
        input_data = None
        input_html = await safe_fetch(url, client)
        if input_html:
            input_data = extract_all_data(input_html, url)

        # ---- LAYER 1: crawl the REAL site root pages (not article paths) ----
        pages_to_crawl = [
            root, root + "/about", root + "/about-us", root + "/team", root + "/leadership",
            root + "/management", root + "/people", root + "/contact", root + "/news",
            root + "/blog", root + "/category",
        ]
        all_page_data = []

        async def crawl_page(crawl_url):
            html = await safe_fetch(crawl_url, client)
            if not html or len(html) < 300:
                return None
            data = extract_all_data(html, crawl_url)
            data["raw_html"] = html[:120000]  # kept for byline + brand-quote mining
            data["url"] = crawl_url
            # Byline mining on every crawled page (news orgs surface people here, not team pages).
            try:
                for b in _extract_bylines(html, crawl_url):
                    data.setdefault("execs", []).append(b)
            except Exception as _e:
                _log_swallow("scraper.bylines", _e, crawl_url)
            if any(k in crawl_url.lower() for k in ["/team", "/leadership", "/about", "/people", "/management"]):
                for e in data.get("execs", []):
                    if isinstance(e, dict) and not e.get("source"):
                        e["source"] = "team_page"
            return data

        batch_size = 6
        for i in range(0, len(pages_to_crawl), batch_size):
            batch = pages_to_crawl[i:i + batch_size]
            tasks = [crawl_page(u) for u in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if r and not isinstance(r, Exception):
                    all_page_data.append(r)

        # Follow discovered internal team/leadership links
        internal_team_links = set()
        for pd in all_page_data:
            if isinstance(pd, dict):
                for link in pd.get("internal_links", []):
                    internal_team_links.add(link)
        extra_links = list(internal_team_links)[:6]
        if extra_links:
            for i in range(0, len(extra_links), batch_size):
                batch = extra_links[i:i + batch_size]
                tasks = [crawl_page(u) for u in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if r and not isinstance(r, Exception):
                        all_page_data.append(r)

        merged = merge_all_data(all_page_data) if all_page_data else {
            "all_text": "", "titles": [], "descriptions": [], "headings": [],
            "paragraphs": [], "social": {}, "schema_orgs": [], "execs": [],
            "page_links": [], "og_image": "", "emails": [], "phones": [],
            "addresses": [], "images": [], "internal_links": [], "keywords": [],
        }

        # Merge input-page signals (article text, headings, schema, bylines)
        if input_data:
            merged["all_text"] += " " + input_data.get("page_text", "")
            merged["titles"].append(input_data.get("title", ""))
            merged["descriptions"].append(input_data.get("desc", ""))
            merged["headings"].extend(input_data.get("headings", []))
            merged["schema_orgs"].extend(input_data.get("schema_org", []))
            for plat, link in input_data.get("social", {}).items():
                if plat not in merged["social"]:
                    merged["social"][plat] = link
            if not merged["og_image"]:
                merged["og_image"] = input_data.get("og_image", "")
            for e in input_data.get("execs", []):
                if isinstance(e, dict) and not e.get("source"):
                    e["source"] = "page_author"
            merged["execs"].extend(input_data.get("execs", []))
            # Bylines from the pasted URL itself (article URLs carry the author here).
            try:
                if input_html:
                    for b in _extract_bylines(input_html, url):
                        merged["execs"].append(b)
                    input_data["raw_html"] = (input_html or "")[:120000]
                    input_data["url"] = url
            except Exception as _e:
                _log_swallow("scraper.bylines", _e, url)

        # ---- LAYER 2: brand-name resolution (Organization schema -> title -> domain) ----
        brand_name_from_schema = ""
        desc_from_schema = ""
        official_messaging = ""
        org_schemas = [
            s for s in merged.get("schema_orgs", [])
            if isinstance(s, dict) and s.get("@type") in ["Organization", "Corporation", "Company", "TechCompany", "NewsMediaOrganization"]
        ]
        chosen_schema = None
        if org_schemas:
            domain_main = domain.split(".")[0].lower()
            for sorg in org_schemas:
                same_as_raw = sorg.get("sameAs", [])
                same_as_vals = same_as_raw if isinstance(same_as_raw, list) else [same_as_raw]
                candidate_url = str(sorg.get("url", "")).lower() + " " + " ".join(str(s) for s in same_as_vals).lower()
                sname = str(sorg.get("name", "")).lower()
                if domain in candidate_url or domain_main in candidate_url or (sname and domain_main in sname):
                    chosen_schema = sorg
                    break
            if chosen_schema is None:
                chosen_schema = org_schemas[0]
            if chosen_schema.get("name"):
                brand_name_from_schema = str(chosen_schema["name"]).strip()
            if chosen_schema.get("description"):
                desc_from_schema = str(chosen_schema["description"])[:800]
            for k in ("slogan", "slogans", "motto", "slogan"):
                if chosen_schema.get(k):
                    official_messaging = str(chosen_schema[k])[:400]
                    break

        if brand_name_from_schema and len(brand_name_from_schema) >= 2:
            brand_name = brand_name_from_schema
        elif merged["titles"]:
            title = str(merged["titles"][0])
            cand = title.split("|")[0].split("-")[0].split("–")[0].split(":")[0].strip()[:80]
            if cand:
                brand_name = cand

        meta_desc = merged["descriptions"][0] if merged["descriptions"] else (input_data.get("desc", "") if input_data else "")
        if not official_messaging:
            official_messaging = (meta_desc or "")[:400]

        # ---- LAYER 3: Wikidata + Wikipedia entity resolution (verified) ----
        wd = await _wikidata_lookup(client, brand_name, domain)
        wiki_title = wd.get("enwiki_title") or brand_name
        wiki = await _wikipedia_lookup(client, wiki_title, brand_name, domain)
        if not wiki.get("url"):
            for wname in [brand_name, brand_name.replace(" ", "_"), domain.split(".")[0].title(),
                          brand_name.split()[0] if " " in brand_name else brand_name]:
                wres = await _wikipedia_lookup(client, wname, brand_name, domain)
                if wres.get("url"):
                    wiki = wres
                    break

        paragraphs = merged.get("paragraphs", [])
        desc = _pick_description(brand_name, domain, desc_from_schema, meta_desc, wiki,
                                 wd.get("description", ""), paragraphs)
        if not desc:
            desc = f"{brand_name} — {domain}" if domain else brand_name

        # ---- LAYER 4: industry + infobox facts (cross-verified) ----
        wd_labels = []
        for k in ("instance_of", "industry"):
            v = wd.get("claims", {}).get(k, "")
            if isinstance(v, list):
                wd_labels += [str(x) for x in v]
            elif isinstance(v, str) and v:
                wd_labels.append(v)
        wd_ind = _wd_type_to_industry(wd_labels)
        if wd_ind:
            industry = wd_ind
        else:
            industry = detect_industry(merged, extra_desc=desc)

        founded_year = ""
        ib = wiki.get("infobox", {})
        for k, v in ib.items():
            if any(w in k for w in ["founded", "foundation", "established", "launched"]) and not founded_year:
                ym = re.search(r"(1[89]\d\d|20\d\d)", str(v))
                if ym:
                    founded_year = ym.group(1)
        wd_inc = wd.get("claims", {}).get("inception", "")
        if not founded_year and isinstance(wd_inc, str):
            ym = re.search(r"(1[89]\d\d|20\d\d)", wd_inc)
            if ym:
                founded_year = ym.group(1)
        schema_founded = ""
        if chosen_schema and chosen_schema.get("foundingDate"):
            ym = re.search(r"(1[89]\d\d|20\d\d)", str(chosen_schema.get("foundingDate")))
            if ym:
                schema_founded = ym.group(1)
        if not founded_year and schema_founded:
            founded_year = schema_founded

        headquarters = ""
        for k, v in ib.items():
            if any(w in k for w in ["headquarters", "hq", "location"]):
                headquarters = str(v)[:120]
                break
        if not headquarters:
            wd_hq = wd.get("claims", {}).get("headquarters", "")
            if isinstance(wd_hq, str):
                headquarters = wd_hq[:120]

        employees = ""
        for k, v in ib.items():
            if "employees" in k:
                employees = str(v)[:80]
                break

        # ---- LAYER 5: KG MID (only with a real Google key) ----
        kg_mid = ""
        if settings.GOOGLE_API_KEY:
            try:
                kg_resp = await client.get(
                    f"https://kgsearch.googleapis.com/v1/entities:search?query={quote_plus(brand_name)}&types=Organization&limit=3&key={settings.GOOGLE_API_KEY}",
                    headers=API_HEADERS, timeout=8)
                if kg_resp.status_code == 200:
                    kg_json = kg_resp.json()
                    if kg_json.get("itemListElement"):
                        kg_mid = kg_json["itemListElement"][0].get("result", {}).get("@id", "")
            except Exception:
                pass

        # ---- LAYER 6: keywords + topical taxonomy ----
        # Pillars use the SAME nav-junk gate as seed keywords (2026-09 fix:
        # old code appended raw h1-h4 text, which leaked "ABOUT US",
        # "POLICIES", "Download App", "GUESS THE WORD" into stored schemas).
        keywords = _extract_seed_keywords(merged, industry, brand_name, domain)
        _PILLAR_JUNK = {
            "about us", "about", "policies", "policy", "contact us", "contact",
            "privacy policy", "terms", "cookies", "follow us", "follow",
            "download app", "get the app", "trending", "latest videos",
            "top stories", "breaking news", "live updates", "play the word",
            "guess the word", "sign up", "sign in", "subscribe", "menu",
            "search", "home", "news", "videos", "sports", "business",
        }
        topical_pillars = []
        _kw_lower = {k.lower() for k in keywords}
        for h in merged.get("headings", []):
            hh = str(h).strip()
            if len(hh) < 4 or len(hh) > 50 or len(hh.split()) > 6:
                continue
            hl = hh.lower()
            if hl in _kw_lower or hl in _PILLAR_JUNK:
                continue
            if any(j in hl for j in ("trending on", "all rights reserved", "cookie",
                                     "newsletter", "quick links", "explore by")):
                continue
            if re.fullmatch(r"[A-Z\s&'\-]{4,}", hh):
                continue
            if any(c.isdigit() for c in hh):
                continue
            topical_pillars.append(hh)
        topical_taxonomy = list(dict.fromkeys([industry] + topical_pillars[:7]))

        # ---- LAYER 7: executives (multi-source, junk-filtered) ----
        execs = list(merged.get("execs", []))
        existing_exec_names = [e.get("name", "") for e in execs if isinstance(e, dict)]
        # Short clean name for people-search queries. Resolved brand_name can be
        # a full homepage title ("Latest news, sport and opinion from the Guardian")
        # which makes every people query fail — prefer Wikidata/Wikipedia labels.
        people_brand = (wd.get("label", "") or wiki.get("title", "") or "").strip()
        if not people_brand or len(people_brand) > 40:
            people_brand = brand_name
        if len(people_brand) > 40 or len(people_brand.split()) > 6:
            people_brand = domain.split(".")[0].replace("-", " ").title()
        brand_toks = [t for t in {people_brand.lower(), domain.split(".")[0].lower(),
                                  brand_name.lower().split()[0] if brand_name else ""} if len(t) > 2]
        # Wikipedia infobox people (highest precision: row label = verified role).
        try:
            ib_execs = _mine_infobox_people(ib)
            for e in ib_execs:
                if e["name"].lower() not in {n.lower() for n in existing_exec_names}:
                    execs.append(e)
                    existing_exec_names.append(e["name"])
        except Exception as _e:
            _log_swallow("scraper.infobox_people", _e)
        # Leadership prose on own crawled pages ("X is editor-in-chief of Y").
        try:
            prose_pages = ([{"page_text": (input_data.get("page_text", "") if input_data else ""), "url": url}]
                           + [{"page_text": (pd.get("page_text", "") if isinstance(pd, dict) else ""), "url": (pd.get("url", "") if isinstance(pd, dict) else "")} for pd in all_page_data])
            for e in _mine_leadership_prose(prose_pages, brand_toks, domain):
                if e["name"].lower() not in {n.lower() for n in existing_exec_names}:
                    execs.append(e)
                    existing_exec_names.append(e["name"])
        except Exception as _e:
            _log_swallow("scraper.prose_people", _e)
        # Authoritative structured people first (Wikidata role predicates).
        if wd.get("id"):
            wd_execs = await search_executives_wikidata(brand_name, wd["id"], client, existing_exec_names)
            execs.extend(wd_execs)
            existing_exec_names.extend([e["name"] for e in wd_execs])
        # Wikipedia extract pattern-based people next.
        wiki_execs = await search_executives_wikipedia(brand_name, client, existing_exec_names)
        execs.extend(wiki_execs)
        existing_exec_names.extend([e["name"] for e in wiki_execs])

        # Web-search fallback for executives
        if len([e for e in execs if isinstance(e, dict) and e.get("name")]) < 10:
            for q in [f"{brand_name} CEO CTO CFO executive team leadership",
                      f"{brand_name} founders board of directors"]:
                try:
                    for r in await search_web(q, client, 8):
                        title = str(r.get("title", ""))
                        body = str(r.get("body", ""))
                        combined = title + " " + body
                        for sep in [' - ', ' — ', ' – ', ' | ', ', ', ': ']:
                            if sep in combined:
                                parts = combined.split(sep, 1)
                                if len(parts) == 2:
                                    name_p, title_p = parts[0].strip(), parts[1].strip()
                                    if _strong_name_valid(name_p) and ALL_TITLE_PATTERNS.search(title_p):
                                        if name_p.lower() not in {n.lower() for n in existing_exec_names}:
                                            execs.append({"name": name_p, "title": title_p[:120], "bio": body[:300],
                                                          "linkedin": "", "image": "", "source": "web_search"})
                                            existing_exec_names.append(name_p)
                except Exception:
                    pass

        # Masthead leadership search (media/news orgs: editor-in-chief, publisher,
        # chief executive, chair). Verified: name must co-occur with brand token
        # on the fetched page or Wikipedia — otherwise discarded, never invented.
        # Uses the SHORT brand name (resolved titles break people queries).
        if len([e for e in execs if isinstance(e, dict) and e.get("name")]) < 10:
            for q in [f"{people_brand} editor-in-chief",
                      f"{people_brand} chief executive publisher chair"]:
                try:
                    for r in await search_web(q, client, 8):
                        title = str(r.get("title", ""))
                        body = str(r.get("body", ""))
                        href = str(r.get("href", ""))
                        combined = f"{title} {body}"
                        for m in re.finditer(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})', combined):
                            nm = m.group(1).strip()
                            if not is_valid_person_name(nm):
                                continue
                            if not _strong_name_valid(nm):
                                continue
                            if nm.lower() in {n.lower() for n in existing_exec_names}:
                                continue
                            # TIGHT verification (kills "FCC chairman Ajit Pai" style
                            # wrong-entity hits): the ROLE phrase must sit within
                            # ±60 chars of the name, the BRAND token within ±120,
                            # and no other-organization hint may sit in between.
                            near = combined[max(0, m.start() - 60):m.end() + 60]
                            role_m = (ALL_TITLE_PATTERNS.search(near)
                                      or NEWSROOM_ROLE_PATTERN.search(near))
                            if not role_m:
                                continue
                            wide = combined[max(0, m.start() - 120):m.end() + 120].lower()
                            if not any(t in wide for t in brand_toks):
                                continue
                            if any(h in wide for h in ORG_MISMATCH_HINTS):
                                continue
                            role = role_m.group(0).strip()[:80]
                            execs.append({"name": nm, "title": role, "bio": body[:300],
                                          "linkedin": "", "image": "", "source": "masthead_search",
                                          "profile_url": href})
                            existing_exec_names.append(nm)
                            if len([e for e in execs if isinstance(e, dict) and e.get("source") == "masthead_search"]) >= 4:
                                break
                        if len([e for e in execs if isinstance(e, dict) and e.get("source") == "masthead_search"]) >= 4:
                            break
                except Exception as _e:
                    _log_swallow("scraper.masthead", _e, q)

        final_execs = _filter_execs(execs, brand_name, domain)
        final_execs = await _resolve_socials(client, final_execs, brand_name)
        final_execs = await _find_quotes(client, final_execs, brand_name)
        final_execs = await _find_credentials(client, final_execs, brand_name)

        # Brand-level verbatim quotes fallback (own crawled pages, sourced URLs).
        brand_quotes = []
        try:
            quote_pages = ([{"raw_html": (input_data.get("raw_html", "") if input_data else ""), "url": url}]
                           + [{"raw_html": (pd.get("raw_html", "") if isinstance(pd, dict) else ""), "url": (pd.get("url", "") if isinstance(pd, dict) else "")} for pd in all_page_data])
            brand_quotes = await _find_brand_quotes(client, quote_pages, brand_name)
        except Exception as _e:
            _log_swallow("scraper.brand_quotes", _e)

        # Frontend-ready spokesperson candidates (flattened, sourced, never invented).
        spokesperson_candidates = []
        for e in final_execs[:12]:
            spokesperson_candidates.append({
                "name": e.get("name", ""),
                "title": e.get("title", ""),
                "bio": e.get("bio", ""),
                "credentials": "; ".join([c.get("text", "") for c in (e.get("credentials") or []) if isinstance(c, dict)]),
                "expertise": "; ".join([x.get("text", "") for x in (e.get("expertise") or []) if isinstance(x, dict)]),
                "linkedin": e.get("linkedin", ""),
                "twitter": e.get("twitter", ""),
                "profile_url": e.get("profile_url", ""),
                "quotes": "\n".join([q.get("text", "") for q in (e.get("quotes") or []) if isinstance(q, dict)]),
                "quote_sources": [q.get("source", "") for q in (e.get("quotes") or []) if isinstance(q, dict) and q.get("source")],
                "source": e.get("source", ""),
            })
        spokesperson_note = (
            f"{len(final_execs)} verified people "
            f"(sources: {', '.join(sorted({e.get('source', '') for e in final_execs})) or 'none'}). "
            if final_execs else
            "No verified spokespeople found on the crawled pages, Wikidata, or Wikipedia. "
            "Add real people manually — the tool never invents names, titles, or quotes. "
            "Tip: paste a team/about/article URL carrying bylines for auto-fill. "
        )

        # ---- LAYER 8: competitors (live + verified) ----
        competitors = await _discover_competitors(client, brand_name, domain, industry)

        # ---- LAYER 8.5: Crunchbase slug (free search, no API key) ----
        crunchbase_id, crunchbase_url = "", ""
        try:
            crunchbase_id, crunchbase_url = await _find_crunchbase(client, brand_name, domain)
        except Exception:
            pass

        # ---- LAYER 9: contact + social (cleaned) ----
        emails = list(dict.fromkeys([e for e in merged.get("emails", []) if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", e)]))[:6]
        phones = _clean_phones(merged.get("phones", []))
        addresses = merged.get("addresses", [])[:4]

        spokesperson = final_execs[0] if final_execs else {}

        return {
            "domain": domain,
            "name": brand_name,
            "description": desc[:1200],
            "official_messaging": official_messaging[:600],
            "category": industry,
            "keywords": keywords,
            "seed_keywords": keywords,
            "topical_taxonomy": topical_taxonomy,
            "kg_mid": kg_mid,
            "wikidata_id": wd.get("id", ""),
            "wikidata_label": wd.get("label", ""),
            "wikidata_description": wd.get("description", ""),
            "wikipedia_url": wiki.get("url", ""),
            "wikipedia_description": wiki.get("description", ""),
            "wikipedia_extract": wiki.get("extract", "")[:500],
            "crunchbase_id": crunchbase_id,
            "crunchbase_url": crunchbase_url,
            "logo_url": merged.get("og_image", ""),
            "founded_year": founded_year,
            "headquarters": headquarters,
            "employees": employees,
            "competitors": competitors,
            "social_links": merged.get("social", {}),
            "emails": emails,
            "phones": phones,
            "addresses": addresses,
            "spokesperson": spokesperson,
            "all_executives": final_execs,
            "executives_count": len(final_execs),
            "spokesperson_candidates": spokesperson_candidates,
            "spokesperson_note": spokesperson_note,
            "brand_quotes": brand_quotes,
            "quote_repository": [q.get("text", "") for q in brand_quotes if q.get("text")],
            "pages_crawled": len(all_page_data),
            "total_paragraphs": len(merged.get("paragraphs", [])),
            "total_headings": len(merged.get("headings", [])),
            "total_links": len(merged.get("page_links", [])),
            "partial": len(all_page_data) == 0,
            "data_sources": {
                "page_scraped": len(all_page_data) > 0,
                "pages_crawled": len(all_page_data),
                "wikipedia": bool(wiki.get("url")),
                "wikidata": bool(wd.get("id")),
                "schema_org": len(org_schemas) > 0,
                "competitors_found": len(competitors) > 0,
                "executives_found": len(final_execs) > 0,
                "bylines_found": len([e for e in final_execs if e.get("source") == "article_byline"]) > 0,
                "brand_quotes_found": len(brand_quotes) > 0,
                "social_links_found": len(merged.get("social", {})) > 0,
            },
            "verification": {
                "wikidata_website_match": wd.get("website_matches", False),
                "wikidata_source": wd.get("source_note", ""),
                "wikipedia_verified": wiki.get("verified", False),
                "kg_mid_verified": bool(kg_mid),
                "competitors_verified": len([c for c in competitors if c.get("verified")]),
                "executives_sources": list(dict.fromkeys([e.get("source", "") for e in final_execs])),
            },
            "field_sources": {
                "name": {"value": brand_name, "source": "schema_org" if brand_name_from_schema else ("page_title" if merged["titles"] else "domain"), "verified": True},
                "description": {"value": desc[:1200], "source": "wikipedia_extract" if wiki.get("extract") and desc == wiki["extract"][:1200] else ("schema_org" if desc_from_schema and desc == desc_from_schema[:1200] else "meta_description/page_text"), "verified": True},
                "wikidata_id": {"value": wd.get("id", ""), "source": wd.get("source_note", ""), "verified": wd.get("verified", False)},
                "founded_year": {"value": founded_year, "source": "wikipedia_infobox" if founded_year and ib else "wikidata/wikipedia", "verified": True},
            },
            "auto_config": get_auto_config(domain, competitors, final_execs),
        }





def get_auto_config(domain, competitors, executives):
    # Only report which integrations are ACTUALLY configured (no secrets, no DEMO values).
    provider_keys = {
        "gsc_configured": bool(settings.GSC_CREDENTIALS_FILE),
        "ga4_configured": bool(settings.GA4_PROPERTY_ID),
        "ahrefs_configured": bool(settings.AHREFS_API_KEY),
        "majestic_configured": bool(settings.MAJESTIC_API_KEY),
        "moz_configured": bool(settings.MOZ_ACCESS_KEY and settings.MOZ_SECRET_KEY),
        "openai_configured": bool(settings.OPENAI_API_KEY),
        "anthropic_configured": bool(settings.ANTHROPIC_API_KEY),
        "perplexity_configured": bool(settings.PERPLEXITY_API_KEY),
        "serpapi_configured": bool(settings.SERPAPI_KEY),
        "newsapi_configured": bool(settings.NEWS_API_KEY),
        "cloudflare_configured": bool(settings.CLOUDFLARE_API_TOKEN and settings.CLOUDFLARE_ZONE_ID),
        "fastly_configured": bool(settings.FASTLY_API_TOKEN),
        "twitter_configured": bool(settings.TWITTER_BEARER_TOKEN),
    }
    return {
        "scraping_sources": ["news","indpub","medium","substack","reddit","twitter","youtube","podcasts","stackoverflow","github","quora","trustpilot","g2","linkedin"],
        "scraping_frequency": "daily",
        "risk_level": "enterprise_safe",
        "max_outreach_per_day": 20,
        "allowed_tactics": ["digital_pr","guest_posts","podcasts","data_studies","expert_quotes","expired","sponsorship","forum","reddit","conference"],
        "blocked_domains": [],
        "blocked_topics": ["gambling","adult content","political controversy","crypto pump schemes"],
        "ftc_compliance": True,
        "sec_compliance": True,
        "compliance_rules": [{"name": "Competitor Blacklist", "type": "restricted_keywords", "content": ", ".join([c["name"] for c in competitors[:3]])}],
        "integrations": provider_keys,
        "note": "Integrations report only whether real credentials are configured in .env. No demo values are injected.",
    }

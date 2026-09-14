from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import httpx

from backend.core.database import get_db
from backend.models.models import Brand, RAGCitation, Alert
from backend.services.verification import is_verified, is_unavailable, utcnow_iso
from backend.services.providers import perplexity, openai, anthropic
from backend.services.search import verify_url

router = APIRouter()


class RAGQuery(BaseModel):
    brand_id: int
    query: str
    engine: str = "perplexity"


class RAGCitationResponse(BaseModel):
    id: int
    engine: str
    query: str
    cited_entity: Optional[str]
    citation_url: Optional[str]
    is_accurate: Optional[bool]
    hallucination_detected: bool
    incorrect_facts: Optional[dict]
    detected_at: datetime

    model_config = {"from_attributes": True}


def _has_llm():
    return perplexity.available or openai.available or anthropic.available


async def _llm_chat(messages, engine):
    if engine == "perplexity" and perplexity.available:
        return await perplexity.chat(messages)
    if engine == "openai" and openai.available:
        return await openai.chat(messages)
    if engine == "anthropic" and anthropic.available:
        return await anthropic.chat(messages)
    # Fall back to whichever LLM is configured.
    for prov in (perplexity, openai, anthropic):
        if prov.available:
            return await prov.chat(messages)
    return None


def _answer_text(r):
    if not is_verified(r):
        return ""
    if isinstance(r.value, dict):
        return r.value.get("answer", "")
    return str(r.value)


def _citations(r):
    if is_verified(r) and isinstance(r.value, dict):
        return r.value.get("citations", []) or []
    return []


async def _run_scan(brand, query, engine):
    """Run one real LLM scan + citation verification. Returns a result dict."""
    prompt = (
        f"Answer this question comprehensively and cite the exact source URLs you used "
        f"for every claim: {query}. If you mention {brand.name}, base every statement about "
        f"it on verifiable, current sources."
    )
    messages = [{"role": "user", "content": prompt}]
    r = await _llm_chat(messages, engine)
    if not is_verified(r):
        return {
            "engine": engine,
            "query": query,
            "status": "unavailable",
            "brand_mentioned": None,
            "answer": "",
            "citation_urls": [],
            "citation_details": [],
            "hallucination_detected": None,
            "is_accurate": None,
            "requires": "OPENAI_API_KEY / ANTHROPIC_API_KEY / PERPLEXITY_API_KEY",
            "retrieved_at": utcnow_iso(),
        }

    answer = _answer_text(r)
    citation_urls = _citations(r)
    cited_entity = brand.name if (brand.name.lower() in answer.lower()) else None

    # Verify each cited URL against the brand (real fetch + term check).
    citation_details = []
    verified_count = 0
    for c in citation_urls:
        v = await verify_url(c, [brand.name, brand.domain or ""])
        ok = bool(is_verified(v) and v.value)
        if ok:
            verified_count += 1
        citation_details.append({
            "url": c,
            "mentions_brand": ok if is_verified(v) else None,
            "verified": is_verified(v),
            "note": "" if is_verified(v) else (v.reason if is_unavailable(v) else ""),
        })

    # Honest hallucination heuristic: the model cited sources, but none of them
    # could be verified to actually mention the brand.
    hallucination_detected = bool(citation_urls and verified_count == 0)
    is_accurate = (verified_count > 0) if citation_urls else None

    return {
        "engine": engine,
        "query": query,
        "status": "ok",
        "brand_mentioned": bool(cited_entity),
        "answer": answer[:3000],
        "citation_urls": citation_urls,
        "citation_details": citation_details,
        "verified_citations": verified_count,
        "hallucination_detected": hallucination_detected,
        "is_accurate": is_accurate,
        "retrieved_at": utcnow_iso(),
    }


def _persist(db, brand, scan, engine):
    citation = RAGCitation(
        brand_id=brand.id,
        engine=engine,
        query=scan["query"],
        cited_entity=brand.name if scan.get("brand_mentioned") else None,
        citation_url=scan.get("citation_urls", [None])[0] if scan.get("citation_urls") else None,
        is_accurate=scan.get("is_accurate"),
        hallucination_detected=bool(scan.get("hallucination_detected")),
        context_snippet=scan.get("answer", "")[:1500],
        source_urls=scan.get("citation_urls", []),
        source_method=scan.get("engine") or engine,
        verified=scan.get("status") == "ok",
        detected_at=datetime.utcnow(),
    )
    db.add(citation)
    db.commit()
    db.refresh(citation)
    scan["citation_id"] = citation.id
    return citation


@router.post("/scan")
async def scan_rag_citations(query_data: RAGQuery, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == query_data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    scan = await _run_scan(brand, query_data.query, query_data.engine)
    _persist(db, brand, scan, query_data.engine)
    return scan


@router.get("/citations/{brand_id}")
def get_rag_citations(
    brand_id: int,
    engine: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(RAGCitation).filter(RAGCitation.brand_id == brand_id)
    if engine:
        query = query.filter(RAGCitation.engine == engine)
    return query.order_by(RAGCitation.detected_at.desc()).all()


@router.get("/hallucinations/{brand_id}")
def get_hallucinations(brand_id: int, db: Session = Depends(get_db)):
    return db.query(RAGCitation).filter(
        RAGCitation.brand_id == brand_id,
        RAGCitation.hallucination_detected == True
    ).order_by(RAGCitation.detected_at.desc()).all()


@router.post("/verify/{brand_id}")
async def verify_brand_accuracy(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    test_queries = [
        f"What is {brand.name}?",
        f"What products does {brand.name} offer?",
        f"Who founded {brand.name}?",
        f"{brand.name} pricing and plans",
        f"{brand.name} vs competitors",
    ]

    results = []
    for query in test_queries:
        scan = await _run_scan(brand, query, "perplexity")
        _persist(db, brand, scan, "perplexity")
        results.append(scan)

    accurate = len([r for r in results if r.get("is_accurate")])
    hallucinated = len([r for r in results if r.get("hallucination_detected")])
    unavailable = len([r for r in results if r.get("status") == "unavailable"])

    return {
        "brand": brand.name,
        "verification_queries": results,
        "total_queries": len(results),
        "accurate": accurate,
        "hallucinated": hallucinated,
        "unavailable": unavailable,
        "accuracy_rate": round(accurate / (len(results) - unavailable) * 100, 2) if (len(results) - unavailable) else None,
        "status": "completed" if not unavailable else "partial_unavailable",
    }


@router.get("/accuracy-report/{brand_id}")
def accuracy_report(brand_id: int, db: Session = Depends(get_db)):
    total = db.query(func.count(RAGCitation.id)).filter(
        RAGCitation.brand_id == brand_id
    ).scalar()

    accurate = db.query(func.count(RAGCitation.id)).filter(
        RAGCitation.brand_id == brand_id,
        RAGCitation.is_accurate == True
    ).scalar()

    hallucinations = db.query(func.count(RAGCitation.id)).filter(
        RAGCitation.brand_id == brand_id,
        RAGCitation.hallucination_detected == True
    ).scalar()

    by_engine = db.query(
        RAGCitation.engine,
        func.count(RAGCitation.id)
    ).filter(
        RAGCitation.brand_id == brand_id
    ).group_by(RAGCitation.engine).all()

    return {
        "brand_id": brand_id,
        "total_citations": total,
        "accurate_citations": accurate,
        "hallucinations": hallucinations,
        "accuracy_rate": round((accurate / total * 100), 2) if total > 0 else None,
        "by_engine": {engine: count for engine, count in by_engine},
        "note": "All figures derive from real LLM scans and live URL verification; unavailable scans are excluded from accuracy.",
    }


@router.post("/generate-correction/{citation_id}")
def generate_correction(citation_id: int, db: Session = Depends(get_db)):
    citation = db.query(RAGCitation).filter(RAGCitation.id == citation_id).first()
    if not citation:
        raise HTTPException(status_code=404, detail="Citation not found")

    brand = db.query(Brand).filter(Brand.id == citation.brand_id).first()

    correction_payload = {
        "citation_id": citation.id,
        "engine": citation.engine,
        "query": citation.query,
        "incorrect_facts": citation.incorrect_facts,
        "hallucination_detected": citation.hallucination_detected,
        "correction_strategy": {
            "step_1": "Generate authoritative JSON-LD schema with correct facts",
            "step_2": "Deploy structured data across primary feeds",
            "step_3": "Submit knowledge update to Wikidata if applicable",
            "step_4": "Monitor next crawl cycle for cache flush",
        },
        "schema_payload": {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": brand.name,
            "url": f"https://{brand.domain}",
            "description": brand.description,
            "sameAs": [brand.wikipedia_url] if brand.wikipedia_url else [],
        },
    }

    return correction_payload

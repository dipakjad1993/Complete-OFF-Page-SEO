from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, JSON,
    ForeignKey, Enum, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.core.database import Base


class RiskLevel(str, enum.Enum):
    ENTERPRISE_SAFE = "enterprise_safe"
    AGGRESSIVE = "aggressive"


class MentionStatus(str, enum.Enum):
    DETECTED = "detected"
    OUTREACH_SENT = "outreach_sent"
    LINK_CONVERTED = "link_converted"
    DECLINED = "declined"


class AlertSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    domain = Column(String(500), nullable=False)
    kg_mid = Column(String(255))
    wikidata_id = Column(String(255))
    crunchbase_id = Column(String(255))
    wikipedia_url = Column(String(500))
    logo_url = Column(String(500))
    description = Column(Text)
    topical_taxonomy = Column(JSON)
    primary_categories = Column(JSON)
    seed_keywords = Column(JSON)
    semantic_vector = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    executives = relationship("Executive", back_populates="brand", cascade="all, delete-orphan")
    competitors = relationship("Competitor", back_populates="brand", cascade="all, delete-orphan")
    mentions = relationship("BrandMention", back_populates="brand", cascade="all, delete-orphan")
    backlinks = relationship("Backlink", back_populates="brand", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="brand", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="brand", cascade="all, delete-orphan")
    podcast_pitches = relationship("PodcastPitch", back_populates="brand", cascade="all, delete-orphan")
    pr_pitches = relationship("PRPitch", back_populates="brand", cascade="all, delete-orphan")
    knowledge_graph_triples = relationship("KnowledgeGraphTriple", back_populates="brand", cascade="all, delete-orphan")
    rag_citations = relationship("RAGCitation", back_populates="brand", cascade="all, delete-orphan")
    vector_distances = relationship("VectorDistance", back_populates="brand", cascade="all, delete-orphan")
    compliance_rules = relationship("ComplianceRule", back_populates="brand", cascade="all, delete-orphan")


class Executive(Base):
    __tablename__ = "executives"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    name = Column(String(255), nullable=False)
    title = Column(String(255))
    bio = Column(Text)
    credentials = Column(JSON)
    quotes = Column(JSON)
    social_profiles = Column(JSON)
    kg_mid = Column(String(255))
    wikidata_id = Column(String(255))
    wikipedia_url = Column(String(500))
    expertise_areas = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    brand = relationship("Brand", back_populates="executives")


class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    name = Column(String(255), nullable=False)
    domain = Column(String(500))
    kg_mid = Column(String(255))
    wikidata_id = Column(String(255))
    vector_embedding = Column(JSON)
    mention_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    brand = relationship("Brand", back_populates="competitors")


class BrandMention(Base):
    __tablename__ = "brand_mentions"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    source_url = Column(String(1000), nullable=False)
    source_domain = Column(String(500), nullable=False)
    source_title = Column(String(1000))
    context_snippet = Column(Text)
    has_link = Column(Boolean, default=False)
    link_url = Column(String(1000))
    link_type = Column(String(50))
    domain_authority = Column(Float)
    sentiment_score = Column(Float)
    is_competitor_mention = Column(Boolean, default=False)
    status = Column(String(50), default="detected")
    detected_at = Column(DateTime, default=datetime.utcnow)
    outreach_sent_at = Column(DateTime)
    link_converted_at = Column(DateTime)
    source = Column(String(100))           # newsapi | search_scrape | live_crawl | wikidata
    source_method = Column(String(100))
    relevance_score = Column(Float)        # 0-1 verified relevance to the brand
    verified = Column(Boolean, default=False)

    brand = relationship("Brand", back_populates="mentions")

    __table_args__ = (
        Index("ix_mentions_domain", "source_domain"),
        Index("ix_mentions_brand_status", "brand_id", "status"),
    )


class Backlink(Base):
    __tablename__ = "backlinks"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    source_url = Column(String(1000), nullable=False)
    source_domain = Column(String(500), nullable=False)
    target_url = Column(String(1000))
    anchor_text = Column(String(500))
    link_type = Column(String(50))
    domain_authority = Column(Float)
    page_authority = Column(Float)
    is_dofollow = Column(Boolean, default=True)
    is_sponsored = Column(Boolean, default=False)
    is_ugc = Column(Boolean, default=False)
    discovered_at = Column(DateTime, default=datetime.utcnow)
    last_checked = Column(DateTime)
    is_toxic = Column(Boolean, default=False)
    toxicity_score = Column(Float)
    toxicity_reasons = Column(JSON)
    source = Column(String(100))           # provider: ahrefs_api | live_crawl | majestic_api | moz_api
    source_method = Column(String(100))    # e.g. "ahrefs_v3_backlinks"
    retrieved_at = Column(DateTime)        # when the data was actually fetched
    verified = Column(Boolean, default=False)

    brand = relationship("Brand", back_populates="backlinks")


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    name = Column(String(255), nullable=False)
    campaign_type = Column(String(100))
    status = Column(String(50), default="draft")
    target_keywords = Column(JSON)
    target_journalists = Column(JSON)
    target_publications = Column(JSON)
    messaging = Column(Text)
    budget = Column(Float)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    results = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    brand = relationship("Brand", back_populates="campaigns")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    alert_type = Column(String(100), nullable=False)
    severity = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    data = Column(JSON)
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    brand = relationship("Brand", back_populates="alerts")


class PodcastPitch(Base):
    __tablename__ = "podcast_pitches"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    podcast_name = Column(String(500))
    podcast_url = Column(String(1000))
    host_name = Column(String(255))
    episode_title = Column(String(1000))
    transcript_snippet = Column(Text)
    brand_mentioned = Column(Boolean, default=False)
    has_link = Column(Boolean, default=False)
    pitch_status = Column(String(50), default="detected")
    pitch_sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    brand = relationship("Brand", back_populates="podcast_pitches")


class PRPitch(Base):
    __tablename__ = "pr_pitches"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    journalist_name = Column(String(255))
    journalist_email = Column(String(255))
    publication = Column(String(500))
    topic = Column(String(500))
    pitch_subject = Column(String(500))
    pitch_body = Column(Text)
    data_assets = Column(JSON)
    compliance_checked = Column(Boolean, default=False)
    compliance_flags = Column(JSON)
    status = Column(String(50), default="draft")
    sent_at = Column(DateTime)
    response_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    brand = relationship("Brand", back_populates="pr_pitches")


class KnowledgeGraphTriple(Base):
    __tablename__ = "knowledge_graph_triples"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    subject = Column(String(500), nullable=False)
    predicate = Column(String(500), nullable=False)
    object_value = Column(String(500), nullable=False)
    source = Column(String(500))
    source_url = Column(String(1000))
    confidence = Column(Float)
    is_verified = Column(Boolean, default=False)
    wikidata_property = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    brand = relationship("Brand", back_populates="knowledge_graph_triples")


class RAGCitation(Base):
    __tablename__ = "rag_citations"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    engine = Column(String(100), nullable=False)
    query = Column(String(1000), nullable=False)
    cited_entity = Column(String(255))
    citation_url = Column(String(1000))
    is_accurate = Column(Boolean)
    hallucination_detected = Column(Boolean, default=False)
    incorrect_facts = Column(JSON)
    context_snippet = Column(Text)
    detected_at = Column(DateTime, default=datetime.utcnow)
    source_urls = Column(JSON)             # the citations Perplexity/LLM returned
    source_method = Column(String(100))    # e.g. "perplexity_sonar" | "openai_gpt4o"
    verified = Column(Boolean, default=False)

    brand = relationship("Brand", back_populates="rag_citations")


class VectorDistance(Base):
    __tablename__ = "vector_distances"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    target_entity = Column(String(255), nullable=False)
    cosine_similarity = Column(Float)
    distance_score = Column(Float)
    co_occurrence_terms = Column(JSON)
    measurement_date = Column(DateTime, default=datetime.utcnow)

    brand = relationship("Brand", back_populates="vector_distances")


class CompetitorBERTVector(Base):
    __tablename__ = "competitor_bert_vectors"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    competitor_name = Column(String(255))
    source_url = Column(String(1000))
    extracted_entities = Column(JSON)
    semantic_phrases = Column(JSON)
    topic_pairings = Column(JSON)
    passage_vectors = Column(JSON)
    extracted_at = Column(DateTime, default=datetime.utcnow)


class EdgeRedirect(Base):
    __tablename__ = "edge_redirects"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    source_url = Column(String(1000), nullable=False)
    target_url = Column(String(1000), nullable=False)
    redirect_type = Column(String(10), default="301")
    is_active = Column(Boolean, default=False)
    deployed_at = Column(DateTime)
    equity_recovered = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class ToxicBacklink(Base):
    __tablename__ = "toxic_backlinks"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    source_url = Column(String(1000), nullable=False)
    source_domain = Column(String(500))
    toxicity_reason = Column(String(255))
    toxicity_score = Column(Float)
    hosting_ip = Column(String(100))
    registration_date = Column(DateTime)
    is_pbn = Column(Boolean, default=False)
    ai_content_score = Column(Float)
    flagged_at = Column(DateTime, default=datetime.utcnow)
    disavowed = Column(Boolean, default=False)


class GeoCrawlAudit(Base):
    __tablename__ = "geo_crawl_audits"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    region = Column(String(100), nullable=False)
    source_url = Column(String(1000))
    brand_cited = Column(Boolean, default=False)
    citation_context = Column(Text)
    domain_authority = Column(Float)
    audit_date = Column(DateTime, default=datetime.utcnow)


class AnchorTextProfile(Base):
    __tablename__ = "anchor_text_profiles"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    anchor_text = Column(String(500))
    count = Column(Integer, default=0)
    percentage = Column(Float)
    entropy_score = Column(Float)
    is_over_optimized = Column(Boolean, default=False)
    measured_at = Column(DateTime, default=datetime.utcnow)


class ShareOfSearch(Base):
    __tablename__ = "share_of_search"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    brand_name = Column(String(255))
    search_volume = Column(Integer)
    market_share_pct = Column(Float)
    revenue_attributed = Column(Float)
    period = Column(String(50))
    source = Column(String(100))
    measured_at = Column(DateTime, default=datetime.utcnow)


class CrawlStatus(Base):
    __tablename__ = "crawl_status"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    url = Column(String(1000), nullable=False)
    googlebot_crawled = Column(Boolean, default=False)
    googlebot_last_crawl = Column(DateTime)
    indexation_status = Column(String(50))
    ping_sent = Column(Boolean, default=False)
    ping_sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class SponsoredCompliance(Base):
    __tablename__ = "sponsored_compliance"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    source_url = Column(String(1000))
    source_domain = Column(String(500))
    has_rel_sponsored = Column(Boolean, default=False)
    has_ftc_disclosure = Column(Boolean, default=False)
    has_ad_disclosure = Column(Boolean, default=False)
    compliance_risk = Column(String(50))
    outreach_sent = Column(Boolean, default=False)
    detected_at = Column(DateTime, default=datetime.utcnow)


class HreflangAudit(Base):
    __tablename__ = "hreflang_audits"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    backlink_url = Column(String(1000))
    backlink_region = Column(String(100))
    target_page_region = Column(String(100))
    cannibalization_risk = Column(Boolean, default=False)
    equity_imbalance_score = Column(Float)
    recommendation = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class SchemaProtocol(Base):
    __tablename__ = "schema_protocols"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    source_url = Column(String(1000))
    schema_type = Column(String(255))
    schema_content = Column(JSON)
    is_machine_readable = Column(Boolean, default=False)
    has_open_api = Column(Boolean, default=False)
    has_c2pa_signature = Column(Boolean, default=False)
    validated_at = Column(DateTime, default=datetime.utcnow)


class ConsensusScore(Base):
    __tablename__ = "consensus_scores"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    overall_sentiment = Column(Float)
    reddit_sentiment = Column(Float)
    forum_sentiment = Column(Float)
    review_sentiment = Column(Float)
    media_sentiment = Column(Float)
    total_mentions = Column(Integer)
    positive_mentions = Column(Integer)
    negative_mentions = Column(Integer)
    neutral_mentions = Column(Integer)
    consensus_gap = Column(Float)
    measured_at = Column(DateTime, default=datetime.utcnow)


class SatelliteEntity(Base):
    __tablename__ = "satellite_entities"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    entity_domain = Column(String(500))
    entity_name = Column(String(255))
    topical_authority = Column(Float)
    estimated_value = Column(Float)
    acquisition_type = Column(String(50))
    domain_age = Column(Integer)
    backlink_count = Column(Integer)
    relevance_score = Column(Float)
    flagged_at = Column(DateTime, default=datetime.utcnow)


class ComplianceRule(Base):
    __tablename__ = "compliance_rules"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    rule_type = Column(String(100))
    rule_name = Column(String(255))
    rule_content = Column(JSON)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    brand = relationship("Brand", back_populates="compliance_rules")


class SimulationResult(Base):
    __tablename__ = "simulation_results"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    simulation_type = Column(String(100))
    input_data = Column(JSON)
    predicted_impact = Column(JSON)
    confidence_score = Column(Float)
    vector_shift_predictions = Column(JSON)
    run_at = Column(DateTime, default=datetime.utcnow)


class VisualEntityAudit(Base):
    __tablename__ = "visual_entity_audits"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    image_url = Column(String(1000))
    source_url = Column(String(1000))
    brand_detected = Column(Boolean, default=False)
    brand_position = Column(String(100))
    competitor_detected = Column(Boolean, default=False)
    competitor_positions = Column(JSON)
    visual_authority_score = Column(Float)
    analyzed_at = Column(DateTime, default=datetime.utcnow)


class PassageAttention(Base):
    __tablename__ = "passage_attention"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    source_url = Column(String(1000))
    passage_text = Column(Text)
    passage_tokens = Column(Integer)
    attention_weight = Column(Float)
    cosine_similarity = Column(Float)
    has_backlink = Column(Boolean, default=False)
    scored_at = Column(DateTime, default=datetime.utcnow)


class RedditConsensus(Base):
    __tablename__ = "reddit_consensus"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    subreddit = Column(String(255))
    thread_url = Column(String(1000))
    brand_mentioned = Column(Boolean, default=False)
    mention_context = Column(Text)
    sentiment = Column(Float)
    paired_terms = Column(JSON)
    competitor_mentions = Column(JSON)
    scraped_at = Column(DateTime, default=datetime.utcnow)


class DeadEquitySalvage(Base):
    __tablename__ = "dead_equity_salvage"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    source_url = Column(String(1000))
    target_url = Column(String(1000))
    http_status = Column(Integer)
    backlink_count = Column(Integer)
    domain_authority = Column(Float)
    equity_value = Column(Float)
    redirect_deployed = Column(Boolean, default=False)
    detected_at = Column(DateTime, default=datetime.utcnow)


class ZeroPartyDataAsset(Base):
    __tablename__ = "zero_party_data_assets"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    asset_name = Column(String(255))
    asset_type = Column(String(100))
    data_summary = Column(JSON)
    widget_embed_code = Column(Text)
    target_journalist = Column(String(255))
    target_publication = Column(String(255))
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PromptRun(Base):
    """Daily prompt-tracking runs (module 37): citation rate + SoV + sentiment."""

    __tablename__ = "prompt_runs"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    mode = Column(String(50))  # llm_keyed | proxy_serp
    prompts_tested = Column(Integer, default=0)
    prompts_cited = Column(Integer, default=0)
    citation_rate = Column(Float)
    sentiment = Column(JSON)
    rows = Column(JSON)
    run_at = Column(DateTime, default=datetime.utcnow)


class BotAudit(Base):
    """AI bot governance snapshots (module 36)."""

    __tablename__ = "bot_audits"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    governance_score = Column(Float)
    llms_present = Column(Boolean, default=False)
    robots_matrix = Column(JSON)
    probes = Column(JSON)
    audited_at = Column(DateTime, default=datetime.utcnow)


class AuthorEntity(Base):
    """E-E-A-T author entities (module 41)."""

    __tablename__ = "author_entities"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    name = Column(String(255), nullable=False)
    authority_score = Column(Float)
    credentials = Column(JSON)
    publications = Column(JSON)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ImageBacklink(Base):
    """Image/logo usage without attribution (module 40)."""

    __tablename__ = "image_backlinks"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    page_url = Column(String(1000))
    image_url = Column(String(1000))
    has_attribution = Column(Boolean, default=False)
    detected_at = Column(DateTime, default=datetime.utcnow)

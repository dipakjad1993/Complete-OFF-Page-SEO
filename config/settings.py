from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    APP_NAME: str = "Complete Off Page SEO - Entity-First Brand Consensus Engine"
    APP_VERSION: str = "2026.1.0"
    DEBUG: bool = False
    
    DATABASE_URL: str = "sqlite:///./offpage_seo.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_CSE_ID: Optional[str] = None
    GSC_CREDENTIALS_FILE: Optional[str] = None
    GA4_PROPERTY_ID: Optional[str] = None
    
    AHREFS_API_KEY: Optional[str] = None
    MAJESTIC_API_KEY: Optional[str] = None
    MOZ_ACCESS_KEY: Optional[str] = None
    MOZ_SECRET_KEY: Optional[str] = None
    
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    
    SERPAPI_KEY: Optional[str] = None
    PERPLEXITY_API_KEY: Optional[str] = None
    
    CLOUDFLARE_API_TOKEN: Optional[str] = None
    CLOUDFLARE_ZONE_ID: Optional[str] = None
    FASTLY_API_TOKEN: Optional[str] = None
    
    WIKIDATA_API_URL: str = "https://www.wikidata.org/w/api.php"
    WIKIPEDIA_API_URL: str = "https://en.wikipedia.org/w/api.php"
    
    NEWS_API_KEY: Optional[str] = None
    TWITTER_BEARER_TOKEN: Optional[str] = None
    
    RISK_TOLERANCE_LEVEL: str = "enterprise_safe"
    
    MAX_CONCURRENT_CRAWLS: int = 10
    CRAWL_DELAY_SECONDS: float = 1.0
    PROXY_URL: Optional[str] = None
    
    WHISPER_MODEL_SIZE: str = "base"

    # Provider reliability / verification settings
    VERIFY_SEARCH_RESULTS: bool = True
    MIN_RELEVANCE_SCORE: float = 0.35
    REQUEST_TIMEOUT_SECONDS: int = 30
    MAX_BACKLINK_REQUESTS: int = 100

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def configured_providers(self) -> list[str]:
        """Return the list of data providers that have credentials configured."""
        providers = []
        mapping = {
            "ahrefs": self.AHREFS_API_KEY,
            "majestic": self.MAJESTIC_API_KEY,
            "moz": self.MOZ_ACCESS_KEY,
            "serpapi": self.SERPAPI_KEY,
            "openai": self.OPENAI_API_KEY,
            "anthropic": self.ANTHROPIC_API_KEY,
            "perplexity": self.PERPLEXITY_API_KEY,
            "newsapi": self.NEWS_API_KEY,
            "google_kg": self.GOOGLE_API_KEY,
        }
        for name, key in mapping.items():
            if key:
                providers.append(name)
        return providers

settings = Settings()

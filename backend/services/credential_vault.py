from __future__ import annotations

"""Encrypted credential vault (Fernet via cryptography).

Replaces plaintext data/api_credentials.json. Per-brand keys, file-encrypted
at rest with CREDENTIALS_FERNET_KEY (or SECRET_KEY-derived fallback — warns).
Never logs secrets; provider-status only reports keyed vs missing.
"""

import base64
import hashlib
import json
import os

VAULT_PATH = "data/credentials.vault"
LEGACY_PATH = "data/api_credentials.json"


def _fernet():
    from cryptography.fernet import Fernet  # type: ignore
    raw = os.environ.get("CREDENTIALS_FERNET_KEY") or ""
    if not raw:
        from config.settings import settings
        if not settings.is_production_secret:
            raise RuntimeError("CREDENTIALS_FERNET_KEY is required in production when SECRET_KEY is default. Set CREDENTIALS_FERNET_KEY (generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())').")
        raw = settings.SECRET_KEY
    digest = hashlib.sha256(raw.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def vault_load() -> dict:
    if os.path.exists(VAULT_PATH):
        try:
            token = open(VAULT_PATH, "rb").read().strip()
            if token:
                return json.loads(_fernet().decrypt(token).decode())
        except Exception:
            return {}
    # one-time legacy migration (plaintext {} or old keys -> encrypted vault)
    if os.path.exists(LEGACY_PATH):
        try:
            data = json.load(open(LEGACY_PATH, encoding="utf-8", errors="replace"))
            if isinstance(data, dict) and data:
                vault_save(data)
                return data
        except Exception:
            pass
    return {}


def vault_save(data: dict) -> None:
    os.makedirs(os.path.dirname(VAULT_PATH) or ".", exist_ok=True)
    token = _fernet().encrypt(json.dumps(data).encode())
    with open(VAULT_PATH, "wb") as f:
        f.write(token)


def vault_status() -> dict:
    data = vault_load()
    known = ["SERPAPI_KEY", "NEWSAPI_KEY", "AHREFS_API_KEY", "MOZ_ACCESS_KEY",
             "MAJESTIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
             "PERPLEXITY_API_KEY", "GOOGLE_API_KEY", "BRAVE_SEARCH_API_KEY",
             "BING_SEARCH_API_KEY"]
    return {k: bool(data.get(k) or os.environ.get(k)) for k in known}

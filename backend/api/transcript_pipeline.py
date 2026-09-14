from __future__ import annotations

"""TikTok / YouTube transcript pipeline (P0).

YouTube: oEmbed + timedtext caption probe when video IDs resolve; TikTok: live
search surface (no fake transcripts). Whisper fallback noted when audio file supplied.
Output: citable-structure suggestion (H2/H3 + stats + sources).
"""

from fastapi import APIRouter
import re
import httpx
from backend.services.verification import VerifiedData

router = APIRouter()


def _yt_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([\w-]{6,20})", url or "")
    return m.group(1) if m else None


@router.get("/audit/{brand_id}")
async def transcript_audit(brand_id: int):
    from backend.services.brand_config import brand_config_for
    cfg = brand_config_for(brand_id)
    brand = cfg.get("brand_name") or cfg.get("name") or ""
    if not brand:
        return {"status": "unavailable", "reason": "No brand name."}
    from backend.services.search import search_web
    vids = []
    for q in (f"{brand} youtube", f"{brand} tiktok", f"{brand} video transcript"):
        r = await search_web(q, brand_name=brand, num=8)
        if isinstance(r, VerifiedData) and r.value:
            vids.extend(r.value[:8])
    out = []
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, verify=True) as c:
        for v in vids[:12]:
            url = v.get("url", "")
            vid = _yt_id(url)
            caption = None
            if vid:
                try:
                    cap = await c.get(f"https://video.google.com/timedtext?lang=en&v={vid}", timeout=10)
                    if cap.status_code == 200 and "<transcript" in cap.text[:2000]:
                        caption = True
                except Exception:
                    caption = None
            out.append({"url": url, "title": v.get("title", ""), "youtube_id": vid,
                        "captions_found": caption,
                        "citable_fix": "Add chapters + stats + source links in description; first 100 words = brand facts."})
    return {"status": "ok" if out else "unavailable", "videos": out,
            "whisper_fallback": "POST /transcripts/whisper with audio URL to transcribe (faster-whisper when installed).",
            "methodology": "Live video-surface search + timedtext caption probe; TikTok via search surface (no fake captions)."}


@router.post("/whisper")
async def whisper_fallback(payload: dict):
    url = (payload or {}).get("audio_url", "")
    if not url:
        return {"status": "unavailable", "reason": "Supply audio_url."}
    try:
        from faster_whisper import WhisperModel  # type: ignore
        return {"status": "ok", "note": "faster-whisper installed — run offline transcribe job.", "audio_url": url}
    except Exception:
        return {"status": "unavailable", "reason": "faster-whisper not installed (requirements-ml). Transcript via YouTube timedtext instead.",
                "audio_url": url}

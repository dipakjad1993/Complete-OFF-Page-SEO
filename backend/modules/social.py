from __future__ import annotations
"""Social / UGC domain facade."""
from .llm import _impl

feature_reddit_consensus_alias = _impl("feature_reddit_consensus")
feature_github_citations_alias = _impl("feature_github_citations")
feature_podcast_video_alias = _impl("feature_podcast_video")
feature_transcription_alias = _impl("feature_transcription")
feature_consensus_alias = _impl("feature_consensus")

"""
Fool Earnings Transcript Downloader

A Python module to download earnings call transcripts from The Motley Fool.
"""

from .fool_transcript_downloader import (
    FoolTranscriptDownloader,
    TranscriptInfo,
    DEFAULT_OUTPUT_DIR,
)

__version__ = "1.0.0"
__all__ = [
    "FoolTranscriptDownloader",
    "TranscriptInfo",
    "DEFAULT_OUTPUT_DIR",
]

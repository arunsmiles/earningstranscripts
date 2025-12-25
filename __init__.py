"""
Earnings Transcripts and SEC Filings Downloader

A Python module to download:
- Earnings call transcripts from The Motley Fool
- SEC EDGAR filings (10-K, 10-Q) for public companies
"""

from .fool_transcript_downloader import (
    FoolTranscriptDownloader,
    TranscriptInfo,
    DEFAULT_OUTPUT_DIR as FOOL_DEFAULT_OUTPUT_DIR,
)

from .sec_edgar_downloader import (
    SECEdgarDownloader,
    SECFilingInfo,
    DEFAULT_OUTPUT_DIR as SEC_DEFAULT_OUTPUT_DIR,
)

__version__ = "1.0.0"
__all__ = [
    "FoolTranscriptDownloader",
    "TranscriptInfo",
    "FOOL_DEFAULT_OUTPUT_DIR",
    "SECEdgarDownloader",
    "SECFilingInfo",
    "SEC_DEFAULT_OUTPUT_DIR",
]

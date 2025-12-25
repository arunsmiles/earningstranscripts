"""
Earnings Data Client

Download and query earnings transcripts and SEC filings.

Main Components:
- EarningsDataClient: High-level query interface
- Downloaders: FoolTranscriptDownloader, SECEdgarDownloader, SECBulkDownloader
- Configuration: Centralized data directory management
"""

# Configuration
from .config import Config, get_config, set_data_directory

# Query Client and Models
from .client import EarningsDataClient
from .models import TranscriptResult, FilingResult, AggregateStats, FileIndex

# Indexer
from .indexer import DataIndexer

# Downloaders
from .fool_transcript_downloader import FoolTranscriptDownloader, TranscriptInfo
from .sec_edgar_downloader import SECEdgarDownloader, SECFilingInfo
from .sec_bulk_downloader import SECBulkDownloader, BulkDownloadProgress

__version__ = "0.1.0"

__all__ = [
    # Configuration
    "Config",
    "get_config",
    "set_data_directory",
    # Query Client
    "EarningsDataClient",
    # Models
    "TranscriptResult",
    "FilingResult",
    "AggregateStats",
    "FileIndex",
    # Indexer
    "DataIndexer",
    # Downloaders
    "FoolTranscriptDownloader",
    "TranscriptInfo",
    "SECEdgarDownloader",
    "SECFilingInfo",
    "SECBulkDownloader",
    "BulkDownloadProgress",
]

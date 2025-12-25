"""
Data models for earnings transcripts and SEC filings.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List


@dataclass
class FileIndex:
    """Metadata for an indexed file"""
    id: Optional[int]
    ticker: str
    file_type: str  # 'transcript' or 'filing'
    form_type: Optional[str]  # '10-K', '10-Q', None for transcripts
    year: int
    quarter: Optional[str]  # 'Q1', 'Q2', 'Q3', 'Q4', 'FY'
    filing_date: Optional[str]  # YYYY-MM-DD format
    file_path: str
    file_size_bytes: int
    indexed_at: Optional[str]  # ISO format timestamp
    content_hash: Optional[str]  # MD5 hash for change detection

    @classmethod
    def from_row(cls, row: tuple) -> 'FileIndex':
        """Create from database row"""
        return cls(
            id=row[0],
            ticker=row[1],
            file_type=row[2],
            form_type=row[3],
            year=row[4],
            quarter=row[5],
            filing_date=row[6],
            file_path=row[7],
            file_size_bytes=row[8],
            indexed_at=row[9],
            content_hash=row[10]
        )


@dataclass
class TranscriptResult:
    """Result from transcript query"""
    ticker: str
    year: int
    quarter: str
    file_path: Path
    file_size_bytes: int
    indexed_at: str
    content: Optional[str] = None  # Lazy loaded

    def load_content(self) -> str:
        """Load transcript content from file"""
        if self.content is None:
            self.content = self.file_path.read_text()
        return self.content

    @classmethod
    def from_file_index(cls, index: FileIndex) -> 'TranscriptResult':
        """Create from FileIndex"""
        return cls(
            ticker=index.ticker,
            year=index.year,
            quarter=index.quarter or '',
            file_path=Path(index.file_path),
            file_size_bytes=index.file_size_bytes,
            indexed_at=index.indexed_at or ''
        )


@dataclass
class FilingResult:
    """Result from SEC filing query"""
    ticker: str
    form_type: str
    year: int
    quarter: Optional[str]
    filing_date: str
    file_path: Path
    file_size_bytes: int
    indexed_at: str
    content: Optional[str] = None  # Lazy loaded

    def load_content(self) -> str:
        """Load filing content from file"""
        if self.content is None:
            self.content = self.file_path.read_text()
        return self.content

    @classmethod
    def from_file_index(cls, index: FileIndex) -> 'FilingResult':
        """Create from FileIndex"""
        return cls(
            ticker=index.ticker,
            form_type=index.form_type or '',
            year=index.year,
            quarter=index.quarter,
            filing_date=index.filing_date or '',
            file_path=Path(index.file_path),
            file_size_bytes=index.file_size_bytes,
            indexed_at=index.indexed_at or ''
        )


@dataclass
class AggregateStats:
    """Aggregate statistics"""
    total_files: int
    total_size_bytes: int
    by_ticker: dict  # ticker -> count
    by_year: dict  # year -> count
    by_type: dict  # file_type -> count
    date_range: tuple  # (earliest, latest)

    @property
    def total_size_mb(self) -> float:
        """Total size in MB"""
        return self.total_size_bytes / (1024 * 1024)

    @property
    def total_size_gb(self) -> float:
        """Total size in GB"""
        return self.total_size_bytes / (1024 * 1024 * 1024)

"""
Metadata indexer for earnings transcripts and SEC filings.

Scans data directories and builds a SQLite database index for fast queries.
"""

import hashlib
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from config import Config, get_config
from models import FileIndex

logger = logging.getLogger(__name__)


class DataIndexer:
    """Indexes earnings data files into a metadata database"""

    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the indexer.

        Args:
            config: Config instance. If None, uses global config.
        """
        self.config = config or get_config()
        self.db_path = self.config.metadata_db
        self.conn = sqlite3.connect(self.db_path)
        self._create_tables()
        logger.info(f"Initialized indexer with database: {self.db_path}")

    def _create_tables(self):
        """Create database tables if they don't exist"""
        # Main file index table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS file_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                file_type TEXT NOT NULL,
                form_type TEXT,
                year INTEGER NOT NULL,
                quarter TEXT,
                filing_date TEXT,
                file_path TEXT UNIQUE NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                indexed_at TEXT NOT NULL,
                content_hash TEXT
            )
        """)

        # Indexes for fast queries
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker ON file_index(ticker)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_year ON file_index(year)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON file_index(file_type)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_form ON file_index(form_type)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON file_index(filing_date)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker_year ON file_index(ticker, year)")

        # Full-text search table (FTS5)
        self.conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS file_content_fts USING fts5(
                ticker,
                file_path,
                content,
                content='',
                tokenize='porter'
            )
        """)

        # Indexing metadata
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS index_metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
        """)

        self.conn.commit()
        logger.debug("Database tables created/verified")

    def _parse_transcript_filename(self, filename: str) -> Optional[Dict]:
        """
        Parse transcript filename to extract metadata.

        Format: <TICKER>_<YEAR>_<QUARTER>_earningstranscript_from_fool.md
        Example: AAPL_2024_Q3_earningstranscript_from_fool.md
        """
        pattern = r'^([A-Z]+)_(\d{4})_(Q[1-4]|FY)_.*\.md$'
        match = re.match(pattern, filename)
        if match:
            return {
                'ticker': match.group(1),
                'year': int(match.group(2)),
                'quarter': match.group(3),
                'file_type': 'transcript',
                'form_type': None,
                'filing_date': None
            }
        return None

    def _parse_filing_filename(self, filename: str) -> Optional[Dict]:
        """
        Parse SEC filing filename to extract metadata.

        Formats:
        - Quarterly: <TICKER>_<YEAR>_<QUARTER>_<FORM>.html
        - Annual: <TICKER>_<YEAR>_FY_<FORM>.html

        Examples:
        - AAPL_2024_Q3_10-Q.html
        - AAPL_2024_FY_10-K.html
        """
        # Pattern for filings
        pattern = r'^([A-Z]+)_(\d{4})_(Q[1-4]|FY)_(10-[KQ](?:/A)?)(?:_complete)?\.(?:html|txt)$'
        match = re.match(pattern, filename)
        if match:
            year = int(match.group(2))
            quarter = match.group(3)
            form_type = match.group(4)

            # Estimate filing date based on quarter (approximate)
            if quarter == 'Q1':
                filing_date = f"{year}-05-01"
            elif quarter == 'Q2':
                filing_date = f"{year}-08-01"
            elif quarter == 'Q3':
                filing_date = f"{year}-11-01"
            else:  # Q4 or FY
                filing_date = f"{year + 1}-02-01"

            return {
                'ticker': match.group(1),
                'year': year,
                'quarter': quarter,
                'file_type': 'filing',
                'form_type': form_type,
                'filing_date': filing_date
            }
        return None

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute MD5 hash of file content"""
        md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return md5.hexdigest()

    def _is_file_indexed(self, file_path: str) -> Optional[str]:
        """
        Check if file is already indexed.

        Returns:
            Content hash if indexed, None otherwise
        """
        cursor = self.conn.execute(
            "SELECT content_hash FROM file_index WHERE file_path = ?",
            (file_path,)
        )
        result = cursor.fetchone()
        return result[0] if result else None

    def index_file(self, file_path: Path, force: bool = False) -> bool:
        """
        Index a single file.

        Args:
            file_path: Path to the file
            force: Force re-indexing even if file is already indexed

        Returns:
            True if indexed, False if skipped or failed
        """
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return False

        # Parse filename to extract metadata
        filename = file_path.name
        metadata = None

        if filename.endswith('.md'):
            metadata = self._parse_transcript_filename(filename)
        elif filename.endswith('.html') or filename.endswith('.txt'):
            metadata = self._parse_filing_filename(filename)

        if not metadata:
            logger.debug(f"Skipping file (unrecognized format): {filename}")
            return False

        # Check if already indexed
        file_path_str = str(file_path)
        existing_hash = self._is_file_indexed(file_path_str)
        current_hash = self._compute_file_hash(file_path)

        if not force and existing_hash == current_hash:
            logger.debug(f"Skipping file (already indexed): {filename}")
            return False

        # Get file size
        file_size = file_path.stat().st_size

        # Insert or update index
        try:
            self.conn.execute("""
                INSERT OR REPLACE INTO file_index
                (ticker, file_type, form_type, year, quarter, filing_date,
                 file_path, file_size_bytes, indexed_at, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metadata['ticker'],
                metadata['file_type'],
                metadata['form_type'],
                metadata['year'],
                metadata['quarter'],
                metadata['filing_date'],
                file_path_str,
                file_size,
                datetime.now().isoformat(),
                current_hash
            ))
            self.conn.commit()
            logger.info(f"Indexed: {filename}")
            return True
        except Exception as e:
            logger.error(f"Failed to index {filename}: {e}")
            return False

    def index_directory(self, directory: Path, file_type: str, force: bool = False) -> Dict[str, int]:
        """
        Index all files in a directory.

        Args:
            directory: Directory to scan
            file_type: 'transcript' or 'filing'
            force: Force re-indexing

        Returns:
            Statistics: {'indexed': count, 'skipped': count, 'failed': count}
        """
        stats = {'indexed': 0, 'skipped': 0, 'failed': 0}

        if not directory.exists():
            logger.warning(f"Directory not found: {directory}")
            return stats

        # Determine file patterns
        if file_type == 'transcript':
            patterns = ['*.md']
        else:  # filing
            patterns = ['*.html', '*_complete.txt']

        logger.info(f"Scanning {directory} for {file_type}s...")

        for pattern in patterns:
            for file_path in directory.glob(pattern):
                # Skip XBRL directories and non-primary files
                if '_xbrl' in str(file_path):
                    continue

                result = self.index_file(file_path, force=force)
                if result:
                    stats['indexed'] += 1
                else:
                    stats['skipped'] += 1

        logger.info(f"Indexed {stats['indexed']} {file_type}s, skipped {stats['skipped']}")
        return stats

    def index_all(self, force: bool = False) -> Dict[str, Dict[str, int]]:
        """
        Index all data directories.

        Args:
            force: Force re-indexing of all files

        Returns:
            Statistics by type
        """
        logger.info("Starting full index...")
        start_time = datetime.now()

        stats = {
            'transcripts': self.index_directory(self.config.transcripts_dir, 'transcript', force),
            'filings': self.index_directory(self.config.secfilings_dir, 'filing', force)
        }

        # Update metadata
        self.conn.execute("""
            INSERT OR REPLACE INTO index_metadata (key, value, updated_at)
            VALUES ('last_full_index', ?, ?)
        """, (start_time.isoformat(), datetime.now().isoformat()))
        self.conn.commit()

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Indexing complete in {elapsed:.2f} seconds")

        return stats

    def get_stats(self) -> Dict:
        """Get indexing statistics"""
        cursor = self.conn.execute("""
            SELECT
                COUNT(*) as total_files,
                SUM(file_size_bytes) as total_size,
                MIN(year) as earliest_year,
                MAX(year) as latest_year
            FROM file_index
        """)
        row = cursor.fetchone()

        cursor = self.conn.execute("""
            SELECT file_type, COUNT(*) as count
            FROM file_index
            GROUP BY file_type
        """)
        by_type = {row[0]: row[1] for row in cursor.fetchall()}

        cursor = self.conn.execute("""
            SELECT ticker, COUNT(*) as count
            FROM file_index
            GROUP BY ticker
            ORDER BY count DESC
            LIMIT 10
        """)
        top_tickers = {row[0]: row[1] for row in cursor.fetchall()}

        return {
            'total_files': row[0] or 0,
            'total_size_bytes': row[1] or 0,
            'total_size_mb': (row[1] or 0) / (1024 * 1024),
            'date_range': (row[2], row[3]),
            'by_type': by_type,
            'top_tickers': top_tickers
        }

    def close(self):
        """Close database connection"""
        self.conn.close()


def main():
    """CLI for indexer"""
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description="Index earnings data for fast queries")
    parser.add_argument(
        '--data-dir',
        help='Base data directory'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force re-indexing of all files'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show indexing statistics'
    )

    args = parser.parse_args()

    # Create config
    from config import Config
    config = Config(args.data_dir) if args.data_dir else get_config()

    # Create indexer
    indexer = DataIndexer(config)

    if args.stats:
        stats = indexer.get_stats()
        print("\n" + "=" * 60)
        print("INDEXING STATISTICS")
        print("=" * 60)
        print(f"Total files:     {stats['total_files']}")
        print(f"Total size:      {stats['total_size_mb']:.2f} MB")
        print(f"Date range:      {stats['date_range'][0]} - {stats['date_range'][1]}")
        print(f"\nBy type:")
        for file_type, count in stats['by_type'].items():
            print(f"  {file_type:12s} {count:6d}")
        print(f"\nTop 10 tickers:")
        for ticker, count in stats['top_tickers'].items():
            print(f"  {ticker:6s} {count:6d}")
        print("=" * 60)
    else:
        # Run indexing
        result = indexer.index_all(force=args.force)
        print("\n" + "=" * 60)
        print("INDEXING COMPLETE")
        print("=" * 60)
        for data_type, stats in result.items():
            print(f"{data_type.capitalize()}:")
            print(f"  Indexed: {stats['indexed']}")
            print(f"  Skipped: {stats['skipped']}")
        print("=" * 60)

        # Show stats
        stats = indexer.get_stats()
        print(f"\nTotal files indexed: {stats['total_files']}")
        print(f"Database location: {config.metadata_db}")

    indexer.close()


if __name__ == '__main__':
    main()

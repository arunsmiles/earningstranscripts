"""
EarningsDataClient - High-level query interface for earnings data.

Provides easy-to-use methods for querying transcripts and SEC filings
with support for filtering, aggregation, and full-text search.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Union

from config import Config, get_config
from models import FileIndex, TranscriptResult, FilingResult, AggregateStats
from indexer import DataIndexer

logger = logging.getLogger(__name__)


class EarningsDataClient:
    """
    Client for querying earnings transcripts and SEC filings.

    This is the main interface for accessing indexed earnings data.
    Provides methods for per-ticker queries, aggregate queries, and full-text search.
    """

    def __init__(self, config: Optional[Config] = None, auto_index: bool = True):
        """
        Initialize the client.

        Args:
            config: Config instance. If None, uses global config.
            auto_index: Automatically run indexer if database is empty
        """
        self.config = config or get_config()
        self.db_path = self.config.metadata_db

        if not self.db_path.exists() and auto_index:
            logger.info("Metadata database not found. Running initial indexing...")
            indexer = DataIndexer(self.config)
            indexer.index_all()
            indexer.close()

        self.conn = sqlite3.connect(self.db_path)
        logger.info(f"Connected to earnings data at {self.config.data_dir}")

    def _file_index_from_row(self, row: tuple) -> FileIndex:
        """Convert database row to FileIndex"""
        return FileIndex.from_row(row)

    def query_transcripts(
        self,
        tickers: Optional[Union[str, List[str]]] = None,
        year: Optional[int] = None,
        quarter: Optional[str] = None,
        year_range: Optional[tuple] = None,
        load_content: bool = False,
        limit: Optional[int] = None
    ) -> List[TranscriptResult]:
        """
        Query earnings call transcripts.

        Args:
            tickers: Single ticker or list of tickers (e.g., 'AAPL' or ['AAPL', 'MSFT'])
            year: Filter by specific year
            quarter: Filter by quarter ('Q1', 'Q2', 'Q3', 'Q4')
            year_range: Filter by year range (start_year, end_year) inclusive
            load_content: Load file content into results (default: False for performance)
            limit: Maximum number of results

        Returns:
            List of TranscriptResult objects
        """
        query = "SELECT * FROM file_index WHERE file_type = 'transcript'"
        params = []

        # Build WHERE clause
        if tickers:
            ticker_list = [tickers] if isinstance(tickers, str) else tickers
            placeholders = ','.join('?' * len(ticker_list))
            query += f" AND ticker IN ({placeholders})"
            params.extend(ticker_list)

        if year:
            query += " AND year = ?"
            params.append(year)

        if year_range:
            query += " AND year BETWEEN ? AND ?"
            params.extend(year_range)

        if quarter:
            query += " AND quarter = ?"
            params.append(quarter)

        # Order by date (most recent first)
        query += " ORDER BY year DESC, quarter DESC"

        if limit:
            query += f" LIMIT {limit}"

        # Execute query
        cursor = self.conn.execute(query, params)
        results = []

        for row in cursor.fetchall():
            index = self._file_index_from_row(row)
            result = TranscriptResult.from_file_index(index)
            if load_content:
                result.load_content()
            results.append(result)

        logger.info(f"Found {len(results)} transcripts")
        return results

    def query_filings(
        self,
        tickers: Optional[Union[str, List[str]]] = None,
        form_types: Optional[Union[str, List[str]]] = None,
        year: Optional[int] = None,
        quarter: Optional[str] = None,
        year_range: Optional[tuple] = None,
        date_range: Optional[tuple] = None,
        load_content: bool = False,
        limit: Optional[int] = None
    ) -> List[FilingResult]:
        """
        Query SEC filings (10-K, 10-Q, etc.).

        Args:
            tickers: Single ticker or list of tickers
            form_types: Single form type or list (e.g., '10-K' or ['10-K', '10-Q'])
            year: Filter by specific year
            quarter: Filter by quarter ('Q1', 'Q2', 'Q3', 'Q4', 'FY')
            year_range: Filter by year range (start_year, end_year) inclusive
            date_range: Filter by filing date range ('YYYY-MM-DD', 'YYYY-MM-DD')
            load_content: Load file content into results
            limit: Maximum number of results

        Returns:
            List of FilingResult objects
        """
        query = "SELECT * FROM file_index WHERE file_type = 'filing'"
        params = []

        # Build WHERE clause
        if tickers:
            ticker_list = [tickers] if isinstance(tickers, str) else tickers
            placeholders = ','.join('?' * len(ticker_list))
            query += f" AND ticker IN ({placeholders})"
            params.extend(ticker_list)

        if form_types:
            form_list = [form_types] if isinstance(form_types, str) else form_types
            placeholders = ','.join('?' * len(form_list))
            query += f" AND form_type IN ({placeholders})"
            params.extend(form_list)

        if year:
            query += " AND year = ?"
            params.append(year)

        if year_range:
            query += " AND year BETWEEN ? AND ?"
            params.extend(year_range)

        if quarter:
            query += " AND quarter = ?"
            params.append(quarter)

        if date_range:
            query += " AND filing_date BETWEEN ? AND ?"
            params.extend(date_range)

        # Order by date (most recent first)
        query += " ORDER BY year DESC, filing_date DESC"

        if limit:
            query += f" LIMIT {limit}"

        # Execute query
        cursor = self.conn.execute(query, params)
        results = []

        for row in cursor.fetchall():
            index = self._file_index_from_row(row)
            result = FilingResult.from_file_index(index)
            if load_content:
                result.load_content()
            results.append(result)

        logger.info(f"Found {len(results)} filings")
        return results

    def get_ticker_data(
        self,
        ticker: str,
        include_transcripts: bool = True,
        include_filings: bool = True
    ) -> Dict:
        """
        Get all data for a specific ticker.

        Args:
            ticker: Stock ticker symbol
            include_transcripts: Include earnings transcripts
            include_filings: Include SEC filings

        Returns:
            Dictionary with transcripts and filings
        """
        result = {}

        if include_transcripts:
            result['transcripts'] = self.query_transcripts(tickers=ticker)

        if include_filings:
            result['filings'] = self.query_filings(tickers=ticker)

        return result

    def aggregate_by_ticker(self) -> Dict[str, int]:
        """
        Get file counts by ticker.

        Returns:
            Dictionary mapping ticker to file count
        """
        cursor = self.conn.execute("""
            SELECT ticker, COUNT(*) as count
            FROM file_index
            GROUP BY ticker
            ORDER BY count DESC
        """)
        return {row[0]: row[1] for row in cursor.fetchall()}

    def aggregate_by_year(self) -> Dict[int, int]:
        """
        Get file counts by year.

        Returns:
            Dictionary mapping year to file count
        """
        cursor = self.conn.execute("""
            SELECT year, COUNT(*) as count
            FROM file_index
            GROUP BY year
            ORDER BY year DESC
        """)
        return {row[0]: row[1] for row in cursor.fetchall()}

    def aggregate_by_type(self) -> Dict[str, int]:
        """
        Get file counts by type.

        Returns:
            Dictionary mapping file type to count
        """
        cursor = self.conn.execute("""
            SELECT file_type, COUNT(*) as count
            FROM file_index
            GROUP BY file_type
        """)
        return {row[0]: row[1] for row in cursor.fetchall()}

    def get_statistics(self) -> AggregateStats:
        """
        Get comprehensive statistics about indexed data.

        Returns:
            AggregateStats object
        """
        cursor = self.conn.execute("""
            SELECT
                COUNT(*) as total_files,
                SUM(file_size_bytes) as total_size,
                MIN(year) as earliest_year,
                MAX(year) as latest_year
            FROM file_index
        """)
        row = cursor.fetchone()

        return AggregateStats(
            total_files=row[0] or 0,
            total_size_bytes=row[1] or 0,
            by_ticker=self.aggregate_by_ticker(),
            by_year=self.aggregate_by_year(),
            by_type=self.aggregate_by_type(),
            date_range=(row[2], row[3])
        )

    def search_content(
        self,
        search_term: str,
        tickers: Optional[Union[str, List[str]]] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Full-text search across all content.

        Args:
            search_term: Search query (supports FTS5 syntax)
            tickers: Optionally filter by ticker(s)
            limit: Maximum number of results

        Returns:
            List of search results with snippets
        """
        # Note: This requires the FTS5 table to be populated
        # For now, return a simple grep-like search
        logger.warning("Full-text search not yet implemented. Use query methods instead.")
        return []

    def get_tickers(self) -> List[str]:
        """
        Get list of all indexed tickers.

        Returns:
            Sorted list of ticker symbols
        """
        cursor = self.conn.execute("""
            SELECT DISTINCT ticker
            FROM file_index
            ORDER BY ticker
        """)
        return [row[0] for row in cursor.fetchall()]

    def get_years(self, ticker: Optional[str] = None) -> List[int]:
        """
        Get list of years with data.

        Args:
            ticker: Optionally filter by ticker

        Returns:
            Sorted list of years
        """
        if ticker:
            cursor = self.conn.execute("""
                SELECT DISTINCT year
                FROM file_index
                WHERE ticker = ?
                ORDER BY year DESC
            """, (ticker,))
        else:
            cursor = self.conn.execute("""
                SELECT DISTINCT year
                FROM file_index
                ORDER BY year DESC
            """)
        return [row[0] for row in cursor.fetchall()]

    def reindex(self, force: bool = False):
        """
        Re-run indexer to update database with new files.

        Args:
            force: Force re-indexing of all files
        """
        logger.info("Running indexer...")
        indexer = DataIndexer(self.config)
        stats = indexer.index_all(force=force)
        indexer.close()
        logger.info(f"Indexing complete: {stats}")
        return stats

    def close(self):
        """Close database connection"""
        self.conn.close()


def main():
    """CLI for querying earnings data"""
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    parser = argparse.ArgumentParser(description="Query earnings transcripts and SEC filings")
    parser.add_argument('--data-dir', help='Base data directory')
    parser.add_argument('-t', '--ticker', help='Ticker symbol')
    parser.add_argument('--year', type=int, help='Filter by year')
    parser.add_argument('--quarter', choices=['Q1', 'Q2', 'Q3', 'Q4', 'FY'], help='Filter by quarter')
    parser.add_argument('--type', choices=['transcripts', 'filings', 'both'], default='both',
                        help='Data type to query')
    parser.add_argument('--stats', action='store_true', help='Show statistics')
    parser.add_argument('--tickers', action='store_true', help='List all tickers')
    parser.add_argument('--reindex', action='store_true', help='Re-run indexer')

    args = parser.parse_args()

    # Create client
    from config import Config
    config = Config(args.data_dir) if args.data_dir else get_config()
    client = EarningsDataClient(config)

    if args.reindex:
        print("Re-indexing data...")
        client.reindex()
        print("Done!")
        return

    if args.stats:
        stats = client.get_statistics()
        print("\n" + "=" * 60)
        print("EARNINGS DATA STATISTICS")
        print("=" * 60)
        print(f"Total files:     {stats.total_files}")
        print(f"Total size:      {stats.total_size_mb:.2f} MB")
        print(f"Date range:      {stats.date_range[0]} - {stats.date_range[1]}")
        print(f"\nBy type:")
        for file_type, count in stats.by_type.items():
            print(f"  {file_type:12s} {count:6d}")
        print(f"\nTop 10 tickers:")
        for i, (ticker, count) in enumerate(list(stats.by_ticker.items())[:10]):
            print(f"  {ticker:6s} {count:6d}")
        print("=" * 60)
        return

    if args.tickers:
        tickers = client.get_tickers()
        print(f"\nIndexed tickers ({len(tickers)}):")
        print(", ".join(tickers))
        return

    if args.ticker:
        print(f"\nQuerying data for {args.ticker}...")

        if args.type in ['transcripts', 'both']:
            transcripts = client.query_transcripts(
                tickers=args.ticker,
                year=args.year,
                quarter=args.quarter
            )
            print(f"\nTranscripts ({len(transcripts)}):")
            for t in transcripts:
                print(f"  {t.year} {t.quarter}: {t.file_path.name} ({t.file_size_bytes // 1024} KB)")

        if args.type in ['filings', 'both']:
            filings = client.query_filings(
                tickers=args.ticker,
                year=args.year,
                quarter=args.quarter
            )
            print(f"\nFilings ({len(filings)}):")
            for f in filings:
                print(f"  {f.year} {f.quarter or 'FY'} {f.form_type}: {f.file_path.name} ({f.file_size_bytes // 1024} KB)")
    else:
        parser.print_help()

    client.close()


if __name__ == '__main__':
    main()

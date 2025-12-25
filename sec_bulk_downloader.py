#!/usr/bin/env python3
"""
SEC EDGAR Bulk Filing Downloader

Downloads SEC filings efficiently using SEC's bulk data files.
Supports filtering by ticker lists, top N companies, or all companies.

Uses SEC's nightly submissions.zip which contains metadata for all companies.
Then downloads actual filing documents for filtered companies.

Author: Claude
License: MIT
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests

from sec_edgar_downloader import SECEdgarDownloader, SECFilingInfo
from config import get_config, Config

# Constants
BULK_DATA_URL = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
DEFAULT_CACHE_DIR = ".sec_cache"
DEFAULT_OUTPUT_DIR = "secfilings"
DEFAULT_USER_EMAIL = "umber-stack.79@icloud.com"
PROGRESS_DB = "download_progress.db"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BulkDownloadProgress:
    """Track download progress using SQLite"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self._create_tables()

    def _create_tables(self):
        """Create progress tracking tables"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                ticker TEXT,
                cik TEXT,
                form_type TEXT,
                filing_date TEXT,
                accession_number TEXT PRIMARY KEY,
                status TEXT,
                downloaded_at TEXT,
                error_message TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                started_at TEXT,
                completed_at TEXT,
                total_tickers INTEGER,
                completed_tickers INTEGER,
                failed_tickers INTEGER
            )
        """)
        self.conn.commit()

    def mark_downloaded(self, ticker: str, filing_info: SECFilingInfo):
        """Mark a filing as downloaded"""
        self.conn.execute("""
            INSERT OR REPLACE INTO downloads
            (ticker, cik, form_type, filing_date, accession_number, status, downloaded_at)
            VALUES (?, ?, ?, ?, ?, 'completed', ?)
        """, (ticker, filing_info.cik, filing_info.form_type, filing_info.filing_date,
              filing_info.accession_number, datetime.now().isoformat()))
        self.conn.commit()

    def mark_failed(self, ticker: str, filing_info: SECFilingInfo, error: str):
        """Mark a filing as failed"""
        self.conn.execute("""
            INSERT OR REPLACE INTO downloads
            (ticker, cik, form_type, filing_date, accession_number, status, error_message)
            VALUES (?, ?, ?, ?, ?, 'failed', ?)
        """, (ticker, filing_info.cik, filing_info.form_type, filing_info.filing_date,
              filing_info.accession_number, error))
        self.conn.commit()

    def is_downloaded(self, accession_number: str) -> bool:
        """Check if a filing has been downloaded"""
        cursor = self.conn.execute(
            "SELECT status FROM downloads WHERE accession_number = ?",
            (accession_number,)
        )
        result = cursor.fetchone()
        return result is not None and result[0] == 'completed'

    def get_stats(self) -> Dict:
        """Get download statistics"""
        cursor = self.conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM downloads
        """)
        row = cursor.fetchone()
        return {
            'total': row[0] or 0,
            'completed': row[1] or 0,
            'failed': row[2] or 0
        }

    def close(self):
        """Close database connection"""
        self.conn.close()


class SECBulkDownloader:
    """Download SEC filings using bulk data files"""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        output_dir: Optional[str] = None,
        user_email: str = DEFAULT_USER_EMAIL,
        verbose: bool = False,
        config: Optional[Config] = None,
        data_dir: Optional[str] = None
    ):
        """
        Initialize bulk downloader

        Args:
            cache_dir: Directory to cache bulk data (deprecated - use config or data_dir instead)
            output_dir: Directory to save downloaded filings (deprecated - use config or data_dir instead)
            user_email: Email for User-Agent header
            verbose: Enable debug logging
            config: Config instance to use. If provided, cache_dir and output_dir are ignored
            data_dir: Base data directory. If provided, creates a new Config with this directory
        """
        # Priority: config > data_dir > explicit cache_dir/output_dir > global config
        if config:
            self.config = config
            self.cache_dir = config.cache_dir
            self.output_dir = config.secfilings_dir
        elif data_dir:
            self.config = Config(data_dir)
            self.cache_dir = self.config.cache_dir
            self.output_dir = self.config.secfilings_dir
        elif cache_dir or output_dir:
            # Backward compatibility: if explicit dirs provided, use them directly
            self.config = None
            self.cache_dir = Path(cache_dir) if cache_dir else Path(DEFAULT_CACHE_DIR)
            self.output_dir = Path(output_dir) if output_dir else Path(DEFAULT_OUTPUT_DIR)
            if cache_dir != DEFAULT_CACHE_DIR or output_dir != DEFAULT_OUTPUT_DIR:
                logger.warning(
                    "Using cache_dir/output_dir directly is deprecated. "
                    "Please use config=Config(data_dir) or data_dir parameter instead."
                )
        else:
            # Use global config
            self.config = get_config()
            self.cache_dir = self.config.cache_dir
            self.output_dir = self.config.secfilings_dir

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.user_email = user_email
        self.verbose = verbose

        if verbose:
            logger.setLevel(logging.DEBUG)

        # Initialize progress tracker
        progress_db_path = self.cache_dir / PROGRESS_DB
        self.progress = BulkDownloadProgress(progress_db_path)

        # Initialize individual downloader (pass config if available)
        if self.config:
            self.downloader = SECEdgarDownloader(
                config=self.config,
                user_email=user_email,
                verbose=verbose
            )
        else:
            self.downloader = SECEdgarDownloader(
                output_dir=str(self.output_dir),
                user_email=user_email,
                verbose=verbose
            )

        # Cache for submissions data
        self.submissions_cache: Dict[str, Dict] = {}

        logger.info(f"Initialized SEC Bulk Downloader")
        logger.info(f"Cache directory: {self.cache_dir}")
        logger.info(f"Output directory: {self.output_dir}")

    def download_bulk_data(self, force: bool = False) -> Path:
        """
        Download SEC bulk submissions data

        Args:
            force: Force re-download even if cached

        Returns:
            Path to extracted submissions directory
        """
        zip_path = self.cache_dir / "submissions.zip"
        extract_dir = self.cache_dir / "submissions"

        # Check if already downloaded
        if zip_path.exists() and not force:
            # Check if it's recent (less than 1 day old)
            age = time.time() - zip_path.stat().st_mtime
            if age < 86400:  # 24 hours
                logger.info(f"Using cached bulk data (age: {age/3600:.1f} hours)")
                if extract_dir.exists():
                    return extract_dir

        logger.info("Downloading SEC bulk submissions data...")
        logger.info(f"URL: {BULK_DATA_URL}")
        logger.info("This may take a few minutes (~2GB file)...")

        # Download with progress
        headers = {
            "User-Agent": f"EarningsTranscripts {self.user_email}",
            "Accept-Encoding": "gzip, deflate"
        }

        response = requests.get(BULK_DATA_URL, headers=headers, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0

        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    progress = (downloaded / total_size) * 100
                    print(f"\rDownload progress: {progress:.1f}%", end='', flush=True)

        print()  # New line after progress
        logger.info(f"Downloaded {downloaded / 1024 / 1024:.1f} MB")

        # Extract ZIP
        logger.info("Extracting bulk data...")
        extract_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        logger.info(f"Extracted to: {extract_dir}")

        # Count files
        json_files = list(extract_dir.glob("CIK*.json"))
        logger.info(f"Found {len(json_files)} company submission files")

        return extract_dir

    def load_submissions_data(self, cik: str) -> Optional[Dict]:
        """
        Load submission data for a CIK from bulk data

        Args:
            cik: CIK number (with or without leading zeros)

        Returns:
            Submission data dict or None if not found
        """
        # Normalize CIK to 10 digits
        cik_padded = cik.zfill(10)

        # Check cache
        if cik_padded in self.submissions_cache:
            return self.submissions_cache[cik_padded]

        # Load from file
        submissions_dir = self.cache_dir / "submissions"
        json_path = submissions_dir / f"CIK{cik_padded}.json"

        if not json_path.exists():
            logger.warning(f"No submission data found for CIK {cik_padded}")
            return None

        with open(json_path, 'r') as f:
            data = json.load(f)

        # Cache it
        self.submissions_cache[cik_padded] = data

        return data

    def get_tickers_from_file(self, file_path: Path, top_n: Optional[int] = None) -> List[str]:
        """
        Read tickers from file

        Args:
            file_path: Path to file containing tickers (one per line)
            top_n: Optional limit to top N tickers

        Returns:
            List of ticker symbols
        """
        tickers = []

        with open(file_path, 'r') as f:
            for line in f:
                ticker = line.strip().upper()
                if ticker and not ticker.startswith('#'):  # Skip comments
                    tickers.append(ticker)

        logger.info(f"Loaded {len(tickers)} tickers from {file_path}")

        if top_n is not None:
            tickers = tickers[:top_n]
            logger.info(f"Limited to top {top_n} tickers")

        return tickers

    def get_all_tickers(self) -> List[str]:
        """
        Get all available tickers from bulk data

        Returns:
            List of all ticker symbols
        """
        # Load from ticker-CIK mapping
        if not self.downloader.ticker_cik_map:
            self.downloader.load_ticker_cik_mapping()

        tickers = list(self.downloader.ticker_cik_map.keys())
        logger.info(f"Found {len(tickers)} total tickers")

        return tickers

    def download_for_tickers(
        self,
        tickers: List[str],
        form_types: List[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip_existing: bool = True
    ) -> Dict[str, int]:
        """
        Download filings for a list of tickers

        Args:
            tickers: List of ticker symbols
            form_types: List of form types to download
            start_date: Optional start date filter
            end_date: Optional end date filter
            skip_existing: Skip already downloaded files

        Returns:
            Dictionary mapping tickers to number of filings downloaded
        """
        logger.info(f"Starting bulk download for {len(tickers)} tickers")

        results = {}
        failed_tickers = []

        for i, ticker in enumerate(tickers, 1):
            logger.info(f"\n[{i}/{len(tickers)}] Processing {ticker}")

            try:
                # Get CIK
                cik = self.downloader.get_cik_from_ticker(ticker)
                if not cik:
                    logger.warning(f"CIK not found for {ticker}, skipping")
                    failed_tickers.append(ticker)
                    results[ticker] = 0
                    continue

                # Load submissions from bulk data
                submissions = self.load_submissions_data(cik)
                if not submissions:
                    logger.warning(f"No submissions data for {ticker}, skipping")
                    failed_tickers.append(ticker)
                    results[ticker] = 0
                    continue

                # Parse filings
                filings = self.downloader.parse_filings_from_submissions(
                    submissions,
                    ticker,
                    form_types=form_types,
                    start_date=start_date,
                    end_date=end_date
                )

                if not filings:
                    logger.info(f"No filings found for {ticker}")
                    results[ticker] = 0
                    continue

                # Download each filing
                downloaded_count = 0
                for filing in filings:
                    # Check if already downloaded (progress tracking)
                    if skip_existing and self.progress.is_downloaded(filing.accession_number):
                        logger.debug(f"Skipping already downloaded: {filing.accession_number}")
                        continue

                    try:
                        # Download filing
                        downloaded = self.downloader.download_filing(filing)

                        # Save filing
                        self.downloader.save_filing(downloaded, filing)

                        # Mark as downloaded
                        self.progress.mark_downloaded(ticker, filing)
                        downloaded_count += 1

                    except Exception as e:
                        logger.error(f"Failed to download {filing.form_type} for {ticker}: {e}")
                        self.progress.mark_failed(ticker, filing, str(e))

                results[ticker] = downloaded_count
                logger.info(f"Downloaded {downloaded_count} filings for {ticker}")

            except Exception as e:
                logger.error(f"Failed to process {ticker}: {e}")
                failed_tickers.append(ticker)
                results[ticker] = 0

        # Summary
        logger.info("\n" + "="*60)
        logger.info("BULK DOWNLOAD SUMMARY")
        logger.info("="*60)
        logger.info(f"Total tickers processed: {len(tickers)}")
        logger.info(f"Successful: {len(tickers) - len(failed_tickers)}")
        logger.info(f"Failed: {len(failed_tickers)}")

        total_filings = sum(results.values())
        logger.info(f"Total filings downloaded: {total_filings}")

        if failed_tickers:
            logger.info(f"\nFailed tickers: {', '.join(failed_tickers)}")

        # Progress stats
        stats = self.progress.get_stats()
        logger.info(f"\nOverall progress stats:")
        logger.info(f"  Total attempts: {stats['total']}")
        logger.info(f"  Completed: {stats['completed']}")
        logger.info(f"  Failed: {stats['failed']}")
        logger.info("="*60)

        return results

    def cleanup(self):
        """Clean up resources"""
        self.progress.close()


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Bulk download SEC EDGAR filings using nightly bulk data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download bulk data first (do this once per day)
  %(prog)s --download-bulk-data

  # Download filings for tickers in a file
  %(prog)s --ticker-file my_tickers.txt

  # Download for top 100 companies (from ranked file)
  %(prog)s --ticker-file sp500.txt --top 100

  # Download for all companies (WARNING: This will take a LONG time!)
  %(prog)s --all-tickers --from 2024-01-01

  # Download only 10-K filings
  %(prog)s --ticker-file my_tickers.txt --forms 10-K

  # Force re-download of bulk data
  %(prog)s --download-bulk-data --force

Note:
  - Bulk data is ~2GB and updated nightly by SEC
  - First run will download and cache bulk data
  - Progress is tracked and downloads can be resumed
  - Use --ticker-file with one ticker per line
        """
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        '--ticker-file',
        type=Path,
        help='File containing tickers to download (one per line)'
    )
    input_group.add_argument(
        '--all-tickers',
        action='store_true',
        help='Download for ALL tickers (WARNING: 10,000+ companies)'
    )

    # Top N filter
    parser.add_argument(
        '--top',
        type=int,
        help='Limit to top N tickers from ticker file'
    )

    # Bulk data management
    parser.add_argument(
        '--download-bulk-data',
        action='store_true',
        help='Download/update SEC bulk submissions data'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='Force re-download of bulk data (even if cached)'
    )

    # Output options
    parser.add_argument(
        '--data-dir',
        type=str,
        help='Base data directory (filings will be saved to {data-dir}/secfilings/, '
             'cache to {data-dir}/cache/). Can also be set via EARNINGS_DATA_DIR environment variable.'
    )

    parser.add_argument(
        '-o', '--output-dir',
        type=str,
        help=f'[DEPRECATED] Output directory. Use --data-dir instead.'
    )

    parser.add_argument(
        '--cache-dir',
        type=str,
        help=f'[DEPRECATED] Cache directory. Use --data-dir instead.'
    )

    # Filtering options
    parser.add_argument(
        '--forms',
        nargs='+',
        choices=['10-K', '10-Q', '10-K/A', '10-Q/A'],
        default=None,
        help='Form types to download (default: all 10-K and 10-Q variants)'
    )

    parser.add_argument(
        '--from',
        dest='from_date',
        help='Start date in YYYY-MM-DD format'
    )

    parser.add_argument(
        '--to',
        dest='to_date',
        help='End date in YYYY-MM-DD format (default: today)'
    )

    # Other options
    parser.add_argument(
        '--email',
        default=DEFAULT_USER_EMAIL,
        help=f'Email for User-Agent header (default: {DEFAULT_USER_EMAIL})'
    )

    parser.add_argument(
        '--no-skip',
        action='store_true',
        help='Re-download existing files (default: skip existing)'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    # Create downloader
    # Use data_dir if provided, otherwise fall back to cache_dir/output_dir for backward compatibility
    bulk_downloader = SECBulkDownloader(
        data_dir=args.data_dir,
        cache_dir=args.cache_dir,
        output_dir=args.output_dir,
        user_email=args.email,
        verbose=args.verbose
    )

    try:
        # Download bulk data if requested
        if args.download_bulk_data or args.ticker_file or args.all_tickers:
            bulk_downloader.download_bulk_data(force=args.force)

        # Exit if only downloading bulk data
        if args.download_bulk_data and not (args.ticker_file or args.all_tickers):
            logger.info("Bulk data downloaded. Run with --ticker-file or --all-tickers to download filings.")
            return

        # Validate input
        if not args.ticker_file and not args.all_tickers:
            parser.error("Must specify --ticker-file, --all-tickers, or --download-bulk-data")

        # Get ticker list
        if args.ticker_file:
            if not args.ticker_file.exists():
                parser.error(f"Ticker file not found: {args.ticker_file}")
            tickers = bulk_downloader.get_tickers_from_file(args.ticker_file, top_n=args.top)
        else:  # --all-tickers
            tickers = bulk_downloader.get_all_tickers()
            if args.top:
                tickers = tickers[:args.top]
                logger.info(f"Limited to first {args.top} tickers")

        if not tickers:
            logger.error("No tickers to process")
            return

        # Confirm for large operations
        if len(tickers) > 100:
            logger.warning(f"\nAbout to download filings for {len(tickers)} companies.")
            logger.warning("This may take several hours or days depending on date range.")
            response = input("Continue? (yes/no): ")
            if response.lower() not in ['yes', 'y']:
                logger.info("Cancelled by user")
                return

        # Parse date range
        end_date = datetime.now()
        if args.to_date:
            end_date = datetime.strptime(args.to_date, "%Y-%m-%d")

        start_date = None
        if args.from_date:
            start_date = datetime.strptime(args.from_date, "%Y-%m-%d")
        else:
            # Default: last 3 months
            start_date = end_date - timedelta(days=90)

        logger.info(f"\nDate range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

        # Download filings
        results = bulk_downloader.download_for_tickers(
            tickers=tickers,
            form_types=args.forms,
            start_date=start_date,
            end_date=end_date,
            skip_existing=not args.no_skip
        )

    except KeyboardInterrupt:
        logger.info("\nDownload interrupted by user")
        logger.info("Progress has been saved. Re-run to resume.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Download failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    finally:
        bulk_downloader.cleanup()


if __name__ == "__main__":
    main()

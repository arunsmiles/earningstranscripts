#!/usr/bin/env python3
"""
SEC EDGAR Filing Downloader

Downloads 10-K (annual) and 10-Q (quarterly) filings from SEC EDGAR for specified companies.
Uses the official SEC EDGAR API (data.sec.gov) which requires no API key.

Downloads:
- Primary HTML document
- Complete submission text file (.txt)
- XBRL financial data files

Author: Claude
License: MIT
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Constants
SEC_BASE_URL = "https://www.sec.gov"
SEC_API_BASE_URL = "https://data.sec.gov"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
DEFAULT_OUTPUT_DIR = "secfilings"
DEFAULT_USER_EMAIL = "umber-stack.79@icloud.com"
MAX_REQUESTS_PER_SECOND = 10
REQUEST_DELAY = 0.15  # Conservative delay between requests (150ms)
MIN_CONTENT_SIZE_KB = 1.0  # Minimum file size to be considered valid

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class SECFilingInfo:
    """Information about a SEC filing"""
    ticker: str
    cik: str
    form_type: str  # 10-K, 10-Q, 10-K/A, 10-Q/A
    filing_date: str  # Date the filing was submitted
    report_date: str  # Period of report
    accession_number: str  # Unique filing identifier
    primary_document: str  # Filename of the primary document
    year: int
    quarter: Optional[str] = None  # Q1, Q2, Q3, Q4 for 10-Q; None for 10-K
    xbrl_files: List[str] = field(default_factory=list)  # List of XBRL-related files


class SECEdgarDownloader:
    """Downloads SEC Edgar filings for specified companies"""

    def __init__(
        self,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        user_email: str = DEFAULT_USER_EMAIL,
        delay: float = REQUEST_DELAY,
        verbose: bool = False
    ):
        """
        Initialize the SEC Edgar downloader

        Args:
            output_dir: Directory to save downloaded filings
            user_email: Email for User-Agent header (required by SEC)
            delay: Delay between requests in seconds
            verbose: Enable debug logging
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.user_email = user_email
        self.delay = delay

        if verbose:
            logger.setLevel(logging.DEBUG)

        # Setup headers required by SEC
        self.headers = {
            "User-Agent": f"EarningsTranscripts {user_email}",
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov"
        }

        # Cache for ticker-to-CIK mapping
        self.ticker_cik_map: Dict[str, str] = {}

        logger.info(f"Initialized SEC Edgar Downloader")
        logger.info(f"Output directory: {self.output_dir}")
        logger.info(f"User-Agent email: {user_email}")

    def _make_request(self, url: str, headers: Optional[Dict] = None) -> requests.Response:
        """
        Make HTTP request with rate limiting and error handling

        Args:
            url: URL to request
            headers: Optional custom headers

        Returns:
            Response object
        """
        if headers is None:
            headers = self.headers.copy()

        # Update Host header based on URL
        if "www.sec.gov" in url:
            headers["Host"] = "www.sec.gov"
        elif "data.sec.gov" in url:
            headers["Host"] = "data.sec.gov"

        time.sleep(self.delay)

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            raise

    def load_ticker_cik_mapping(self) -> Dict[str, str]:
        """
        Load ticker-to-CIK mapping from SEC

        Returns:
            Dictionary mapping ticker symbols to CIK numbers
        """
        if self.ticker_cik_map:
            return self.ticker_cik_map

        logger.info("Loading ticker-to-CIK mapping from SEC...")

        try:
            response = self._make_request(TICKER_CIK_URL)
            data = response.json()

            # The JSON structure is: {0: {ticker: "AAPL", cik_str: 320193, ...}, ...}
            for entry in data.values():
                ticker = entry.get("ticker", "").upper()
                cik = str(entry.get("cik_str", ""))
                if ticker and cik:
                    self.ticker_cik_map[ticker] = cik

            logger.info(f"Loaded {len(self.ticker_cik_map)} ticker-to-CIK mappings")
            return self.ticker_cik_map

        except Exception as e:
            logger.error(f"Failed to load ticker-to-CIK mapping: {e}")
            raise

    def get_cik_from_ticker(self, ticker: str) -> Optional[str]:
        """
        Get CIK number for a ticker symbol

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL")

        Returns:
            10-digit CIK number with leading zeros, or None if not found
        """
        if not self.ticker_cik_map:
            self.load_ticker_cik_mapping()

        ticker = ticker.upper()
        cik = self.ticker_cik_map.get(ticker)

        if cik:
            # Pad CIK to 10 digits with leading zeros
            return cik.zfill(10)

        logger.warning(f"CIK not found for ticker: {ticker}")
        return None

    def get_company_submissions(self, cik: str) -> Dict:
        """
        Get company submission history from SEC API

        Args:
            cik: 10-digit CIK number

        Returns:
            JSON data containing filing history
        """
        url = f"{SEC_API_BASE_URL}/submissions/CIK{cik}.json"
        logger.debug(f"Fetching submissions for CIK {cik}: {url}")

        try:
            response = self._make_request(url)
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch submissions for CIK {cik}: {e}")
            raise

    def _calculate_quarter(self, report_date: str, fiscal_year_end: str) -> str:
        """
        Calculate fiscal quarter from report date

        Args:
            report_date: Report date in YYYY-MM-DD format
            fiscal_year_end: Fiscal year end in MMDD format (e.g., "1231")

        Returns:
            Quarter string: Q1, Q2, Q3, or Q4
        """
        try:
            report_dt = datetime.strptime(report_date, "%Y-%m-%d")
            report_month = report_dt.month

            # Extract fiscal year end month
            fye_month = int(fiscal_year_end[:2])

            # Calculate quarter based on fiscal year end
            # Q1 ends 3 months after FYE, Q2 ends 6 months after, etc.
            quarters = []
            for i in range(1, 5):
                quarter_end_month = (fye_month + (i * 3)) % 12
                if quarter_end_month == 0:
                    quarter_end_month = 12
                quarters.append((quarter_end_month, f"Q{i}"))

            # Find which quarter this report falls into
            for month, quarter in quarters:
                # Allow some flexibility (within 1 month)
                if abs(report_month - month) <= 1 or abs(report_month - month) >= 11:
                    return quarter

            # Default to calendar quarter if we can't determine fiscal quarter
            calendar_quarter = (report_month - 1) // 3 + 1
            return f"Q{calendar_quarter}"

        except Exception as e:
            logger.debug(f"Error calculating quarter: {e}, using calendar quarter")
            # Fallback to calendar quarter
            report_dt = datetime.strptime(report_date, "%Y-%m-%d")
            calendar_quarter = (report_dt.month - 1) // 3 + 1
            return f"Q{calendar_quarter}"

    def _get_filing_files_list(self, cik: str, accession_number: str) -> List[str]:
        """
        Get list of all files in a filing submission

        Args:
            cik: CIK number
            accession_number: Accession number

        Returns:
            List of filenames in the submission
        """
        # Remove dashes from accession number
        accession_no_dashes = accession_number.replace("-", "")

        # Construct URL to filing directory index
        index_url = f"{SEC_ARCHIVES_URL}/{cik}/{accession_no_dashes}/index.json"

        try:
            headers = self.headers.copy()
            headers["Host"] = "www.sec.gov"
            response = self._make_request(index_url, headers=headers)
            index_data = response.json()

            # Extract filenames from directory listing
            files = []
            if "directory" in index_data and "item" in index_data["directory"]:
                for item in index_data["directory"]["item"]:
                    if "name" in item:
                        files.append(item["name"])

            return files
        except Exception as e:
            logger.debug(f"Could not fetch file list for {accession_number}: {e}")
            return []

    def _identify_xbrl_files(self, files: List[str]) -> List[str]:
        """
        Identify XBRL-related files from a file list

        Args:
            files: List of filenames

        Returns:
            List of XBRL-related filenames
        """
        xbrl_files = []
        xbrl_extensions = ['.xml', '.xsd', '.cal', '.def', '.lab', '.pre']

        for filename in files:
            # Check for XBRL file extensions
            if any(filename.lower().endswith(ext) for ext in xbrl_extensions):
                # Exclude non-XBRL XML files
                if not any(exclude in filename.lower() for exclude in ['xml.old', 'cached']):
                    xbrl_files.append(filename)

        return xbrl_files

    def parse_filings_from_submissions(
        self,
        submissions_data: Dict,
        ticker: str,
        form_types: List[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[SECFilingInfo]:
        """
        Parse filing information from submissions JSON

        Args:
            submissions_data: JSON data from submissions API
            ticker: Stock ticker symbol
            form_types: List of form types to include (default: ['10-K', '10-Q', '10-K/A', '10-Q/A'])
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of SECFilingInfo objects
        """
        if form_types is None:
            form_types = ['10-K', '10-Q', '10-K/A', '10-Q/A']

        filings = []
        cik = submissions_data.get("cik", "")
        fiscal_year_end = submissions_data.get("fiscalYearEnd", "1231")

        recent = submissions_data.get("filings", {}).get("recent", {})

        if not recent:
            logger.warning(f"No recent filings found for {ticker}")
            return filings

        # Get arrays from JSON
        accession_numbers = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        forms = recent.get("form", [])
        primary_docs = recent.get("primaryDocument", [])

        logger.debug(f"Processing {len(forms)} total filings for {ticker}")
        logger.debug(f"Form types filter: {form_types}")

        # Iterate through filings
        for i in range(len(forms)):
            form = forms[i]

            if form not in form_types:
                continue

            filing_date_str = filing_dates[i]
            report_date_str = report_dates[i]

            # Apply date filters
            if start_date or end_date:
                filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d")

                if start_date and filing_date < start_date:
                    continue
                if end_date and filing_date > end_date:
                    continue

            # Extract year from report date
            year = int(report_date_str.split("-")[0])

            # Calculate quarter for 10-Q filings
            quarter = None
            if form.startswith("10-Q"):
                quarter = self._calculate_quarter(report_date_str, fiscal_year_end)

            # Get list of files in this submission to identify XBRL files
            cik_padded = cik.zfill(10)
            files = self._get_filing_files_list(cik_padded, accession_numbers[i])
            xbrl_files = self._identify_xbrl_files(files) if files else []

            filing_info = SECFilingInfo(
                ticker=ticker,
                cik=cik,
                form_type=form,
                filing_date=filing_date_str,
                report_date=report_date_str,
                accession_number=accession_numbers[i],
                primary_document=primary_docs[i],
                year=year,
                quarter=quarter,
                xbrl_files=xbrl_files
            )

            filings.append(filing_info)

        logger.info(f"Found {len(filings)} filings for {ticker} matching criteria")
        if filings:
            form_counts = {}
            for f in filings:
                form_counts[f.form_type] = form_counts.get(f.form_type, 0) + 1
            logger.info(f"Breakdown by form type: {form_counts}")

        return filings

    def _get_filing_url(self, filing_info: SECFilingInfo, filename: str = None) -> str:
        """
        Construct URL for filing document

        Args:
            filing_info: Filing information
            filename: Optional specific filename (defaults to primary document)

        Returns:
            URL to download filing
        """
        # Remove dashes from accession number for URL
        accession_no_dashes = filing_info.accession_number.replace("-", "")

        if filename is None:
            filename = filing_info.primary_document

        # Pad CIK to 10 digits
        cik_padded = filing_info.cik.zfill(10)

        url = f"{SEC_ARCHIVES_URL}/{cik_padded}/{accession_no_dashes}/{filename}"
        return url

    def _get_complete_submission_url(self, filing_info: SECFilingInfo) -> str:
        """
        Construct URL for complete submission text file

        Args:
            filing_info: Filing information

        Returns:
            URL to download complete submission
        """
        # Complete submission uses the accession number with dashes as filename
        cik_padded = filing_info.cik.zfill(10)
        url = f"{SEC_ARCHIVES_URL}/{cik_padded}/{filing_info.accession_number.replace('-', '')}/{filing_info.accession_number}.txt"
        return url

    def _generate_filename(self, filing_info: SECFilingInfo, extension: str, suffix: str = "") -> str:
        """
        Generate filename following the naming convention

        Args:
            filing_info: Filing information
            extension: File extension (.html, .txt, .xml, etc.)
            suffix: Optional suffix to add before extension (e.g., "_complete", "_xbrl")

        Returns:
            Filename string
        """
        ticker = filing_info.ticker.upper()
        year = filing_info.year
        form_id = filing_info.form_type.replace("/", "-")  # 10-K/A -> 10-K-A

        if filing_info.quarter:
            # Quarterly filing: TICKER_YEAR_QUARTER_FORMID.ext
            filename = f"{ticker}_{year}_{filing_info.quarter}_{form_id}{suffix}{extension}"
        else:
            # Annual filing: TICKER_YEAR_FY_FORMID.ext
            filename = f"{ticker}_{year}_FY_{form_id}{suffix}{extension}"

        return filename

    def download_filing(self, filing_info: SECFilingInfo) -> Dict[str, str]:
        """
        Download all files for a single filing

        Args:
            filing_info: Filing information

        Returns:
            Dictionary mapping file types to content
            Keys: 'html', 'complete_txt', 'xbrl_files' (dict of filename: content)
        """
        logger.info(f"Downloading {filing_info.ticker} {filing_info.form_type} from {filing_info.filing_date}")

        downloaded = {}
        headers = self.headers.copy()
        headers["Host"] = "www.sec.gov"

        # 1. Download primary HTML document
        try:
            html_url = self._get_filing_url(filing_info)
            logger.debug(f"Downloading HTML: {html_url}")
            response = self._make_request(html_url, headers=headers)
            html_content = response.text

            # Validate content size
            content_size_kb = len(html_content) / 1024
            if content_size_kb < MIN_CONTENT_SIZE_KB:
                logger.warning(f"Downloaded HTML content is very small ({content_size_kb:.2f} KB), might be incomplete")

            downloaded['html'] = html_content
            logger.debug(f"Downloaded HTML ({content_size_kb:.2f} KB)")
        except Exception as e:
            logger.error(f"Failed to download HTML: {e}")
            downloaded['html'] = None

        # 2. Download complete submission text file
        try:
            complete_url = self._get_complete_submission_url(filing_info)
            logger.debug(f"Downloading complete submission: {complete_url}")
            response = self._make_request(complete_url, headers=headers)
            complete_txt = response.text

            content_size_kb = len(complete_txt) / 1024
            downloaded['complete_txt'] = complete_txt
            logger.debug(f"Downloaded complete submission ({content_size_kb:.2f} KB)")
        except Exception as e:
            logger.warning(f"Failed to download complete submission: {e}")
            downloaded['complete_txt'] = None

        # 3. Download XBRL files
        downloaded['xbrl_files'] = {}
        if filing_info.xbrl_files:
            logger.debug(f"Downloading {len(filing_info.xbrl_files)} XBRL files")
            for xbrl_file in filing_info.xbrl_files:
                try:
                    xbrl_url = self._get_filing_url(filing_info, filename=xbrl_file)
                    logger.debug(f"Downloading XBRL file: {xbrl_file}")
                    response = self._make_request(xbrl_url, headers=headers)
                    downloaded['xbrl_files'][xbrl_file] = response.text
                except Exception as e:
                    logger.warning(f"Failed to download XBRL file {xbrl_file}: {e}")

        return downloaded

    def save_filing(self, downloaded: Dict[str, str], filing_info: SECFilingInfo) -> List[Path]:
        """
        Save filing files to disk

        Args:
            downloaded: Dictionary of downloaded content
            filing_info: Filing information

        Returns:
            List of saved file paths
        """
        saved_paths = []

        # 1. Save HTML
        if downloaded.get('html'):
            html_filename = self._generate_filename(filing_info, ".html")
            html_path = self.output_dir / html_filename
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(downloaded['html'])
            logger.info(f"Saved HTML: {html_path}")
            saved_paths.append(html_path)

        # 2. Save complete submission text
        if downloaded.get('complete_txt'):
            txt_filename = self._generate_filename(filing_info, ".txt", suffix="_complete")
            txt_path = self.output_dir / txt_filename
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(downloaded['complete_txt'])
            logger.info(f"Saved complete submission: {txt_path}")
            saved_paths.append(txt_path)

        # 3. Save XBRL files
        xbrl_files = downloaded.get('xbrl_files', {})
        if xbrl_files:
            # Create XBRL subdirectory for this filing
            base_filename = self._generate_filename(filing_info, "", suffix="")
            xbrl_dir = self.output_dir / f"{base_filename}_xbrl"
            xbrl_dir.mkdir(exist_ok=True)

            for filename, content in xbrl_files.items():
                xbrl_path = xbrl_dir / filename
                with open(xbrl_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                saved_paths.append(xbrl_path)

            if xbrl_files:
                logger.info(f"Saved {len(xbrl_files)} XBRL files to: {xbrl_dir}")

        return saved_paths

    def download_all_for_ticker(
        self,
        ticker: str,
        form_types: List[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip_existing: bool = True
    ) -> List[List[Path]]:
        """
        Download all filings for a ticker

        Args:
            ticker: Stock ticker symbol
            form_types: List of form types to download
            start_date: Optional start date filter
            end_date: Optional end date filter
            skip_existing: Skip already downloaded files

        Returns:
            List of lists of file paths for downloaded filings
        """
        logger.info(f"Starting download for ticker: {ticker}")

        # Get CIK
        cik = self.get_cik_from_ticker(ticker)
        if not cik:
            logger.error(f"Cannot proceed without CIK for {ticker}")
            return []

        logger.info(f"CIK for {ticker}: {cik}")

        # Get submissions
        submissions = self.get_company_submissions(cik)

        # Parse filings
        filings = self.parse_filings_from_submissions(
            submissions,
            ticker,
            form_types=form_types,
            start_date=start_date,
            end_date=end_date
        )

        if not filings:
            logger.warning(f"No filings found for {ticker}")
            return []

        downloaded_files = []
        skipped_count = 0

        for filing_info in filings:
            # Check if already exists
            if skip_existing:
                html_filename = self._generate_filename(filing_info, ".html")
                html_path = self.output_dir / html_filename

                if html_path.exists():
                    logger.debug(f"Skipping existing filing: {html_filename}")
                    skipped_count += 1
                    continue

            try:
                # Download filing
                downloaded = self.download_filing(filing_info)

                # Save filing
                paths = self.save_filing(downloaded, filing_info)
                downloaded_files.append(paths)

            except Exception as e:
                logger.error(f"Failed to download {filing_info.ticker} {filing_info.form_type}: {e}")
                continue

        if skipped_count > 0:
            logger.info(f"Skipped {skipped_count} existing filings")

        logger.info(f"Downloaded {len(downloaded_files)} filings for {ticker}")
        return downloaded_files

    def download_bulk(
        self,
        tickers: List[str],
        form_types: List[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip_existing: bool = True
    ) -> Dict[str, List[List[Path]]]:
        """
        Download filings for multiple tickers

        Args:
            tickers: List of stock ticker symbols
            form_types: List of form types to download
            start_date: Optional start date filter
            end_date: Optional end date filter
            skip_existing: Skip already downloaded files

        Returns:
            Dictionary mapping tickers to list of downloaded file paths
        """
        logger.info(f"Starting bulk download for {len(tickers)} tickers")

        results = {}

        for ticker in tickers:
            try:
                files = self.download_all_for_ticker(
                    ticker,
                    form_types=form_types,
                    start_date=start_date,
                    end_date=end_date,
                    skip_existing=skip_existing
                )
                results[ticker] = files
            except Exception as e:
                logger.error(f"Failed to download filings for {ticker}: {e}")
                results[ticker] = []

        total_downloaded = sum(len(files) for files in results.values())
        logger.info(f"Bulk download complete. Total filings downloaded: {total_downloaded}")

        return results


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Download SEC EDGAR 10-K and 10-Q filings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download last 3 months of filings for Apple
  %(prog)s -t AAPL

  # Download all historical filings for Microsoft
  %(prog)s -t MSFT --all

  # Download only 10-K filings for Google
  %(prog)s -t GOOGL --forms 10-K

  # Download for multiple tickers
  %(prog)s -t AAPL MSFT GOOGL

  # Download with custom date range
  %(prog)s -t AAPL --from 2020-01-01 --to 2024-12-31

  # Specify custom output directory
  %(prog)s -t AAPL -o ./my_filings
        """
    )

    parser.add_argument(
        '-t', '--tickers',
        nargs='+',
        required=True,
        help='Stock ticker symbols (e.g., AAPL MSFT GOOGL)'
    )

    parser.add_argument(
        '-o', '--output-dir',
        default=DEFAULT_OUTPUT_DIR,
        help=f'Output directory (default: {DEFAULT_OUTPUT_DIR})'
    )

    parser.add_argument(
        '--forms',
        nargs='+',
        choices=['10-K', '10-Q', '10-K/A', '10-Q/A'],
        default=None,
        help='Form types to download (default: all 10-K and 10-Q variants)'
    )

    parser.add_argument(
        '--all',
        action='store_true',
        help='Download all historical filings (default: last 3 months only)'
    )

    parser.add_argument(
        '--from',
        dest='from_date',
        help='Start date in YYYY-MM-DD format (default: 3 months ago unless --all is used)'
    )

    parser.add_argument(
        '--to',
        dest='to_date',
        help='End date in YYYY-MM-DD format (default: today)'
    )

    parser.add_argument(
        '--email',
        default=DEFAULT_USER_EMAIL,
        help=f'Email for User-Agent header (default: {DEFAULT_USER_EMAIL})'
    )

    parser.add_argument(
        '-d', '--delay',
        type=float,
        default=REQUEST_DELAY,
        help=f'Delay between requests in seconds (default: {REQUEST_DELAY})'
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

    # Calculate date range
    end_date = datetime.now()
    if args.to_date:
        end_date = datetime.strptime(args.to_date, "%Y-%m-%d")

    start_date = None
    if args.all:
        # Download all historical filings
        start_date = None
    elif args.from_date:
        start_date = datetime.strptime(args.from_date, "%Y-%m-%d")
    else:
        # Default: last 3 months
        start_date = end_date - timedelta(days=90)

    # Log date range
    if start_date:
        logger.info(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    else:
        logger.info(f"Downloading all historical filings up to {end_date.strftime('%Y-%m-%d')}")

    # Create downloader
    downloader = SECEdgarDownloader(
        output_dir=args.output_dir,
        user_email=args.email,
        delay=args.delay,
        verbose=args.verbose
    )

    # Download filings
    try:
        results = downloader.download_bulk(
            tickers=args.tickers,
            form_types=args.forms,
            start_date=start_date,
            end_date=end_date,
            skip_existing=not args.no_skip
        )

        # Print summary
        print("\n" + "="*60)
        print("DOWNLOAD SUMMARY")
        print("="*60)
        for ticker, files in results.items():
            print(f"{ticker}: {len(files)} filings downloaded")
        print("="*60)

    except KeyboardInterrupt:
        logger.info("\nDownload interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Download failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

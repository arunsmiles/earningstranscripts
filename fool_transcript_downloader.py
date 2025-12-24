"""
Motley Fool Earnings Transcript Downloader v2

This module downloads all earnings transcripts from The Motley Fool website
and stores them with the naming convention: <stockticker>_<year>_<quarter>_earningstranscript_from_fool.md

Improvements in v2:
- Shows file size in KB when saving
- Detects incomplete files (<2KB) and attempts to follow redirects
- Adds Source: <url> at the bottom of each file
- Supports month-level granularity for sitemap crawling
"""

import os
import re
import time
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_URL = "https://www.fool.com"
TRANSCRIPTS_URL = "https://www.fool.com/earnings-call-transcripts/"
SITEMAP_INDEX_URL = "https://www.fool.com/sitemap/"
DEFAULT_OUTPUT_DIR = "transcripts"
MIN_CONTENT_SIZE_KB = 2.0  # Files smaller than this are likely incomplete


@dataclass
class TranscriptInfo:
    """Information about a single transcript."""
    url: str
    ticker: str
    year: str
    quarter: str
    company_name: str


class FoolTranscriptDownloader:
    """Downloads earnings transcripts from The Motley Fool."""

    def __init__(self, output_dir: str = DEFAULT_OUTPUT_DIR, headless: bool = True, browser: str = "auto"):
        """
        Initialize the downloader.

        Args:
            output_dir: Directory to save transcripts
            headless: Run browser in headless mode
            browser: Browser to use - "auto" (try Chrome then Edge), "chrome", or "edge"
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.browser = browser.lower()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

    def _create_driver(self):
        """Create a Selenium driver with automatic driver management.

        Tries Chrome first, falls back to Edge (pre-installed on Windows).
        """
        if self.browser == "chrome":
            return self._create_chrome_driver()
        elif self.browser == "edge":
            return self._create_edge_driver()

        # Auto mode: try Chrome first, fall back to Edge
        try:
            return self._create_chrome_driver()
        except (WebDriverException, Exception) as e:
            logger.warning(f"Chrome not available: {e}")
            logger.info("Falling back to Microsoft Edge...")

        # Fall back to Edge (comes pre-installed on Windows)
        return self._create_edge_driver()

    def _create_chrome_driver(self) -> webdriver.Chrome:
        """Create a Chrome driver using Selenium's built-in driver management."""
        options = ChromeOptions()
        if self.headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

        # Selenium 4.6+ has built-in driver management
        return webdriver.Chrome(options=options)

    def _create_edge_driver(self) -> webdriver.Edge:
        """Create an Edge driver using Selenium's built-in driver management."""
        options = EdgeOptions()
        if self.headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

        # Selenium 4.6+ has built-in driver management
        return webdriver.Edge(options=options)

    def get_transcript_urls(self, max_pages: int = 50) -> list[TranscriptInfo]:
        """
        Scrape all transcript URLs from the main listing page.

        Args:
            max_pages: Maximum number of times to click "Load More"

        Returns:
            List of TranscriptInfo objects
        """
        logger.info("Starting to scrape transcript URLs...")
        driver = self._create_driver()
        transcripts = []

        try:
            driver.get(TRANSCRIPTS_URL)
            time.sleep(5)  # Initial page load - give React time to render

            # Multiple selectors to try for the Load More button
            load_more_selectors = [
                (By.XPATH, "//button[contains(text(), 'Load More')]"),
                (By.XPATH, "//button[contains(text(), 'Load more')]"),
                (By.XPATH, "//button[contains(text(), 'LOAD MORE')]"),
                (By.XPATH, "//*[contains(text(), 'Load More') and (self::button or self::a)]"),
                (By.CSS_SELECTOR, "button[class*='load']"),
                (By.CSS_SELECTOR, "button[class*='more']"),
                (By.CSS_SELECTOR, "[data-testid*='load-more']"),
            ]

            load_more_clicks = 0
            while load_more_clicks < max_pages:
                # Scroll to bottom first to trigger any lazy loading
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)

                load_more_btn = None
                for selector_type, selector in load_more_selectors:
                    try:
                        load_more_btn = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((selector_type, selector))
                        )
                        if load_more_btn:
                            logger.debug(f"Found button with selector: {selector}")
                            break
                    except TimeoutException:
                        continue

                if not load_more_btn:
                    logger.info("No more 'Load More' button found or page fully loaded")
                    break

                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", load_more_btn)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", load_more_btn)
                    load_more_clicks += 1
                    logger.info(f"Clicked 'Load More' {load_more_clicks} times...")
                    time.sleep(3)  # Wait for content to load
                except Exception as e:
                    logger.warning(f"Error clicking Load More: {e}")
                    break

            # Parse all transcript links from the page
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            transcripts = self._parse_transcript_links(soup)
            logger.info(f"Found {len(transcripts)} transcripts")

        finally:
            driver.quit()

        return transcripts

    def get_transcript_urls_from_sitemap(self, start_year: int = 2020, end_year: int = 2025,
                                          start_month: int = 1, end_month: int = 12) -> list[TranscriptInfo]:
        """
        Scrape transcript URLs from the sitemap archives.

        Args:
            start_year: Year to start searching from
            end_year: Year to end searching at
            start_month: Month to start from (1-12), applies to start_year
            end_month: Month to end at (1-12), applies to end_year

        Returns:
            List of TranscriptInfo objects
        """
        logger.info(f"Crawling sitemaps from {start_year}/{start_month:02d} to {end_year}/{end_month:02d}...")
        transcripts = []

        # Crawl monthly sitemaps
        for year in range(start_year, end_year + 1):
            m_start = start_month if year == start_year else 1
            m_end = end_month if year == end_year else 12

            for month in range(m_start, m_end + 1):
                # Skip future months
                from datetime import datetime
                now = datetime.now()
                if year == now.year and month > now.month:
                    break

                sitemap_url = f"{SITEMAP_INDEX_URL}{year}/{month:02d}"
                logger.info(f"Fetching sitemap: {sitemap_url}")

                try:
                    response = self.session.get(sitemap_url, timeout=30)
                    if response.status_code != 200:
                        logger.debug(f"Sitemap not found: {sitemap_url}")
                        continue

                    # Parse XML sitemap
                    soup = BeautifulSoup(response.text, 'xml')
                    urls = soup.find_all('loc')

                    for url_elem in urls:
                        url = url_elem.get_text(strip=True)
                        if '/earnings/call-transcripts/' in url and 'earnings-call-transcript' in url:
                            info = self._parse_transcript_url(url)
                            if info and not any(t.url == info.url for t in transcripts):
                                transcripts.append(info)

                    logger.info(f"Found {len(transcripts)} transcripts so far...")
                    time.sleep(0.5)  # Be respectful

                except requests.RequestException as e:
                    logger.warning(f"Failed to fetch {sitemap_url}: {e}")
                    continue

        logger.info(f"Total transcripts found from sitemaps: {len(transcripts)}")
        return transcripts

    def _parse_transcript_url(self, url: str) -> Optional[TranscriptInfo]:
        """Parse a transcript URL and extract metadata."""
        # Pattern: company-name-TICKER-qN-YYYY-earnings-call-transcript
        url_match = re.search(r'/([^/]+)-([a-zA-Z]+)-q([1-4])-(\d{4})-earnings-call-transcript', url, re.IGNORECASE)

        if url_match:
            company_slug = url_match.group(1)
            ticker = url_match.group(2).upper()
            quarter = f"Q{url_match.group(3)}"
            year = url_match.group(4)

            # Clean up company name from slug
            company_name = company_slug.replace('-', ' ').title()

            return TranscriptInfo(
                url=url,
                ticker=ticker,
                year=year,
                quarter=quarter,
                company_name=company_name
            )
        return None

    def _parse_transcript_links(self, soup: BeautifulSoup) -> list[TranscriptInfo]:
        """Parse transcript links from the BeautifulSoup object."""
        transcripts = []

        # Find all transcript article links
        # Links typically follow pattern: /earnings/call-transcripts/YYYY/MM/DD/company-ticker-qN-YYYY-earnings-call-transcript/
        transcript_pattern = re.compile(r'/earnings/call-transcripts/\d{4}/\d{2}/\d{2}/.*earnings-call-transcript')

        for link in soup.find_all('a', href=transcript_pattern):
            href = link.get('href', '')
            if not href:
                continue

            full_url = urljoin(BASE_URL, href)

            # Extract ticker, year, quarter from URL
            # Pattern: company-name-TICKER-qN-YYYY-earnings-call-transcript
            url_match = re.search(r'/([^/]+)-([a-zA-Z]+)-q([1-4])-(\d{4})-earnings-call-transcript', href, re.IGNORECASE)

            if url_match:
                company_slug = url_match.group(1)
                ticker = url_match.group(2).upper()
                quarter = f"Q{url_match.group(3)}"
                year = url_match.group(4)

                # Clean up company name from slug
                company_name = company_slug.replace('-', ' ').title()

                info = TranscriptInfo(
                    url=full_url,
                    ticker=ticker,
                    year=year,
                    quarter=quarter,
                    company_name=company_name
                )

                # Avoid duplicates
                if not any(t.url == info.url for t in transcripts):
                    transcripts.append(info)

        return transcripts

    def _find_redirect_url(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """Look for redirect URLs in page content."""
        # Check meta refresh
        meta = soup.find('meta', attrs={'http-equiv': re.compile(r'refresh', re.I)})
        if meta:
            content = meta.get('content', '')
            if 'url=' in content.lower():
                redirect_url = content.split('url=')[-1].strip().strip('"\'')
                if redirect_url and redirect_url != current_url:
                    return redirect_url if redirect_url.startswith('http') else urljoin(BASE_URL, redirect_url)

        # Check for canonical link
        canonical = soup.find('link', rel='canonical')
        if canonical:
            href = canonical.get('href', '')
            if href and href != current_url and 'earnings-call-transcript' in href:
                return href if href.startswith('http') else urljoin(BASE_URL, href)

        # Check for transcript links in the page
        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            if 'earnings-call-transcript' in href and href != current_url:
                full_url = href if href.startswith('http') else urljoin(BASE_URL, href)
                if full_url != current_url:
                    return full_url

        return None

    def download_transcript(self, info: TranscriptInfo, max_redirects: int = 3) -> Tuple[Optional[str], str]:
        """
        Download a single transcript and return its content as markdown.
        Follows redirects if content is too small.

        Args:
            info: TranscriptInfo object with transcript details
            max_redirects: Maximum number of redirects to follow

        Returns:
            Tuple of (content as markdown string or None, final URL used)
        """
        url = info.url

        for attempt in range(max_redirects):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')
                content = self._extract_transcript_content(soup, info, url)

                size_kb = len(content.encode('utf-8')) / 1024

                if size_kb < MIN_CONTENT_SIZE_KB:
                    # Content too small, look for redirect
                    redirect_url = self._find_redirect_url(soup, url)
                    if redirect_url:
                        logger.warning(f"Content too small ({size_kb:.1f}KB), following redirect: {redirect_url}")
                        url = redirect_url
                        continue
                    else:
                        logger.warning(f"Content small ({size_kb:.1f}KB) but no redirect found for {url}")

                return content, url

            except requests.RequestException as e:
                logger.error(f"Failed to download {url}: {e}")
                return None, url

        logger.error(f"Max redirects reached for {info.url}")
        return None, url

    def _extract_transcript_content(self, soup: BeautifulSoup, info: TranscriptInfo, source_url: str) -> str:
        """Extract and format transcript content as markdown."""
        content_parts = []

        # Add header
        content_parts.append(f"# {info.company_name} ({info.ticker}) - {info.quarter} {info.year} Earnings Call Transcript")
        content_parts.append("")
        content_parts.append("---")
        content_parts.append("")

        # Try to find the main article content
        # The transcript is typically in an article or main content section
        article = soup.find('article') or soup.find('main') or soup.find('div', class_=re.compile(r'article|content|transcript', re.I))

        if not article:
            # Fallback: try to find content div
            article = soup.find('div', {'id': re.compile(r'content|article', re.I)})

        if not article:
            article = soup.body

        if article:
            # Get all text content, preserving structure
            for element in article.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'blockquote']):
                text = element.get_text(strip=True)
                if not text:
                    continue

                # Skip navigation and footer elements
                if element.find_parent(['nav', 'footer', 'aside']):
                    continue

                # Format based on element type
                tag_name = element.name
                if tag_name in ['h1', 'h2']:
                    content_parts.append(f"## {text}")
                    content_parts.append("")
                elif tag_name in ['h3', 'h4']:
                    content_parts.append(f"### {text}")
                    content_parts.append("")
                elif tag_name in ['h5', 'h6']:
                    content_parts.append(f"#### {text}")
                    content_parts.append("")
                elif tag_name == 'p':
                    # Check if this looks like a speaker name (usually bold or followed by --)
                    if element.find('strong') or element.find('b'):
                        bold_text = element.find(['strong', 'b'])
                        if bold_text:
                            speaker = bold_text.get_text(strip=True)
                            remaining = text.replace(speaker, '', 1).strip()
                            if remaining.startswith('--') or remaining.startswith(':'):
                                remaining = remaining.lstrip('-:').strip()
                            content_parts.append(f"**{speaker}**")
                            if remaining:
                                content_parts.append(remaining)
                            content_parts.append("")
                        else:
                            content_parts.append(text)
                            content_parts.append("")
                    else:
                        content_parts.append(text)
                        content_parts.append("")
                elif tag_name in ['ul', 'ol']:
                    for li in element.find_all('li', recursive=False):
                        li_text = li.get_text(strip=True)
                        if li_text:
                            content_parts.append(f"- {li_text}")
                    content_parts.append("")
                elif tag_name == 'blockquote':
                    content_parts.append(f"> {text}")
                    content_parts.append("")

        # Clean up multiple blank lines
        content = '\n'.join(content_parts)
        content = re.sub(r'\n{3,}', '\n\n', content)

        # Add source link at bottom
        content = content.strip()
        content += f"\n\n---\n\nSource: {source_url}"

        return content

    def save_transcript(self, info: TranscriptInfo, content: str) -> Tuple[Path, float]:
        """
        Save transcript to file with proper naming convention.

        Args:
            info: TranscriptInfo object
            content: Transcript content as markdown

        Returns:
            Tuple of (Path to saved file, size in KB)
        """
        filename = f"{info.ticker}_{info.year}_{info.quarter}_earningstranscript_from_fool.md"
        filepath = self.output_dir / filename

        filepath.write_text(content, encoding='utf-8')
        size_kb = len(content.encode('utf-8')) / 1024
        logger.info(f"Saved: {filepath} ({size_kb:.1f}KB)")

        return filepath, size_kb

    def download_all(self, max_pages: int = 50, delay: float = 1.0, use_sitemap: bool = False,
                     start_year: int = 2020, end_year: int = 2025,
                     start_month: int = 1, end_month: int = 12) -> list[Path]:
        """
        Download all available transcripts.

        Args:
            max_pages: Maximum number of "Load More" clicks (for page scraping mode)
            delay: Delay between downloads (seconds) to be respectful
            use_sitemap: If True, use sitemap crawling instead of page scraping
            start_year: Start year for sitemap crawling
            end_year: End year for sitemap crawling
            start_month: Start month for sitemap crawling (1-12)
            end_month: End month for sitemap crawling (1-12)

        Returns:
            List of paths to saved files
        """
        if use_sitemap:
            transcripts = self.get_transcript_urls_from_sitemap(
                start_year=start_year, end_year=end_year,
                start_month=start_month, end_month=end_month
            )
        else:
            transcripts = self.get_transcript_urls(max_pages=max_pages)

        saved_files = []
        skipped_small = []

        for i, info in enumerate(transcripts, 1):
            logger.info(f"Downloading {i}/{len(transcripts)}: {info.ticker} {info.quarter} {info.year}")

            # Check if already downloaded
            filename = f"{info.ticker}_{info.year}_{info.quarter}_earningstranscript_from_fool.md"
            filepath = self.output_dir / filename
            if filepath.exists():
                size_kb = filepath.stat().st_size / 1024
                logger.info(f"Already exists ({size_kb:.1f}KB), skipping: {filename}")
                saved_files.append(filepath)
                continue

            content, final_url = self.download_transcript(info)
            if content:
                saved_path, size_kb = self.save_transcript(info, content)
                saved_files.append(saved_path)

                if size_kb < MIN_CONTENT_SIZE_KB:
                    skipped_small.append((saved_path, size_kb))

            # Be respectful with delays between requests
            if i < len(transcripts):
                time.sleep(delay)

        logger.info(f"Download complete! Saved {len(saved_files)} transcripts to {self.output_dir}")

        if skipped_small:
            logger.warning(f"Warning: {len(skipped_small)} files are smaller than {MIN_CONTENT_SIZE_KB}KB and may be incomplete:")
            for path, size in skipped_small:
                logger.warning(f"  - {path.name} ({size:.1f}KB)")

        return saved_files


def main():
    """Main entry point for the downloader."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Download earnings transcripts from The Motley Fool'
    )
    parser.add_argument(
        '-o', '--output-dir',
        default=DEFAULT_OUTPUT_DIR,
        help=f'Output directory for transcripts (default: {DEFAULT_OUTPUT_DIR})'
    )
    parser.add_argument(
        '-m', '--max-pages',
        type=int,
        default=50,
        help='Maximum number of "Load More" clicks (default: 50)'
    )
    parser.add_argument(
        '-d', '--delay',
        type=float,
        default=1.0,
        help='Delay between downloads in seconds (default: 1.0)'
    )
    parser.add_argument(
        '--no-headless',
        action='store_true',
        help='Run browser in visible mode (for debugging)'
    )
    parser.add_argument(
        '-b', '--browser',
        choices=['auto', 'chrome', 'edge'],
        default='auto',
        help='Browser to use: auto (try Chrome then Edge), chrome, or edge (default: auto)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--sitemap',
        action='store_true',
        help='Use sitemap crawling instead of page scraping (more comprehensive)'
    )
    parser.add_argument(
        '--start-year',
        type=int,
        default=2020,
        help='Start year for sitemap crawling (default: 2020)'
    )
    parser.add_argument(
        '--end-year',
        type=int,
        default=2025,
        help='End year for sitemap crawling (default: 2025)'
    )
    parser.add_argument(
        '--start-month',
        type=int,
        default=1,
        choices=range(1, 13),
        help='Start month for sitemap crawling (default: 1)'
    )
    parser.add_argument(
        '--end-month',
        type=int,
        default=12,
        choices=range(1, 13),
        help='End month for sitemap crawling (default: 12)'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    downloader = FoolTranscriptDownloader(
        output_dir=args.output_dir,
        headless=not args.no_headless,
        browser=args.browser
    )

    downloader.download_all(
        max_pages=args.max_pages,
        delay=args.delay,
        use_sitemap=args.sitemap,
        start_year=args.start_year,
        end_year=args.end_year,
        start_month=args.start_month,
        end_month=args.end_month
    )


if __name__ == '__main__':
    main()

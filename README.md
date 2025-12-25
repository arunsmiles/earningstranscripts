# Earnings Transcripts and SEC Filings Downloader

A Python toolkit for downloading:
- 📄 **Earnings call transcripts** from The Motley Fool
- 📊 **SEC EDGAR filings** (10-K, 10-Q) for public companies

## Features

### Motley Fool Transcript Downloader
- Download earnings call transcripts from The Motley Fool
- Supports sitemap crawling and page scraping methods
- Converts HTML to clean markdown format
- Smart ticker validation to prevent data corruption
- Selenium-based rendering for JavaScript content

### SEC EDGAR Filing Downloader
- Download 10-K (annual) and 10-Q (quarterly) filings from SEC EDGAR
- Uses official SEC API (free, no API key required)
- Downloads multiple formats per filing:
  - Primary HTML document
  - Complete submission text file (contains all exhibits)
  - XBRL financial data files
- Automatic fiscal year and quarter calculation
- Supports amendments (10-K/A, 10-Q/A)
- Configurable date ranges (default: last 3 months)
- Two download modes:
  - **Individual mode**: Download specific tickers via API
  - **Bulk mode**: Download from SEC's nightly bulk data (~2GB, all companies)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### SEC EDGAR Filings

**Download last 3 months of filings for Apple:**
```bash
python sec_edgar_downloader.py -t AAPL
```

**Download all historical filings:**
```bash
python sec_edgar_downloader.py -t AAPL --all
```

**Download only 10-K filings:**
```bash
python sec_edgar_downloader.py -t AAPL --forms 10-K
```

**Download for multiple tickers:**
```bash
python sec_edgar_downloader.py -t AAPL MSFT GOOGL
```

**Download with custom date range:**
```bash
python sec_edgar_downloader.py -t AAPL --from 2020-01-01 --to 2024-12-31
```

**Specify output directory:**
```bash
python sec_edgar_downloader.py -t AAPL -o ./my_filings
```

**Full options:**
```bash
python sec_edgar_downloader.py --help
```

### SEC EDGAR Bulk Download (Recommended for Many Tickers)

**Step 1: Download SEC's bulk data (once per day):**
```bash
python sec_bulk_downloader.py --download-bulk-data
```

**Step 2: Download filings for tickers from a file:**
```bash
python sec_bulk_downloader.py --ticker-file my_tickers.txt
```

**Download top N companies from ranked list:**
```bash
python sec_bulk_downloader.py --ticker-file sp500.txt --top 100
```

**Download all companies (WARNING: 10,000+ companies, may take days):**
```bash
python sec_bulk_downloader.py --all-tickers --from 2024-01-01
```

**Download only 10-K filings:**
```bash
python sec_bulk_downloader.py --ticker-file my_tickers.txt --forms 10-K
```

**Ticker file format** (one ticker per line):
```
# Comments start with #
AAPL
MSFT
GOOGL
```

**Features:**
- Downloads SEC's nightly bulk data file (~2GB, all companies)
- Much faster than API for multiple companies
- Progress tracking with SQLite database
- Automatic resume on interruption
- Respects SEC rate limits

### Motley Fool Transcripts

**Download current month transcripts:**
```bash
python fool_transcript_downloader.py
```

**Download specific ticker:**
```bash
python fool_transcript_downloader.py -t AAPL
```

**Download date range using sitemap:**
```bash
python fool_transcript_downloader.py --from 2024-01 --to 2024-12
```

**Use page scraping method:**
```bash
python fool_transcript_downloader.py --page-scrape --max-pages 50
```

## File Naming Convention

### SEC Filings
- **Quarterly reports:** `secfilings\<TICKER>_<YEAR>_<QUARTER>_<FORM>.<ext>`
  - HTML: `secfilings\AAPL_2024_Q3_10-Q.html`
  - Complete submission: `secfilings\AAPL_2024_Q3_10-Q_complete.txt`
  - XBRL files: `secfilings\AAPL_2024_Q3_10-Q_xbrl\*.xml`

- **Annual reports:** `secfilings\<TICKER>_<YEAR>_FY_<FORM>.<ext>`
  - HTML: `secfilings\MSFT_2023_FY_10-K.html`
  - Complete submission: `secfilings\MSFT_2023_FY_10-K_complete.txt`
  - XBRL files: `secfilings\MSFT_2023_FY_10-K_xbrl\*.xml`

### Fool Transcripts
- `transcripts\<TICKER>_<YEAR>_<QUARTER>_earningstranscript_from_fool.md`
  - Example: `transcripts\AAPL_2024_Q4_earningstranscript_from_fool.md`

## Output Structure

```
earningstranscripts/
├── secfilings/                      # SEC EDGAR filings
│   ├── AAPL_2024_Q1_10-Q.html       # Primary HTML document
│   ├── AAPL_2024_Q1_10-Q_complete.txt  # Complete submission (all exhibits)
│   ├── AAPL_2024_Q1_10-Q_xbrl/      # XBRL financial data
│   │   ├── aapl-20240330.xml
│   │   ├── aapl-20240330.xsd
│   │   └── ...
│   ├── AAPL_2024_Q2_10-Q.html
│   ├── AAPL_2024_Q2_10-Q_complete.txt
│   ├── AAPL_2024_Q2_10-Q_xbrl/
│   ├── AAPL_2023_FY_10-K.html
│   ├── AAPL_2023_FY_10-K_complete.txt
│   └── AAPL_2023_FY_10-K_xbrl/
└── transcripts/                     # Motley Fool transcripts
    ├── AAPL_2024_Q1_earningstranscript_from_fool.md
    └── AAPL_2024_Q2_earningstranscript_from_fool.md
```

## Requirements

- Python 3.7+
- requests
- beautifulsoup4
- selenium
- lxml

## SEC EDGAR API

This tool uses the official SEC EDGAR API at `data.sec.gov`, which:
- Requires no API key or authentication
- Has a rate limit of 10 requests/second
- Requires a User-Agent header with email (configured via `--email`)
- Provides real-time updated filing data

## License

MIT
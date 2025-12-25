# Usage Guide: earnings-data-client

## Table of Contents
1. [Installation](#installation)
2. [Configuration](#configuration)
3. [Python API Usage](#python-api-usage)
4. [Command-Line Interface](#command-line-interface)
5. [Integration with Other Projects](#integration-with-other-projects)

---

## Installation

### Install from Source (Development)

```bash
# Clone the repository
git clone https://github.com/arunsmiles/earningstranscripts.git
cd earningstranscripts

# Install in editable mode
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

### Install from PyPI (when published)

```bash
pip install earnings-data-client
```

---

## Configuration

### Data Directory Configuration

All data (transcripts, SEC filings, cache) is stored in a configurable base directory with the following structure:

```
{data_dir}/
├── transcripts/       # Earnings call transcripts
├── secfilings/        # SEC filings (10-K, 10-Q, etc.)
├── cache/             # SEC bulk data cache
└── metadata.db        # Metadata index database (coming soon)
```

### Configuration Priority (Highest to Lowest)

1. **Explicit parameter** - Pass `config` or `data_dir` to downloader classes
2. **Environment variable** - Set `EARNINGS_DATA_DIR`
3. **Config file** - `~/.earnings_data/config.json`
4. **Default** - `~/.earnings_data`

### Setting the Data Directory

#### Method 1: Environment Variable (Recommended for Projects)

```bash
export EARNINGS_DATA_DIR=/path/to/your/data
```

Add to your `.bashrc` or `.zshrc` for persistence.

#### Method 2: Config File

```bash
# Set data directory and save to config file
earnings-config --set-dir /path/to/your/data

# View current configuration
earnings-config --show

# Initialize directory structure
earnings-config --init
```

#### Method 3: In Python Code

```python
from config import Config, set_data_directory

# Option A: Set globally
set_data_directory('/path/to/your/data', save=True)

# Option B: Create a config instance
config = Config('/path/to/your/data')
```

---

## Python API Usage

### Basic Usage with Global Config

```python
from fool_transcript_downloader import FoolTranscriptDownloader
from sec_edgar_downloader import SECEdgarDownloader
from sec_bulk_downloader import SECBulkDownloader

# All downloaders will use the default config (~/.earnings_data)
# or the config set via environment variable or config file

# Download transcripts
fool = FoolTranscriptDownloader()
fool.download_all(ticker="AAPL")

# Download SEC filings
sec = SECEdgarDownloader()
sec.download_all_for_ticker("AAPL", form_types=["10-K", "10-Q"])

# Bulk download
bulk = SECBulkDownloader()
bulk.download_for_tickers(["AAPL", "MSFT", "GOOGL"])
```

### Usage with Explicit Config

```python
from config import Config
from fool_transcript_downloader import FoolTranscriptDownloader
from sec_edgar_downloader import SECEdgarDownloader
from sec_bulk_downloader import SECBulkDownloader

# Create a config pointing to your custom data directory
config = Config('/path/to/your/project/data')

# Pass config to all downloaders
fool = FoolTranscriptDownloader(config=config)
sec = SECEdgarDownloader(config=config)
bulk = SECBulkDownloader(config=config)

# Now all writes go to /path/to/your/project/data/
```

### Usage with data_dir Parameter

```python
# Simplest approach - just pass data_dir
fool = FoolTranscriptDownloader(data_dir='/path/to/your/data')
sec = SECEdgarDownloader(data_dir='/path/to/your/data')
bulk = SECBulkDownloader(data_dir='/path/to/your/data')
```

### Accessing Configuration

```python
from config import get_config

# Get the current global config
config = get_config()

print(f"Data directory: {config.data_dir}")
print(f"Transcripts: {config.transcripts_dir}")
print(f"SEC filings: {config.secfilings_dir}")
print(f"Cache: {config.cache_dir}")
print(f"Metadata DB: {config.metadata_db}")
```

---

## Command-Line Interface

All CLI tools now support the `--data-dir` parameter:

### Configuration Management

```bash
# Show current configuration
earnings-config --show

# Set data directory
earnings-config --set-dir /path/to/data

# Initialize directory structure
earnings-config --init
```

### Download Transcripts

```bash
# Using default config
earnings-download-transcripts -t AAPL --from 2024-01 --to 2024-12

# Using custom data directory
earnings-download-transcripts --data-dir /path/to/data -t AAPL

# Using environment variable
export EARNINGS_DATA_DIR=/path/to/data
earnings-download-transcripts -t AAPL
```

### Download SEC Filings

```bash
# Using default config
earnings-download-sec -t AAPL MSFT --forms 10-K 10-Q

# Using custom data directory
earnings-download-sec --data-dir /path/to/data -t AAPL MSFT

# Download historical data
earnings-download-sec --data-dir /path/to/data -t AAPL --all
```

### Bulk Download

```bash
# Using default config
earnings-download-bulk --ticker-file tickers.txt

# Using custom data directory
earnings-download-bulk --data-dir /path/to/data --ticker-file tickers.txt

# Download for top 100 companies
earnings-download-bulk --data-dir /path/to/data --ticker-file sp500.txt --top 100
```

---

## Integration with Other Projects

### Scenario: Agentic Workflow Orchestrator

Your agentic workflow project can consume this package and access data from a shared location.

#### Option 1: Shared Data Directory (Recommended)

```python
# In your agentic workflow project
import os
from fool_transcript_downloader import FoolTranscriptDownloader
from sec_edgar_downloader import SECEdgarDownloader
from config import Config

# Set the shared data directory
SHARED_DATA_DIR = "/data/earnings"  # Common location for both projects
os.environ['EARNINGS_DATA_DIR'] = SHARED_DATA_DIR

# Now downloaders will automatically use this directory
fool = FoolTranscriptDownloader()
sec = SECEdgarDownloader()

# Download new data if needed
fool.download_all(ticker="AAPL")
sec.download_all_for_ticker("AAPL")

# Read the data directly from the shared location
import glob
transcripts = glob.glob(f"{SHARED_DATA_DIR}/transcripts/AAPL_*.md")
filings = glob.glob(f"{SHARED_DATA_DIR}/secfilings/AAPL_*.html")
```

#### Option 2: Config Object Pattern

```python
# Create a centralized config module in your project
# my_project/earnings_config.py
from config import Config

# Single source of truth for data location
EARNINGS_CONFIG = Config('/data/earnings')
```

```python
# In your workflow modules
from my_project.earnings_config import EARNINGS_CONFIG
from fool_transcript_downloader import FoolTranscriptDownloader

# All modules use the same config
downloader = FoolTranscriptDownloader(config=EARNINGS_CONFIG)
```

#### Option 3: Environment Variable (Simplest)

```bash
# In your shell profile or .env file
export EARNINGS_DATA_DIR=/data/earnings
```

```python
# All Python scripts automatically use this directory
from fool_transcript_downloader import FoolTranscriptDownloader

# No config needed - uses environment variable
downloader = FoolTranscriptDownloader()
```

### Example: Query API Integration

```python
from pathlib import Path
from config import get_config
import glob

class EarningsDataProvider:
    """Simple data provider for your agentic workflow"""

    def __init__(self, data_dir=None):
        from config import Config
        self.config = Config(data_dir) if data_dir else get_config()

    def get_transcripts(self, ticker, year=None, quarter=None):
        """Get transcripts for a ticker"""
        pattern = f"{ticker}_"
        if year:
            pattern += f"{year}_"
        if quarter:
            pattern += f"{quarter}_"
        pattern += "*.md"

        files = glob.glob(str(self.config.transcripts_dir / pattern))
        return [Path(f) for f in files]

    def get_filings(self, ticker, form_type=None):
        """Get SEC filings for a ticker"""
        pattern = f"{ticker}_*"
        if form_type:
            pattern += f"_{form_type}"
        pattern += ".html"

        files = glob.glob(str(self.config.secfilings_dir / pattern))
        return [Path(f) for f in files]

    def read_transcript(self, file_path):
        """Read transcript content"""
        return Path(file_path).read_text()

    def read_filing(self, file_path):
        """Read filing content"""
        return Path(file_path).read_text()

# Usage in your agentic workflow
provider = EarningsDataProvider(data_dir="/data/earnings")
transcripts = provider.get_transcripts("AAPL", year=2024)
content = provider.read_transcript(transcripts[0])
```

---

## Backward Compatibility

The package maintains backward compatibility with the old `output_dir` and `cache_dir` parameters:

```python
# Old way (still works, but deprecated)
fool = FoolTranscriptDownloader(output_dir="./my_transcripts")
sec = SECEdgarDownloader(output_dir="./my_filings")
bulk = SECBulkDownloader(cache_dir="./my_cache", output_dir="./my_filings")

# New way (recommended)
fool = FoolTranscriptDownloader(data_dir="./my_data")
sec = SECEdgarDownloader(data_dir="./my_data")
bulk = SECBulkDownloader(data_dir="./my_data")
```

When using the old parameters, a deprecation warning will be logged.

---

## Best Practices

### 1. **Single Data Directory per Environment**

Use one data directory per environment (dev, staging, prod):

```bash
# Development
export EARNINGS_DATA_DIR=~/.earnings_data

# Production
export EARNINGS_DATA_DIR=/mnt/data/earnings
```

### 2. **Shared Data Across Projects**

For multiple projects accessing the same data:

```bash
# In your shell profile
export EARNINGS_DATA_DIR=/data/shared/earnings

# Or in a shared config file
echo '{"data_dir": "/data/shared/earnings"}' > ~/.earnings_data/config.json
```

### 3. **Version Control**

Don't commit the data directory to git. Add to `.gitignore`:

```gitignore
# Data directories
transcripts/
secfilings/
.sec_cache/
*.db

# Or if using custom location
/my_data/
```

### 4. **Testing**

Use temporary directories for testing:

```python
import tempfile
from config import Config

with tempfile.TemporaryDirectory() as tmpdir:
    config = Config(tmpdir)
    downloader = FoolTranscriptDownloader(config=config)
    # Test operations...
```

---

## Troubleshooting

### Check Current Configuration

```bash
earnings-config --show
```

```python
from config import get_config
config = get_config()
print(config)
```

### Verify Data Directory

```python
from config import get_config
config = get_config()

print(f"Data directory exists: {config.data_dir.exists()}")
print(f"Transcripts dir: {config.transcripts_dir}")
print(f"Is writable: {os.access(config.data_dir, os.W_OK)}")
```

### Reset to Defaults

```bash
# Remove custom config
rm ~/.earnings_data/config.json

# Unset environment variable
unset EARNINGS_DATA_DIR

# Now uses default: ~/.earnings_data
earnings-config --show
```

---

## Next Steps

- Add metadata indexing for fast queries (coming soon)
- Implement query client for per-ticker and aggregate queries
- Add REST API wrapper for remote access (optional)

For questions or issues, please visit:
https://github.com/arunsmiles/earningstranscripts/issues

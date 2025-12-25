# Quick Start Guide

Get up and running with earnings-data-client in 5 minutes!

## Installation

```bash
# Install from source (development)
cd earningstranscripts
pip install -e .

# Or when published
pip install earnings-data-client
```

## Step 1: Configure Data Directory

Choose where to store your data:

```bash
# Option A: Use environment variable (recommended)
export EARNINGS_DATA_DIR=/path/to/your/data

# Option B: Use config command
earnings-config --set-dir /path/to/your/data

# Verify configuration
earnings-config --show
```

## Step 2: Download Some Data

Download transcripts and filings for a few companies:

```bash
# Download AAPL transcripts for 2024
earnings-download-transcripts -t AAPL --from 2024-01 --to 2024-12

# Download AAPL SEC filings (10-K, 10-Q)
earnings-download-sec -t AAPL MSFT --forms 10-K 10-Q
```

## Step 3: Index the Data

Create the metadata database for fast queries:

```bash
# Run the indexer
earnings-index

# View statistics
earnings-index --stats
```

## Step 4: Query the Data

### Command Line

```bash
# Query all data for AAPL
earnings-query -t AAPL

# Show statistics
earnings-query --stats

# List all tickers
earnings-query --tickers
```

### Python API

```python
from earnings_data_client import EarningsDataClient

# Create client
client = EarningsDataClient()

# Query transcripts
transcripts = client.query_transcripts(tickers="AAPL", year=2024)
for t in transcripts:
    print(f"{t.year} {t.quarter}: {t.file_path.name}")

# Query SEC filings
filings = client.query_filings(tickers="AAPL", form_types="10-K")
for f in filings:
    print(f"{f.year}: {f.form_type}")

# Get all data for a company
data = client.get_ticker_data("AAPL")
print(f"Transcripts: {len(data['transcripts'])}")
print(f"Filings: {len(data['filings'])}")

# Get statistics
stats = client.get_statistics()
print(f"Total files: {stats.total_files}")
print(f"Total size: {stats.total_size_mb:.2f} MB")

client.close()
```

## Integration with Your Project

### For Agentic Workflows

```python
# In your agentic workflow project
import os
from earnings_data_client import EarningsDataClient

# Set shared data directory
os.environ['EARNINGS_DATA_DIR'] = '/data/earnings'

# Create client in your agent
class MyAgent:
    def __init__(self):
        self.client = EarningsDataClient()

    def analyze_company(self, ticker):
        # Get data
        data = self.client.get_ticker_data(ticker)

        # Process with your LLM
        for transcript in data['transcripts']:
            content = transcript.load_content()
            # Send to LLM for analysis...

        return analysis_results
```

### Shared Data Directory

Both projects can access the same data:

```bash
# Set once in your shell profile
export EARNINGS_DATA_DIR=/data/shared/earnings
```

Now both projects automatically use the same data location!

## Common Workflows

### 1. Download and Query

```bash
# Download
earnings-download-transcripts -t AAPL MSFT GOOGL --from 2024-01
earnings-download-sec -t AAPL MSFT GOOGL

# Index
earnings-index

# Query
earnings-query -t AAPL --year 2024
```

### 2. Bulk Download for Analysis

```bash
# Create ticker list
echo "AAPL" > tickers.txt
echo "MSFT" >> tickers.txt
echo "GOOGL" >> tickers.txt

# Bulk download SEC filings
earnings-download-bulk --ticker-file tickers.txt --from 2023-01-01

# Index
earnings-index

# Query in Python
python3 -c "
from earnings_data_client import EarningsDataClient
client = EarningsDataClient()
stats = client.get_statistics()
print(f'Indexed {stats.total_files} files')
"
```

### 3. Aggregate Analysis

```python
from earnings_data_client import EarningsDataClient

client = EarningsDataClient()

# Get all tickers
tickers = client.get_tickers()

# Analyze each
for ticker in tickers[:10]:  # First 10
    data = client.get_ticker_data(ticker)
    print(f"{ticker}: {len(data['transcripts'])} transcripts, {len(data['filings'])} filings")

client.close()
```

## Next Steps

- See `examples/basic_usage.py` for more Python examples
- See `examples/agentic_workflow_integration.py` for integration patterns
- Read `USAGE.md` for comprehensive documentation
- Check `README.md` for full feature list

## Troubleshooting

### Data directory not found?

```bash
earnings-config --show  # Check current config
earnings-config --init  # Initialize directories
```

### No data when querying?

```bash
# Make sure you've downloaded data
earnings-download-transcripts -t AAPL --from 2024-01

# Make sure you've indexed
earnings-index
```

### Want to use a different data location?

```bash
# Set new location
export EARNINGS_DATA_DIR=/new/location

# Or use --data-dir flag
earnings-download-transcripts --data-dir /new/location -t AAPL
earnings-index --data-dir /new/location
```

## Help & Support

- Issues: https://github.com/arunsmiles/earningstranscripts/issues
- Examples: See `examples/` directory
- Documentation: See `USAGE.md`

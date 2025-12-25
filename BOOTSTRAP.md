# Bootstrap Guide - Setting Up With Existing Data

This guide will help you migrate your existing data and configure the package.

## Quick Setup (3 Steps)

### Step 1: Install Dependencies

```bash
# Install python-dotenv and other dependencies
pip install -r requirements.txt

# Or reinstall the package
pip install -e .
```

### Step 2: Configure Data Directory

Create a `.env` file in the project root:

```bash
# Copy the example
cp .env.example .env

# Edit .env and set your data directory
# For example:
echo "EARNINGS_DATA_DIR=./data" > .env

# Or use an absolute path:
echo "EARNINGS_DATA_DIR=/Users/arunath/earnings_data" > .env
```

**Example `.env` file:**
```bash
# Use project subdirectory
EARNINGS_DATA_DIR=./data

# OR use absolute path
# EARNINGS_DATA_DIR=/Users/arunath/earnings_data

# OR use home directory
# EARNINGS_DATA_DIR=~/.earnings_data
```

### Step 3: Migrate Your Existing Data

You have existing data in:
- `transcripts/` (726 files, ~37 MB)
- `secfilings/` (76+ files, ~1.7 GB)
- `.sec_cache/` (~8.4 GB)

**Option A: Dry Run First (Recommended)**

See what will happen without making changes:

```bash
python migrate_data.py --dry-run
```

**Option B: Migrate (Move)**

Move data to new location (saves disk space):

```bash
python migrate_data.py
```

**Option C: Migrate (Copy)**

Copy data to new location (safer, keeps original):

```bash
python migrate_data.py --copy
```

**Option D: Migrate to Custom Location**

```bash
python migrate_data.py --data-dir /path/to/your/data
```

---

## Step 4: Create Metadata Index

After migration, create the index for fast queries:

```bash
# Index all your data
earnings-index

# Check statistics
earnings-index --stats
```

Expected output:
```
============================================================
INDEXING STATISTICS
============================================================
Total files:     800+
Total size:      XX.XX MB
Date range:      2015 - 2025

By type:
  transcript        726
  filing            76+

Top 10 tickers:
  AAPL          XX
  MSFT          XX
  ...
============================================================
```

---

## Step 5: Test Queries

### Command Line

```bash
# Show statistics
earnings-query --stats

# List all tickers
earnings-query --tickers

# Query specific ticker
earnings-query -t AAPL

# Query with filters
earnings-query -t AAPL --year 2024
```

### Python

```python
from earnings_data_client import EarningsDataClient

# Create client (automatically uses .env configuration)
client = EarningsDataClient()

# Query transcripts
transcripts = client.query_transcripts(tickers="AAPL")
print(f"Found {len(transcripts)} AAPL transcripts")

for t in transcripts[:5]:
    print(f"  {t.year} {t.quarter}: {t.file_path.name}")

# Query SEC filings
filings = client.query_filings(tickers="AAPL", form_types="10-K")
print(f"\nFound {len(filings)} 10-K filings")

for f in filings:
    print(f"  {f.year}: {f.form_type}")

# Get statistics
stats = client.get_statistics()
print(f"\nTotal files: {stats.total_files}")
print(f"Total size: {stats.total_size_mb:.2f} MB")

client.close()
```

---

## Environment Variables Configuration

### Available Variables

Create a `.env` file with these variables:

```bash
# Required: Base data directory
EARNINGS_DATA_DIR=/path/to/your/data
```

### Priority Order

The package reads configuration in this order (highest to lowest):

1. **Explicit parameter in code**: `Config(data_dir="/path")`
2. **Environment variable**: `EARNINGS_DATA_DIR` (from `.env` or shell)
3. **Config file**: `~/.earnings_data/config.json`
4. **Default**: `~/.earnings_data`

### Example Configurations

**Development (use project subdirectory):**
```bash
EARNINGS_DATA_DIR=./data
```

**Production (use dedicated location):**
```bash
EARNINGS_DATA_DIR=/data/earnings
```

**Multi-project (shared location):**
```bash
EARNINGS_DATA_DIR=/Users/arunath/shared/earnings
```

---

## Directory Structure After Migration

```
Your configured data directory (e.g., ./data/):
├── transcripts/           # 726 earnings call transcripts
│   ├── AAPL_2025_Q1_earningstranscript_from_fool.md
│   ├── MSFT_2024_Q4_earningstranscript_from_fool.md
│   └── ...
├── secfilings/           # SEC filings (10-K, 10-Q, etc.)
│   ├── AAPL_2015_FY_10-K.html
│   ├── AAPL_2015_Q1_10-Q.html
│   └── ...
├── cache/                # SEC bulk data cache
│   ├── download_progress.db
│   ├── submissions.zip
│   └── submissions/
└── metadata.db           # SQLite index (created by earnings-index)
```

---

## Troubleshooting

### Issue: "No data found" when running examples

**Solution:**

1. Check if .env file exists and has correct path:
   ```bash
   cat .env
   ```

2. Verify data was migrated:
   ```bash
   # Check what config is being used
   earnings-config --show

   # List files in data directory
   ls -lh $(python -c "from config import get_config; print(get_config().transcripts_dir)")
   ```

3. Make sure index was created:
   ```bash
   earnings-index --stats
   ```

### Issue: ".env file not being read"

**Solution:**

1. Make sure python-dotenv is installed:
   ```bash
   pip install python-dotenv
   ```

2. .env file must be in the directory where you run the commands:
   ```bash
   # Should be in project root
   ls -la .env
   ```

3. Alternatively, set environment variable directly:
   ```bash
   export EARNINGS_DATA_DIR=./data
   ```

### Issue: "Data directory not found"

**Solution:**

```bash
# Initialize the directory structure
earnings-config --init

# Or run migration again
python migrate_data.py
```

### Issue: "Permission denied"

**Solution:**

Make sure you have write permissions to the target directory:

```bash
# Check permissions
ls -ld /path/to/your/data

# Fix permissions if needed
chmod 755 /path/to/your/data
```

---

## Complete Example

Here's a complete workflow from scratch:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create .env file
cat > .env << EOF
EARNINGS_DATA_DIR=./data
EOF

# 3. Test configuration
earnings-config --show

# 4. Dry run migration
python migrate_data.py --dry-run

# 5. Actual migration
python migrate_data.py

# 6. Create index
earnings-index

# 7. Check stats
earnings-index --stats

# 8. Test query
earnings-query -t AAPL

# 9. Run Python examples
python examples/basic_usage.py

# 10. Success! 🎉
```

---

## Next Steps

After successful migration:

1. **Test the integration**: Run `python examples/basic_usage.py`
2. **Try agentic workflow**: See `examples/agentic_workflow_integration.py`
3. **Download more data**: Use `earnings-download-transcripts` or `earnings-download-sec`
4. **Reindex**: After downloading new data, run `earnings-index` again

---

## Integration with Your Agentic Workflow

Once bootstrapped, use in your workflow project:

```python
# In your agentic workflow project
from earnings_data_client import EarningsDataClient

# Automatically uses .env configuration
client = EarningsDataClient()

# Query data
data = client.get_ticker_data("AAPL")

# Use in your agents...
for transcript in data['transcripts']:
    content = transcript.load_content()
    # Send to LLM for analysis

client.close()
```

**Shared Configuration:**

Both projects can share the same .env file or EARNINGS_DATA_DIR environment variable!

---

## Questions?

- Check `USAGE.md` for comprehensive documentation
- Check `QUICKSTART.md` for quick reference
- See `examples/` for code examples
- Report issues: https://github.com/arunsmiles/earningstranscripts/issues

#!/usr/bin/env python3
"""
Basic Usage Examples for EarningsDataClient

This script demonstrates the basic usage of the earnings data client
for querying transcripts and SEC filings.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports (if running as standalone script)
sys.path.insert(0, str(Path(__file__).parent.parent))

from client import EarningsDataClient
from config import Config


def example_1_basic_query():
    """Example 1: Basic query for a single ticker"""
    print("\n" + "=" * 60)
    print("Example 1: Query transcripts for AAPL")
    print("=" * 60)

    # Create client (uses default config or EARNINGS_DATA_DIR env var)
    client = EarningsDataClient()

    # Query all AAPL transcripts
    transcripts = client.query_transcripts(tickers="AAPL")

    print(f"\nFound {len(transcripts)} transcripts for AAPL:")
    for t in transcripts[:5]:  # Show first 5
        print(f"  {t.year} {t.quarter}: {t.file_path.name}")

    client.close()


def example_2_filtered_query():
    """Example 2: Query with filters"""
    print("\n" + "=" * 60)
    print("Example 2: Query 2024 Q3 earnings for multiple tickers")
    print("=" * 60)

    client = EarningsDataClient()

    # Query specific year and quarter for multiple tickers
    transcripts = client.query_transcripts(
        tickers=["AAPL", "MSFT", "GOOGL"],
        year=2024,
        quarter="Q3"
    )

    print(f"\nFound {len(transcripts)} transcripts:")
    for t in transcripts:
        print(f"  {t.ticker:6s} {t.year} {t.quarter}: {t.file_path.name}")

    client.close()


def example_3_sec_filings():
    """Example 3: Query SEC filings"""
    print("\n" + "=" * 60)
    print("Example 3: Query 10-K and 10-Q filings for AAPL")
    print("=" * 60)

    client = EarningsDataClient()

    # Query 10-K filings (annual reports)
    filings_10k = client.query_filings(
        tickers="AAPL",
        form_types="10-K",
        limit=5
    )

    print(f"\nFound {len(filings_10k)} 10-K filings:")
    for f in filings_10k:
        print(f"  {f.year} FY: {f.file_path.name}")

    # Query 10-Q filings (quarterly reports)
    filings_10q = client.query_filings(
        tickers="AAPL",
        form_types="10-Q",
        year=2024
    )

    print(f"\nFound {len(filings_10q)} 10-Q filings for 2024:")
    for f in filings_10q:
        print(f"  {f.year} {f.quarter}: {f.file_path.name}")

    client.close()


def example_4_all_ticker_data():
    """Example 4: Get all data for a ticker"""
    print("\n" + "=" * 60)
    print("Example 4: Get all data for MSFT")
    print("=" * 60)

    client = EarningsDataClient()

    # Get all data for a ticker
    data = client.get_ticker_data("MSFT")

    print(f"\nMSFT Data:")
    print(f"  Transcripts: {len(data['transcripts'])}")
    print(f"  Filings:     {len(data['filings'])}")

    # Show recent transcripts
    print(f"\nRecent transcripts:")
    for t in data['transcripts'][:3]:
        print(f"  {t.year} {t.quarter}: {t.file_path.name}")

    # Show recent filings
    print(f"\nRecent filings:")
    for f in data['filings'][:3]:
        print(f"  {f.year} {f.quarter or 'FY':3s} {f.form_type}: {f.file_path.name}")

    client.close()


def example_5_aggregate_queries():
    """Example 5: Aggregate queries and statistics"""
    print("\n" + "=" * 60)
    print("Example 5: Aggregate queries and statistics")
    print("=" * 60)

    client = EarningsDataClient()

    # Get file counts by ticker
    by_ticker = client.aggregate_by_ticker()
    print(f"\nTop 10 tickers by file count:")
    for i, (ticker, count) in enumerate(list(by_ticker.items())[:10], 1):
        print(f"  {i:2d}. {ticker:6s} {count:4d} files")

    # Get file counts by year
    by_year = client.aggregate_by_year()
    print(f"\nFiles by year:")
    for year, count in list(by_year.items())[:5]:
        print(f"  {year}: {count:4d} files")

    # Get comprehensive statistics
    stats = client.get_statistics()
    print(f"\nOverall Statistics:")
    print(f"  Total files:   {stats.total_files}")
    print(f"  Total size:    {stats.total_size_mb:.2f} MB")
    print(f"  Date range:    {stats.date_range[0]} - {stats.date_range[1]}")
    print(f"  Transcripts:   {stats.by_type.get('transcript', 0)}")
    print(f"  Filings:       {stats.by_type.get('filing', 0)}")

    client.close()


def example_6_load_content():
    """Example 6: Load file content"""
    print("\n" + "=" * 60)
    print("Example 6: Load and analyze file content")
    print("=" * 60)

    client = EarningsDataClient()

    # Query with content loading
    transcripts = client.query_transcripts(
        tickers="AAPL",
        year=2024,
        quarter="Q3",
        load_content=True  # Load content immediately
    )

    if transcripts:
        t = transcripts[0]
        content = t.content
        print(f"\nTranscript: {t.file_path.name}")
        print(f"Size:       {len(content):,} characters")
        print(f"Preview:    {content[:200]}...")
    else:
        print("\nNo transcripts found for AAPL 2024 Q3")

    client.close()


def example_7_year_range():
    """Example 7: Query with year range"""
    print("\n" + "=" * 60)
    print("Example 7: Query data for a date range")
    print("=" * 60)

    client = EarningsDataClient()

    # Query transcripts from 2022 to 2024
    transcripts = client.query_transcripts(
        tickers=["AAPL", "MSFT"],
        year_range=(2022, 2024)
    )

    print(f"\nFound {len(transcripts)} transcripts from 2022-2024:")

    # Group by year
    by_year = {}
    for t in transcripts:
        by_year.setdefault(t.year, []).append(t)

    for year in sorted(by_year.keys(), reverse=True):
        print(f"  {year}: {len(by_year[year])} transcripts")

    client.close()


def example_8_list_available_data():
    """Example 8: List available tickers and years"""
    print("\n" + "=" * 60)
    print("Example 8: List available data")
    print("=" * 60)

    client = EarningsDataClient()

    # Get all indexed tickers
    tickers = client.get_tickers()
    print(f"\nAvailable tickers ({len(tickers)}):")
    print(f"  {', '.join(tickers[:20])}")
    if len(tickers) > 20:
        print(f"  ... and {len(tickers) - 20} more")

    # Get available years
    years = client.get_years()
    print(f"\nAvailable years:")
    print(f"  {', '.join(map(str, years))}")

    # Get years for specific ticker
    aapl_years = client.get_years(ticker="AAPL")
    print(f"\nYears with AAPL data:")
    print(f"  {', '.join(map(str, aapl_years))}")

    client.close()


def main():
    """Run all examples"""
    print("\n" + "=" * 60)
    print("EARNINGS DATA CLIENT - USAGE EXAMPLES")
    print("=" * 60)

    try:
        example_1_basic_query()
        example_2_filtered_query()
        example_3_sec_filings()
        example_4_all_ticker_data()
        example_5_aggregate_queries()
        example_6_load_content()
        example_7_year_range()
        example_8_list_available_data()

        print("\n" + "=" * 60)
        print("All examples completed successfully!")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\nError: {e}")
        print("\nMake sure you have:")
        print("  1. Downloaded some data (transcripts or filings)")
        print("  2. Run the indexer: earnings-index")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

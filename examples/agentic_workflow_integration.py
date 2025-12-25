#!/usr/bin/env python3
"""
Agentic Workflow Integration Example

This example demonstrates how to integrate earnings-data-client
into an agentic workflow orchestrator.

Use Case: An AI agent that analyzes company earnings and generates reports.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from client import EarningsDataClient
from config import Config


class EarningsAnalysisAgent:
    """
    Example agent that analyzes earnings data.

    This agent demonstrates how your agentic workflow can use
    the earnings data client to access transcripts and filings.
    """

    def __init__(self, data_dir: str = None):
        """
        Initialize the agent with access to earnings data.

        Args:
            data_dir: Optional custom data directory
        """
        # Set up configuration
        if data_dir:
            self.config = Config(data_dir)
        else:
            self.config = Config()  # Uses default or env var

        # Initialize client
        self.client = EarningsDataClient(config=self.config)

        print(f"Agent initialized with data from: {self.config.data_dir}")

    def analyze_company_performance(self, ticker: str, year: int) -> Dict:
        """
        Analyze company performance for a given year.

        This is a simplified example. In a real agentic workflow,
        you would use an LLM to analyze the content.
        """
        print(f"\n{'=' * 60}")
        print(f"Analyzing {ticker} performance for {year}")
        print(f"{'=' * 60}")

        # Get all data for the year
        transcripts = self.client.query_transcripts(
            tickers=ticker,
            year=year
        )

        filings = self.client.query_filings(
            tickers=ticker,
            year=year
        )

        # Collect analysis data
        analysis = {
            'ticker': ticker,
            'year': year,
            'transcripts_count': len(transcripts),
            'filings_count': len(filings),
            'quarters_covered': []
        }

        # Check which quarters have data
        for t in transcripts:
            if t.quarter not in analysis['quarters_covered']:
                analysis['quarters_covered'].append(t.quarter)

        # In a real implementation, you would:
        # 1. Load the content: t.load_content()
        # 2. Send to LLM for analysis
        # 3. Extract key metrics, sentiment, etc.

        print(f"\nData Summary:")
        print(f"  Transcripts: {analysis['transcripts_count']}")
        print(f"  Filings:     {analysis['filings_count']}")
        print(f"  Quarters:    {', '.join(sorted(analysis['quarters_covered']))}")

        return analysis

    def compare_companies(self, tickers: List[str], year: int, quarter: str) -> Dict:
        """
        Compare multiple companies for a specific quarter.

        Example of aggregate analysis across companies.
        """
        print(f"\n{'=' * 60}")
        print(f"Comparing companies for {year} {quarter}")
        print(f"{'=' * 60}")

        results = {}

        for ticker in tickers:
            # Get transcript for this quarter
            transcripts = self.client.query_transcripts(
                tickers=ticker,
                year=year,
                quarter=quarter
            )

            # Get 10-Q filing
            filings = self.client.query_filings(
                tickers=ticker,
                year=year,
                quarter=quarter,
                form_types="10-Q"
            )

            results[ticker] = {
                'has_transcript': len(transcripts) > 0,
                'has_10q': len(filings) > 0,
                'transcript_size': transcripts[0].file_size_bytes if transcripts else 0,
                'filing_size': filings[0].file_size_bytes if filings else 0
            }

            # In real implementation, analyze content here
            if transcripts:
                # content = transcripts[0].load_content()
                # Send to LLM for sentiment analysis, key topics, etc.
                pass

        # Print comparison
        print(f"\nComparison Results:")
        print(f"{'Ticker':<8} {'Transcript':<12} {'10-Q':<12}")
        print("-" * 40)
        for ticker, data in results.items():
            has_t = "✓" if data['has_transcript'] else "✗"
            has_f = "✓" if data['has_10q'] else "✗"
            print(f"{ticker:<8} {has_t:<12} {has_f:<12}")

        return results

    def track_company_over_time(self, ticker: str, quarters: int = 4) -> Dict:
        """
        Track a company's data over the last N quarters.

        Example of time-series analysis.
        """
        print(f"\n{'=' * 60}")
        print(f"Tracking {ticker} over last {quarters} quarters")
        print(f"{'=' * 60}")

        # Get all transcripts, sorted by date
        transcripts = self.client.query_transcripts(
            tickers=ticker,
            limit=quarters
        )

        timeline = []
        for t in transcripts:
            timeline.append({
                'period': f"{t.year} {t.quarter}",
                'file_size': t.file_size_bytes,
                'file_path': t.file_path
            })

            # In real implementation:
            # - Load content and extract metrics
            # - Track sentiment trends
            # - Identify recurring topics
            # - Compare quarter-over-quarter changes

        print(f"\nQuarterly Data:")
        for i, item in enumerate(timeline, 1):
            size_kb = item['file_size'] / 1024
            print(f"  {i}. {item['period']}: {size_kb:.1f} KB")

        return {
            'ticker': ticker,
            'periods_analyzed': len(timeline),
            'timeline': timeline
        }

    def generate_portfolio_report(self, tickers: List[str], year: int) -> Dict:
        """
        Generate a report for a portfolio of companies.

        Example of batch processing for multiple tickers.
        """
        print(f"\n{'=' * 60}")
        print(f"Generating Portfolio Report for {year}")
        print(f"{'=' * 60}")

        report = {
            'year': year,
            'companies': {},
            'summary': {}
        }

        for ticker in tickers:
            # Get all data for the company
            data = self.client.get_ticker_data(ticker)

            # Filter by year
            year_transcripts = [
                t for t in data['transcripts']
                if t.year == year
            ]
            year_filings = [
                f for f in data['filings']
                if f.year == year
            ]

            report['companies'][ticker] = {
                'transcripts': len(year_transcripts),
                'filings': len(year_filings)
            }

            print(f"\n{ticker}:")
            print(f"  Transcripts: {len(year_transcripts)}")
            print(f"  Filings:     {len(year_filings)}")

            # In real implementation:
            # - Analyze each company's documents
            # - Extract key financial metrics
            # - Generate company-specific insights
            # - Aggregate insights across portfolio

        # Summary statistics
        total_transcripts = sum(c['transcripts'] for c in report['companies'].values())
        total_filings = sum(c['filings'] for c in report['companies'].values())

        report['summary'] = {
            'total_companies': len(tickers),
            'total_transcripts': total_transcripts,
            'total_filings': total_filings
        }

        print(f"\nPortfolio Summary:")
        print(f"  Companies:   {report['summary']['total_companies']}")
        print(f"  Transcripts: {report['summary']['total_transcripts']}")
        print(f"  Filings:     {report['summary']['total_filings']}")

        return report

    def close(self):
        """Clean up resources"""
        self.client.close()


def example_workflow():
    """
    Example agentic workflow using earnings data.

    This demonstrates how an AI agent orchestrator would use
    the earnings data client to perform analysis tasks.
    """
    # Initialize agent
    agent = EarningsAnalysisAgent()

    # Task 1: Analyze single company
    aapl_analysis = agent.analyze_company_performance("AAPL", 2024)

    # Task 2: Compare competitors
    tech_companies = ["AAPL", "MSFT", "GOOGL"]
    comparison = agent.compare_companies(tech_companies, 2024, "Q3")

    # Task 3: Track company over time
    timeline = agent.track_company_over_time("MSFT", quarters=4)

    # Task 4: Portfolio analysis
    portfolio = ["AAPL", "MSFT", "GOOGL", "META", "AMZN"]
    report = agent.generate_portfolio_report(portfolio, 2024)

    # Cleanup
    agent.close()

    return {
        'company_analysis': aapl_analysis,
        'comparison': comparison,
        'timeline': timeline,
        'portfolio_report': report
    }


def integration_pattern_example():
    """
    Shows the recommended integration pattern for your agentic workflow.
    """
    print("\n" + "=" * 60)
    print("RECOMMENDED INTEGRATION PATTERN")
    print("=" * 60)

    print("""
1. SET SHARED DATA DIRECTORY
   ------------------------
   In your agentic workflow project, set the data directory:

   import os
   os.environ['EARNINGS_DATA_DIR'] = '/path/to/shared/data'

   OR configure in your project's config:

   from earnings_data_client import Config
   config = Config('/path/to/shared/data')

2. CREATE CLIENT IN YOUR AGENT
   ----------------------------
   Your agent creates a client to access data:

   from earnings_data_client import EarningsDataClient

   class MyAgent:
       def __init__(self):
           self.earnings_client = EarningsDataClient()

       def analyze_company(self, ticker):
           data = self.earnings_client.get_ticker_data(ticker)
           # Process data with your LLM...

3. QUERY DATA AS NEEDED
   --------------------
   Use the client's query methods:

   # Per-ticker queries
   transcripts = client.query_transcripts(tickers="AAPL", year=2024)
   filings = client.query_filings(tickers="AAPL", form_types="10-K")

   # Aggregate queries
   all_tickers = client.get_tickers()
   stats = client.get_statistics()

   # Load content for LLM processing
   for t in transcripts:
       content = t.load_content()
       # Send to your LLM for analysis...

4. DOWNLOAD NEW DATA
   -----------------
   Your workflow can trigger downloads when needed:

   from earnings_data_client import FoolTranscriptDownloader

   downloader = FoolTranscriptDownloader()
   downloader.download_all(ticker="AAPL")

   # Reindex after downloading
   client.reindex()
    """)


def main():
    """Run integration examples"""
    print("\n" + "=" * 60)
    print("AGENTIC WORKFLOW INTEGRATION EXAMPLES")
    print("=" * 60)

    try:
        # Show integration pattern
        integration_pattern_example()

        # Run example workflow
        print("\n" + "=" * 60)
        print("RUNNING EXAMPLE WORKFLOW")
        print("=" * 60)

        results = example_workflow()

        print("\n" + "=" * 60)
        print("WORKFLOW COMPLETED SUCCESSFULLY")
        print("=" * 60)

        print(f"\nResults Summary:")
        print(f"  Company analysis:  ✓")
        print(f"  Comparison:        ✓")
        print(f"  Timeline tracking: ✓")
        print(f"  Portfolio report:  ✓")

    except Exception as e:
        print(f"\nError: {e}")
        print("\nMake sure you have:")
        print("  1. Downloaded earnings data")
        print("  2. Run the indexer")
        print("  3. Set EARNINGS_DATA_DIR if using custom location")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

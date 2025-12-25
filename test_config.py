#!/usr/bin/env python3
"""
Test script to verify that all downloaders properly use the centralized config system.
"""

import tempfile
import shutil
from pathlib import Path

from config import Config
from fool_transcript_downloader import FoolTranscriptDownloader
from sec_edgar_downloader import SECEdgarDownloader
from sec_bulk_downloader import SECBulkDownloader


def test_config_system():
    """Test that all downloaders use the configured data directory"""

    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        test_data_dir = Path(temp_dir) / "test_earnings_data"
        print(f"Testing with data directory: {test_data_dir}")

        # Create a config with the test directory
        config = Config(data_dir=str(test_data_dir))

        print(f"\nConfig created:")
        print(f"  Data dir: {config.data_dir}")
        print(f"  Transcripts: {config.transcripts_dir}")
        print(f"  SEC filings: {config.secfilings_dir}")
        print(f"  Cache: {config.cache_dir}")

        # Test 1: FoolTranscriptDownloader with config
        print(f"\n[Test 1] FoolTranscriptDownloader with config parameter")
        fool_downloader = FoolTranscriptDownloader(config=config)
        assert fool_downloader.output_dir == config.transcripts_dir, \
            f"Expected {config.transcripts_dir}, got {fool_downloader.output_dir}"
        assert fool_downloader.output_dir.exists(), "Transcripts directory should exist"
        print(f"  ✓ Output dir: {fool_downloader.output_dir}")

        # Test 2: FoolTranscriptDownloader with data_dir
        print(f"\n[Test 2] FoolTranscriptDownloader with data_dir parameter")
        fool_downloader2 = FoolTranscriptDownloader(data_dir=str(test_data_dir))
        assert fool_downloader2.output_dir == config.transcripts_dir
        print(f"  ✓ Output dir: {fool_downloader2.output_dir}")

        # Test 3: SECEdgarDownloader with config
        print(f"\n[Test 3] SECEdgarDownloader with config parameter")
        sec_downloader = SECEdgarDownloader(config=config)
        assert sec_downloader.output_dir == config.secfilings_dir, \
            f"Expected {config.secfilings_dir}, got {sec_downloader.output_dir}"
        assert sec_downloader.output_dir.exists(), "SEC filings directory should exist"
        print(f"  ✓ Output dir: {sec_downloader.output_dir}")

        # Test 4: SECEdgarDownloader with data_dir
        print(f"\n[Test 4] SECEdgarDownloader with data_dir parameter")
        sec_downloader2 = SECEdgarDownloader(data_dir=str(test_data_dir))
        assert sec_downloader2.output_dir == config.secfilings_dir
        print(f"  ✓ Output dir: {sec_downloader2.output_dir}")

        # Test 5: SECBulkDownloader with config
        print(f"\n[Test 5] SECBulkDownloader with config parameter")
        bulk_downloader = SECBulkDownloader(config=config)
        assert bulk_downloader.output_dir == config.secfilings_dir
        assert bulk_downloader.cache_dir == config.cache_dir
        assert bulk_downloader.cache_dir.exists(), "Cache directory should exist"
        print(f"  ✓ Output dir: {bulk_downloader.output_dir}")
        print(f"  ✓ Cache dir: {bulk_downloader.cache_dir}")

        # Test 6: SECBulkDownloader with data_dir
        print(f"\n[Test 6] SECBulkDownloader with data_dir parameter")
        bulk_downloader2 = SECBulkDownloader(data_dir=str(test_data_dir))
        assert bulk_downloader2.output_dir == config.secfilings_dir
        assert bulk_downloader2.cache_dir == config.cache_dir
        print(f"  ✓ Output dir: {bulk_downloader2.output_dir}")
        print(f"  ✓ Cache dir: {bulk_downloader2.cache_dir}")

        # Verify all expected directories were created
        print(f"\n[Verification] Checking directory structure:")
        expected_dirs = [
            config.data_dir,
            config.transcripts_dir,
            config.secfilings_dir,
            config.cache_dir
        ]
        for dir_path in expected_dirs:
            exists = "✓" if dir_path.exists() else "✗"
            print(f"  {exists} {dir_path}")
            assert dir_path.exists(), f"Directory should exist: {dir_path}"

        print(f"\n{'='*60}")
        print("All tests passed! ✓")
        print(f"{'='*60}")
        print(f"\nAll data was written to the configured directory: {test_data_dir}")
        print("The test directory will be automatically cleaned up.")


if __name__ == "__main__":
    test_config_system()
